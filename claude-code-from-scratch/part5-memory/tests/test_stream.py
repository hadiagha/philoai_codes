"""Part 3 on: streaming, events, stopping safely, headless mode and the screen. Runs on parts 3-6."""
import argparse
import json
import sys

import pytest

from cato import agent, model, tools
from cato.agent import repair, run_agent
from fakes import pieces, use_script


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))      # keep ~/.cato out of the real home
    tools.files_read.clear()
    (tmp_path / "a.py").write_text("x = 1\n")
    yield tmp_path
    model.replay_file, model.record_file, model._recorded = None, None, None


def events_of(messages, **kwargs):
    return list(run_agent(messages, "fake", **kwargs))


def test_text_streams_in_pieces(tmp_path):
    use_script(tmp_path, pieces(text="Hello there, friend."))
    messages = [{"role": "user", "content": "hi"}]
    events = events_of(messages)
    texts = [e["text"] for e in events if e["type"] == "text"]
    assert len(texts) == 4 and "".join(texts) == "Hello there, friend."
    assert events[-1] == {"type": "done", "text": "Hello there, friend.", "reason": "end", "turns": 1}
    assert messages[-1] == {"role": "assistant", "content": "Hello there, friend."}


def test_tool_call_glued_and_run(tmp_path):
    use_script(tmp_path,
               pieces(calls=[("Read", {"file_path": "a.py"}), ("Grep", {"pattern": "x"})]),
               pieces(text="x is 1."))
    messages = [{"role": "user", "content": "what is x"}]
    events = events_of(messages)
    kinds = [e["type"] for e in events]
    # two reads: from part 4 on they run side by side, so both starts may come first
    assert kinds[0] == "usage" and sorted(kinds[1:5]) == ["tool_end", "tool_end", "tool_start", "tool_start"]
    assert kinds[1] == "tool_start" and kinds[5:] == ["text", "text", "usage", "done"]
    call = messages[1]["tool_calls"][0]
    assert call["function"] == {"name": "Read", "arguments": json.dumps({"file_path": "a.py"})}
    assert messages[2]["tool_call_id"] == "call_0" and "x = 1" in messages[2]["content"]
    assert messages[3]["tool_call_id"] == "call_1"


def test_reasoning_is_kept_for_next_turn(tmp_path):
    use_script(tmp_path, pieces(text="ok", reasoning="Let me think about it."))
    messages = []
    events_of(messages)
    assert messages[0]["reasoning_details"] == [
        {"type": "reasoning.text", "index": 0, "text": "Let me think about it."}]


def test_changes_need_a_yes(tmp_path):
    edit = ("Write", {"file_path": "b.txt", "content": "hi"})
    use_script(tmp_path, pieces(calls=[edit]), pieces(text="no"), pieces(calls=[edit]), pieces(text="yes"))
    events_of([])                                             # nobody to ask: no
    assert not (tmp_path / "b.txt").exists()
    asked = []
    events_of([], ask=lambda name, *rest: asked.append(name) or "yes")
    assert asked == ["Write"] and (tmp_path / "b.txt").read_text() == "hi"


def test_cost_and_turn_limits(tmp_path):
    loop = pieces(calls=[("Glob", {"pattern": "*"})], usage={"cost": 0.3})
    use_script(tmp_path, *[loop] * 5)
    assert events_of([], max_cost=0.5)[-1]["reason"] == "cost limit $0.5"
    use_script(tmp_path, *[loop] * 5)
    assert events_of([], max_turns=2)[-1]["reason"] == "turn limit (2)"


def test_repair_answers_every_request():
    messages = [{"role": "user", "content": "go"},
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "a", "function": {}}, {"id": "b", "function": {}}]},
                {"role": "tool", "tool_call_id": "a", "content": "done"}]
    repair(messages)
    assert messages[-1] == {"role": "tool", "tool_call_id": "b",
                            "content": "Stopped by the user before this finished."}
    repair(messages)
    assert len(messages) == 4      # nothing left to repair


def test_stream_error_raises(tmp_path):
    use_script(tmp_path, [{"error": {"message": "overloaded"}}])
    with pytest.raises(model.ModelError, match="overloaded"):
        events_of([])


def test_record_then_replay(tmp_path):
    use_script(tmp_path, pieces(text="recorded answer"))
    model.record_file = str(tmp_path / "rec.jsonl")
    events_of([])
    model.record_file = None
    model.replay_file, model._recorded = str(tmp_path / "rec.jsonl"), None
    assert events_of([])[-1]["text"] == "recorded answer"


def test_headless_json(tmp_path, monkeypatch, capsys):
    from cato.__main__ import main
    use_script(tmp_path, pieces(calls=[("Bash", {"command": "echo hi"})]), pieces(text="Said hi."))
    monkeypatch.setattr(sys, "argv", ["cato", "-p", "say hi", "--yes", "--json",
                                      "--replay", model.replay_file])
    model._recorded = None
    main()
    out = json.loads(capsys.readouterr().out)
    assert out["result"] == "Said hi." and out["turns"] == 2 and out["reason"] == "end"
    assert out["cost"] == pytest.approx(0.002)


def test_screen_with_scripted_inputs(tmp_path):
    from cato import ui
    use_script(tmp_path,
               pieces(text="Let me fix it.", calls=[("Read", {"file_path": "a.py"})]),
               pieces(calls=[("Edit", {"file_path": "a.py", "old_string": "1", "new_string": "2"})]),
               pieces(text="Done: **x** is now 2."))
    (tmp_path / "inputs.txt").write_text("set x to 2\ny\n/cost\n/exit\n")
    args = argparse.Namespace(model="terra", mode=None, desk_limit=None, max_turns=10, max_cost=None,
                              inputs=str(tmp_path / "inputs.txt"), svg=str(tmp_path / "shot.svg"))
    ui.repl(args)
    assert (tmp_path / "a.py").read_text() == "x = 2\n"
    svg = svg_text(tmp_path / "shot.svg")
    assert "Cato Code" in svg and "Edit(a.py)" in svg and "x is now 2." in svg and "+x = 2" in svg


def svg_text(path):
    """The words in a Rich SVG, without the drawing code around them."""
    import html, re
    return html.unescape(re.sub(r"<[^>]+>", "", path.read_text())).replace("\xa0", " ")
