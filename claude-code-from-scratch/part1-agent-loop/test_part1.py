"""Part 1: the loop with one bash tool, driven by a fake model."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import os
os.environ.setdefault("OPENROUTER_API_KEY", "test")
import cato  # noqa: E402  (cato.py, next to this file)


def reply(text=None, command=None):
    message = {"role": "assistant", "content": text}
    if command:
        message["tool_calls"] = [{"id": "call_1", "type": "function", "function": {
            "name": "bash", "arguments": json.dumps({"command": command})}}]
    return message


def test_loop_runs_tool_then_answers(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    replies = [reply(command="echo hello"), reply(text="Done.")]
    monkeypatch.setattr(cato, "ask_model", lambda messages: replies.pop(0))
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    messages = [{"role": "user", "content": "say hello"}]
    assert cato.agent_loop(messages) == "Done."
    assert messages[2] == {"role": "tool", "tool_call_id": "call_1", "content": "hello\n"}


def test_user_can_say_no(monkeypatch):
    replies = [reply(command="rm -rf /tmp/x"), reply(text="Okay.")]
    monkeypatch.setattr(cato, "ask_model", lambda messages: replies.pop(0))
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    messages = []
    cato.agent_loop(messages)
    assert "said no" in messages[1]["content"]


def test_turn_limit(monkeypatch):
    monkeypatch.setattr(cato, "ask_model", lambda messages: reply(command="true"))
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    assert cato.agent_loop([]) == f"Stopped after {cato.MAX_TURNS} turns."
