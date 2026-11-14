"""The six tools and the one path every call goes through. Runs against parts 2-6."""
import json

import pytest

from cato import tools
from cato.tools import run_tool


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tools.files_read.clear()
    (tmp_path / "app.py").write_text("def hello():\n    return 'hi'\n\n\ndef bye():\n    return 'bye'\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "util.py").write_text("X = 1\nY = 'hi'\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config.py").write_text("hi = 1\n")
    return tmp_path


def call(name, **args):
    return run_tool(name, json.dumps(args))


def test_read_numbers_lines():
    out, ok = call("Read", file_path="app.py")
    assert ok and out.splitlines()[0] == "     1\tdef hello():"


def test_read_page():
    out, ok = call("Read", file_path="app.py", offset=2, limit=1)
    assert ok and out.startswith("     2\t    return 'hi'") and "more lines" in out


def test_edit_needs_read_first(project):
    out, ok = call("Edit", file_path="app.py", old_string="'hi'", new_string="'hello'")
    assert not ok and "before changing" in out


def test_edit_exact_and_unique(project):
    call("Read", file_path="app.py")
    out, ok = call("Edit", file_path="app.py", old_string="return", new_string="yield")
    assert not ok and "2 times" in out
    out, ok = call("Edit", file_path="app.py", old_string="nope", new_string="x")
    assert not ok and "not found" in out
    out, ok = call("Edit", file_path="app.py", old_string="'hi'", new_string="'hello'")
    assert ok and "+    return 'hello'" in out
    assert "'hello'" in (project / "app.py").read_text()


def test_edit_replace_all(project):
    call("Read", file_path="app.py")
    out, ok = call("Edit", file_path="app.py", old_string="return", new_string="yield",
                   replace_all=True)
    assert ok and (project / "app.py").read_text().count("yield") == 2


def test_edit_refuses_stale_file(project):
    call("Read", file_path="app.py")
    import os, time
    (project / "app.py").write_text("changed by someone else\n")
    os.utime(project / "app.py", (time.time() + 5, time.time() + 5))
    out, ok = call("Edit", file_path="app.py", old_string="changed", new_string="x")
    assert not ok and "changed since" in out


def test_write_new_and_existing(project):
    out, ok = call("Write", file_path="new/notes.txt", content="a\nb\n")
    assert ok and "Created" in out and (project / "new" / "notes.txt").exists()
    out, ok = call("Write", file_path="app.py", content="x")
    assert not ok  # must read it first


def test_glob_skips_git():
    out, ok = call("Glob", pattern="**/*.py")
    assert ok and "app.py" in out and "src/util.py" in out and ".git" not in out


def test_grep():
    out, ok = call("Grep", pattern="'hi'")
    assert ok and "app.py:2:" in out and "src/util.py:2:" in out and ".git" not in out
    out, ok = call("Grep", pattern="HELLO", ignore_case=True, glob="app*")
    assert ok and out.count("\n") == 0 and "app.py:1:" in out


def test_bash_output_and_exit_code():
    out, ok = call("Bash", command="echo hi && false")
    assert ok and "hi" in out and "exit code 1" in out


def test_bash_timeout():
    out, ok = call("Bash", command="sleep 3", timeout=1)
    assert not ok and "longer than 1 seconds" in out


def test_errors_become_results():
    assert run_tool("Nope", "{}") == ("Error: there is no tool called Nope.", False)
    out, ok = run_tool("Read", "{bad json")
    assert not ok and "not valid JSON" in out
    out, ok = call("Read")
    assert not ok and "Missing required field 'file_path'" in out
    out, ok = call("Read", file_path="app.py", offset="2")
    assert not ok and "should be of type integer" in out
    out, ok = call("Read", file_path="missing.py")
    assert not ok and "No such file" in out


def test_trim_keeps_start_and_end():
    text = "A" * 30_000 + "END"
    out = tools.trim(text, limit=1000)
    assert out.startswith("A" * 500) and out.endswith("END") and "characters cut" in out
