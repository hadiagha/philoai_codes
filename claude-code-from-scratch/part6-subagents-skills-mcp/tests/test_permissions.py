"""Part 4 on: the traffic light, modes, rules, hooks, and reads side by side. Runs on parts 4-6."""
import json
import sys
import time

import pytest

from cato import model, tools
from cato.agent import group_calls, run_agent
from cato.permissions import allow_from_now_on, check_call, decide, matches, split_command
from cato.settings import load_settings
from cato.tools import TOOLS, Tool, find_tool
from fakes import pieces, use_script


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    tools.files_read.clear()
    (tmp_path / "a.py").write_text("x = 1\n")
    yield tmp_path
    model.replay_file, model._recorded = None, None


def rules(mode="default", allow=(), ask=(), deny=(), hooks=None):
    return {"mode": mode, "allow": list(allow), "ask": list(ask), "deny": list(deny),
            "hooks": hooks or {}}


def light(name, settings, **args):
    return decide(name, args, find_tool(name, TOOLS), settings)[0]


def test_split_command():
    assert split_command("ls && rm -rf build") == ["ls", "rm -rf build"]
    assert split_command("a; b | c || d & e") == ["a", "b", "c", "d", "e"]
    assert split_command("pytest -q 2>&1 | tail -5") == ["pytest -q 2>&1", "tail -5"]
    assert split_command("echo 'a && b' \"c; d\"") == ["echo 'a && b' \"c; d\""]
    assert split_command("cmd &> log") == ["cmd &> log"]


def test_rule_matching():
    assert matches("Bash(git *)", "Bash", "git status")
    assert matches("Bash(git *)", "Bash", "git")
    assert not matches("Bash(git *)", "Bash", "gitk")
    assert matches("Bash(pytest)", "Bash", "pytest") and not matches("Bash(pytest)", "Bash", "pytest -x")
    assert matches("Read(.env)", "Read", "config/.env")
    assert matches("Edit(src/*)", "Edit", "src/app.py") and not matches("Edit(src/*)", "Edit", "app.py")
    assert matches("Read", "Read", "anything") and not matches("Read", "Edit", "x")


def test_the_naive_trick_is_caught():
    settings = rules(allow=["Bash(ls *)"])
    assert light("Bash", settings, command="ls -la") == "allow"
    assert light("Bash", settings, command="ls && rm -rf build") == "ask"
    settings["deny"].append("Bash(rm *)")
    assert light("Bash", settings, command="ls && rm -rf build") == "deny"


def test_deny_always_wins():
    settings = rules(mode="bypassPermissions", allow=["Bash(rm *)"], deny=["Bash(rm *)"])
    assert light("Bash", settings, command="rm -rf /") == "deny"
    assert light("Bash", settings, command="echo hi") == "allow"      # bypass allows the rest


def test_hidden_commands_always_ask():
    assert light("Bash", rules(allow=["Bash(echo *)"]), command="echo $(rm -rf x)") == "ask"


def test_reading_inside_vs_outside(project):
    assert light("Read", rules(), file_path="a.py") == "allow"
    assert light("Read", rules(), file_path="/etc/hosts") == "ask"
    assert light("Read", rules(deny=["Read(.env)"]), file_path=".env") == "deny"


def test_modes():
    assert light("Edit", rules(), file_path="a.py") == "ask"
    assert light("Edit", rules("acceptEdits"), file_path="a.py") == "allow"
    assert light("Edit", rules("acceptEdits"), file_path="/tmp/x.py") == "ask"
    assert light("Edit", rules("plan"), file_path="a.py") == "deny"
    assert light("Grep", rules("plan"), pattern="x") == "allow"


def test_yes_and_dont_ask_again():
    settings = rules()
    allow_from_now_on(settings, "Bash", {"command": "pytest -q && git status"})
    assert settings["allow"] == ["Bash(pytest -q)", "Bash(git status)"]
    allow_from_now_on(settings, "Edit", {"file_path": "a.py"})
    assert settings["mode"] == "acceptEdits"


def test_settings_files_are_joined(project):
    (project / "home" / ".cato").mkdir(parents=True)
    (project / "home" / ".cato" / "settings.json").write_text(json.dumps(
        {"permissions": {"allow": ["Bash(git *)"], "deny": ["Bash(rm *)"]}}))
    (project / ".cato").mkdir()
    (project / ".cato" / "settings.json").write_text(json.dumps(
        {"permissions": {"allow": ["Bash(pytest *)"], "defaultMode": "acceptEdits"}}))
    settings = load_settings()
    assert settings["allow"] == ["Bash(git *)", "Bash(pytest *)"] and settings["mode"] == "acceptEdits"
    assert load_settings("plan")["mode"] == "plan"


def hook(command, matcher="Edit|Write"):
    return [{"matcher": matcher, "hooks": [{"type": "command", "command": command}]}]


def test_pre_hook_blocks_with_its_message(project):
    script = project / "no_env.py"
    script.write_text("import json, sys\n"
                      "call = json.load(sys.stdin)\n"
                      "if call['tool_input'].get('file_path', '').endswith('.env'):\n"
                      "    print('Editing .env is not allowed.', file=sys.stderr); sys.exit(2)\n")
    settings = rules("bypassPermissions", hooks={"PreToolUse": hook(f"{sys.executable} {script}")})
    allowed, message = check_call("Write", json.dumps({"file_path": ".env", "content": "x"}),
                                  find_tool("Write", TOOLS), settings, None)
    assert not allowed and "Editing .env is not allowed." in message
    allowed, _ = check_call("Write", json.dumps({"file_path": "ok.txt", "content": "x"}),
                            find_tool("Write", TOOLS), settings, None)
    assert allowed


def test_post_hook_feedback_reaches_the_model(project):
    script = project / "check.py"
    script.write_text("import sys; print('Syntax error on line 1', file=sys.stderr); sys.exit(2)\n")
    settings = rules("bypassPermissions", hooks={"PostToolUse": hook(f"{sys.executable} {script}")})
    use_script(project, pieces(calls=[("Write", {"file_path": "b.py", "content": "def ("})]),
               pieces(text="I'll fix it."))
    messages = []
    list(run_agent(messages, "fake", settings=settings))
    assert "A hook found a problem: Syntax error on line 1" in messages[1]["content"]


def test_reads_run_side_by_side(project):
    def slow_read(seconds):
        time.sleep(seconds)
        return "done"
    slow = Tool("Slow", "waits", {"type": "object", "properties": {"seconds": {"type": "number"}},
                                  "required": ["seconds"]}, slow_read, read_only=True)
    bash = find_tool("Bash", TOOLS)
    calls = [{"id": str(i), "function": {"name": n, "arguments": "{}"}}
             for i, n in enumerate(["Slow", "Slow", "Bash", "Slow"])]
    assert [[c["id"] for c in g] for g in group_calls(calls, [slow, bash])] == [["0", "1"], ["2"], ["3"]]

    use_script(project, pieces(calls=[("Slow", {"seconds": 0.4})] * 3), pieces(text="ok"))
    start = time.time()
    events = list(run_agent([], "fake", tools=[slow], settings=rules()))
    assert time.time() - start < 1.0                       # not 1.2 s one after another
    assert [e["id"] for e in events if e["type"] == "tool_end"] == ["call_0", "call_1", "call_2"]
