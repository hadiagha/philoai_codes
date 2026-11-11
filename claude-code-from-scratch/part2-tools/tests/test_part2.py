"""Part 2: the loop with six tools, driven by a fake model."""
import json

from cato import agent


def reply(text=None, calls=()):
    message = {"role": "assistant", "content": text}
    if calls:
        message["tool_calls"] = [
            {"id": f"call_{i}", "type": "function",
             "function": {"name": name, "arguments": json.dumps(args)}}
            for i, (name, args) in enumerate(calls)]
    return message


def fake_model(replies):
    def ask_model(messages, tools, model):
        return replies.pop(0), {"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.0}
    return ask_model


def test_read_edit_flow(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n")
    monkeypatch.setattr(agent, "ask_model", fake_model([
        reply(calls=[("Read", {"file_path": "a.py"})]),
        reply(calls=[("Edit", {"file_path": "a.py", "old_string": "1", "new_string": "2"})]),
        reply(text="Changed x to 2."),
    ]))
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    messages = [{"role": "user", "content": "set x to 2"}]
    assert agent.agent_loop(messages, "fake") == "Changed x to 2."
    assert (tmp_path / "a.py").read_text() == "x = 2\n"
    # every request got an answer, with the matching id
    assert [m["tool_call_id"] for m in messages if m["role"] == "tool"] == ["call_0", "call_0"]


def test_read_only_tools_do_not_ask(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    asked = []
    monkeypatch.setattr("builtins.input", lambda prompt="": asked.append(prompt) or "y")
    monkeypatch.setattr(agent, "ask_model", fake_model([
        reply(calls=[("Glob", {"pattern": "*"}), ("Bash", {"command": "true"})]),
        reply(text="ok")]))
    agent.agent_loop([], "fake")
    assert len(asked) == 1  # only Bash asked


def test_describe():
    assert agent.describe("Read", json.dumps({"file_path": "shop.py"})) == "Read(shop.py)"
    assert agent.describe("Bash", "{oops") == "Bash(?)"
