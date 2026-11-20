"""Part 5 on: the desk, CATO.md, the reread discount, and clearing the desk. Runs on parts 5-6."""
import argparse
import json

import pytest

from cato import context, model, tools
from cato.agent import run_agent
from cato.context import (clear_old_results, memory_files, pairs_ok, reminders, summarize,
                          system_prompt, with_reminders)
from fakes import pieces, use_script


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    home = tmp_path / "home"
    work = home / "code" / "shop"
    work.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(work)
    tools.files_read.clear()
    yield work
    model.replay_file, model.record_file, model._recorded = None, None, None


def test_system_prompt_is_stable():
    assert system_prompt() == system_prompt()
    assert system_prompt().startswith("You are Cato") and "<env>" in system_prompt()


def test_cato_md_found_top_down(project):
    (project.parent.parent / ".cato").mkdir()
    (project.parent.parent / ".cato" / "CATO.md").write_text("I like short answers.")
    (project.parent / "CATO.md").write_text("All code here uses tabs.")
    (project / "CATO.md").write_text("Run tests with: python test_shop.py")
    found = memory_files()
    assert [p.parent.name for p in found] == [".cato", "code", "shop"]
    note = reminders()
    assert note.startswith("<system-reminder>") and note.index("tabs") < note.index("python test_shop.py")
    assert with_reminders("fix it", first=True).endswith("fix it")
    assert with_reminders("fix it", first=False) == "fix it"


def test_claude_gets_the_cache_flag():
    assert model.request_body([], [], "sonnet")["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in model.request_body([], [], "terra")
    assert "tools" not in model.request_body([], [], "terra")


def chat_with_results(n):
    messages = [{"role": "system", "content": "s"}]
    for i in range(n):
        messages.append({"role": "assistant", "content": None,
                         "tool_calls": [{"id": f"c{i}", "function": {"name": "Read", "arguments": "{}"}}]})
        messages.append({"role": "tool", "tool_call_id": f"c{i}", "content": "x" * 1000})
    return messages


def test_clear_old_results_keeps_the_pairs():
    messages = chat_with_results(10)
    assert clear_old_results(messages, keep=3) == 7
    results = [m["content"] for m in messages if m["role"] == "tool"]
    assert results[:7] == [context.CLEARED] * 7 and results[7:] == ["x" * 1000] * 3
    assert pairs_ok(messages)


def test_pairs_ok_spots_an_orphan():
    messages = chat_with_results(2)
    assert pairs_ok(messages)
    assert not pairs_ok(messages[:1] + messages[2:])         # a result without its request
    assert not pairs_ok(messages[:-1])                        # a request without its result


def test_big_output_saved_to_a_file(project):
    out = tools.trim("A" * 20_000 + "END", limit=1000)
    saved = out.split("saved in ")[1].split(";")[0]
    assert out.endswith("END") and (project / saved).read_text().endswith("END")


def test_summarize_swaps_the_chat(project):
    (project / "shop.py").write_text("PRICES = {}\n")
    messages = chat_with_results(3)
    messages[1]["tool_calls"][0]["function"]["arguments"] = json.dumps({"file_path": "shop.py"})
    use_script(project, pieces(text="Goal: fix cart_total. Next: run the tests."))
    summarize(messages, "fake")
    assert len(messages) == 2 and messages[1]["role"] == "user"
    assert "Goal: fix cart_total" in messages[1]["content"]
    assert "Current contents of shop.py" in messages[1]["content"]
    assert pairs_ok(messages)


def test_auto_clear_when_the_desk_is_full(project):
    big = {"prompt_tokens": 9000, "completion_tokens": 10, "cost": 0.01}
    use_script(project,
               pieces(calls=[("Bash", {"command": "echo hi"})], usage=big),
               pieces(text="Summary: said hi."),                 # the summary call
               pieces(text="Done."))
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "x" * 40_000}]
    events = list(run_agent(messages, "fake", ask=lambda *a: "yes", desk_limit=5000))
    compact = [e for e in events if e["type"] == "compact"][0]
    assert compact["how"] == "summarized the conversation" and compact["before"] == 9010
    assert events[-1]["text"] == "Done." and pairs_ok(messages)
    assert "Summary: said hi." in messages[1]["content"]


def test_screen_context_and_memory(project):
    from cato import ui
    use_script(project, pieces(text="Hello!"))
    (project / "CATO.md").write_text("- use tabs\n")
    (project / "inputs.txt").write_text("hi\n/context\n/memory\n/exit\n")
    args = argparse.Namespace(model="terra", mode=None, desk_limit=None, max_turns=5, max_cost=None,
                              inputs=str(project / "inputs.txt"), svg=None)
    ui.repl(args)
    assert (project / "CATO.md").read_text() == "- use tabs\n"       # /memory only shows; it never writes


def test_clearing_comes_first_when_it_is_enough(project):
    big = {"prompt_tokens": 9000, "completion_tokens": 10, "cost": 0.01}
    use_script(project, pieces(calls=[("Bash", {"command": "echo hi"})], usage=big), pieces(text="Done."))
    messages = chat_with_results(6)                           # six old results, 20,000 characters each
    for message in messages:
        if message["role"] == "tool":
            message["content"] = "x" * 20_000
    messages.insert(1, {"role": "user", "content": "go"})
    events = list(run_agent(messages, "fake", ask=lambda *a: "yes", desk_limit=5000))
    compact = [e for e in events if e["type"] == "compact"][0]
    assert compact["how"].startswith("cleared") and compact["cost"] == 0     # no summary call needed
    assert events[-1]["text"] == "Done." and pairs_ok(messages)
