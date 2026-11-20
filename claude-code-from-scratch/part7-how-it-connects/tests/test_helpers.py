"""Part 6: subagents, skills, slash commands and MCP. Runs on part 6."""
import json
import sys
from pathlib import Path

import pytest

from cato import model, tools
from cato.agent import run_agent
from cato.cards import find_cards, read_card, skill_menu
from cato.context import reminders
from cato.helpers import helper_tools
from cato.mcp import load_servers, stop_servers
from cato.tools import TOOLS, run_tool
from fakes import pieces, use_script

NOTES_SERVER = Path(__file__).parents[1] / "examples" / "playground" / "mcp" / "notes_server.py"
if not NOTES_SERVER.exists():   # the public philoai_codes folder: the shop sits next to the tests
    NOTES_SERVER = Path(__file__).parents[1] / "shop" / "mcp" / "notes_server.py"


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    tools.files_read.clear()
    (work / "a.py").write_text("def pay(amount):\n    return charge(amount)\n")
    yield work
    model.replay_file, model._recorded = None, None


def card(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def rules(**kw):
    return {"mode": "default", "allow": [], "ask": [], "deny": [], "hooks": {}, **kw}


def test_read_card(project):
    card(project / ".cato" / "agents" / "reviewer.md",
         "---\nname: reviewer\ndescription: Finds bugs.\ntools: Read, Grep\n---\nYou review code.\n")
    header, body = read_card(project / ".cato" / "agents" / "reviewer.md")
    assert header == {"name": "reviewer", "description": "Finds bugs.", "tools": "Read, Grep"}
    assert body == "You review code."


def test_project_cards_win(project, tmp_path):
    card(tmp_path / "home" / ".cato" / "skills" / "deploy" / "SKILL.md", "---\ndescription: mine\n---\nA")
    card(project / ".cato" / "skills" / "deploy" / "SKILL.md", "---\ndescription: project\n---\nB")
    card(tmp_path / "home" / ".cato" / "skills" / "notes" / "SKILL.md", "---\ndescription: notes\n---\nC")
    skills = find_cards("skills")
    assert skills["deploy"]["body"] == "B" and skills["notes"]["body"] == "C"
    assert "- deploy: project" in skill_menu() and "- deploy: project" in reminders()


def test_skill_tool_loads_the_full_card(project):
    card(project / ".cato" / "skills" / "release" / "SKILL.md",
         "---\ndescription: How we release.\n---\n1. Bump the version.\n2. Tag it.")
    use_script(project, pieces(calls=[("Skill", {"name": "release"})]), pieces(text="ok"))
    messages = []
    list(run_agent(messages, "fake", tools=TOOLS + helper_tools("fake", rules(), None), settings=rules()))
    assert "1. Bump the version." in messages[1]["content"]


def test_subagent_has_a_clean_desk(project):
    use_script(project,
               pieces(calls=[("Agent", {"description": "find payments",
                                        "prompt": "Where do we handle payments?"})]),
               pieces(calls=[("Grep", {"pattern": "charge"})]),           # the helper searches
               pieces(text="Payments: a.py:2 calls charge()."),             # the helper reports
               pieces(text="It's in a.py, line 2."))                        # the main loop answers
    seen = []
    messages = [{"role": "user", "content": "where are payments?"}]
    events = list(run_agent(messages, "fake",
                            tools=TOOLS + helper_tools("fake", rules(), None, seen.append),
                            ask=lambda *a: "yes", settings=rules()))
    assert events[-1]["text"] == "It's in a.py, line 2."
    assert [m["role"] for m in messages] == ["user", "assistant", "tool", "assistant"]
    assert "Payments: a.py:2 calls charge()." in messages[2]["content"]
    assert "a.py:2:" not in json.dumps(messages)          # the raw grep output stayed on the helper's desk
    assert [e["name"] for e in seen if e["type"] == "tool_start"] == ["Grep"]


def test_unknown_helper_is_an_error(project):
    agent = helper_tools("fake", rules(), None)[0]
    out, ok = run_tool("Agent", json.dumps({"description": "x", "prompt": "y", "subagent_type": "chef"}),
                       [agent])
    assert not ok and "No helper called chef" in out


def test_slash_command_and_skill_by_hand(project):
    from cato import ui
    card(project / ".cato" / "commands" / "review.md", "Review $ARGUMENTS for bugs. Be brief.")
    card(project / ".cato" / "skills" / "tidy" / "SKILL.md", "---\ndescription: t\n---\nTidy the folder.")
    session = {"model": "fake", "settings": rules(), "mcp_tools": []}
    assert ui.run_command(session, "/review shop.py") == ("prompt", "Review shop.py for bugs. Be brief.")
    assert ui.run_command(session, "/tidy now") == ("prompt", "Tidy the folder.\n\nARGUMENTS: now")
    assert ui.run_command(session, "/tidy") == ("prompt", "Tidy the folder.")


def test_helper_with_a_typo_in_its_tools_gets_none(project):
    card(project / ".cato" / "agents" / "sloppy.md", "---\ndescription: s\ntools: Read, Gerp\n---\nHi")
    agent = helper_tools("fake", rules(), None)[0]
    out, ok = run_tool("Agent", json.dumps({"description": "x", "prompt": "y", "subagent_type": "sloppy"}),
                       [agent])
    assert not ok and "lists a tool Cato doesn't have" in out


def write_mcp_config(project):
    (project / ".mcp.json").write_text(json.dumps(
        {"mcpServers": {"notes": {"command": sys.executable, "args": [str(NOTES_SERVER)]}}}))


def test_mcp_server_tools_join_the_list(project):
    write_mcp_config(project)
    servers, mcp_tools, problems = load_servers()
    try:
        assert problems == [] and [t.name for t in mcp_tools] == ["mcp__notes__add_note",
                                                                  "mcp__notes__list_notes"]
        assert run_tool("mcp__notes__add_note", json.dumps({"text": "buy milk"}), mcp_tools) == \
            ("Saved note 1.", True)
        assert run_tool("mcp__notes__list_notes", "{}", mcp_tools) == ("1. buy milk", True)
        out, ok = run_tool("mcp__notes__add_note", "{}", mcp_tools)
        assert not ok and "Missing required field 'text'" in out
    finally:
        stop_servers(servers)


def test_mcp_tools_obey_the_traffic_light(project):
    write_mcp_config(project)
    servers, mcp_tools, _ = load_servers()
    try:
        call = pieces(calls=[("mcp__notes__add_note", {"text": "hi"})])
        use_script(project, call, pieces(text="no"), call, pieces(text="yes"))
        messages = []
        list(run_agent(messages, "fake", tools=TOOLS + mcp_tools, settings=rules()))
        assert "said no" in messages[1]["content"]                      # nobody to ask: no
        messages = []
        list(run_agent(messages, "fake", tools=TOOLS + mcp_tools,
                       settings=rules(allow=["mcp__notes__*"])))
        assert messages[1]["content"] == "Saved note 1."
    finally:
        stop_servers(servers)


def test_broken_server_is_reported(project):
    (project / ".mcp.json").write_text(json.dumps({"mcpServers": {"bad": {"command": "no-such-program"}}}))
    servers, mcp_tools, problems = load_servers()
    assert servers == [] and problems and problems[0].startswith("bad:")


LEGACY_SERVER = """
import json, sys
ready = False
for line in sys.stdin:
    m = json.loads(line)
    if "id" not in m:
        ready = ready or m["method"] == "notifications/initialized"
        continue
    if m["method"] == "initialize":
        out = {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}}}
    elif ready and m["method"] == "tools/list":
        out = {"tools": [{"name": "ping", "inputSchema": {"type": "object"}}]}
    elif ready and m["method"] == "tools/call":
        out = {"content": [{"type": "text", "text": "pong"}]}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": m["id"], "error": {"code": -32601, "message": "no"}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": out}), flush=True)
"""


def test_older_server_gets_the_handshake(project):
    (project / "old.py").write_text(LEGACY_SERVER)
    (project / ".mcp.json").write_text(json.dumps({"mcpServers": {"old": {"command": sys.executable,
                                                                          "args": ["old.py"]}}}))
    servers, mcp_tools, problems = load_servers()
    try:
        assert problems == [] and servers[0]["version"] == "2025-11-25"
        assert run_tool("mcp__old__ping", "{}", mcp_tools) == ("pong", True)
    finally:
        stop_servers(servers)


def test_every_request_says_its_version(project, monkeypatch):
    from cato import mcp
    sent = []
    real_send = mcp.send
    monkeypatch.setattr(mcp, "send", lambda server, message: (sent.append(message), real_send(server, message)))
    write_mcp_config(project)
    servers, mcp_tools, _ = load_servers()
    try:
        assert servers[0]["version"] == "2026-07-28"
        assert [m["method"] for m in sent] == ["server/discover", "tools/list"]
        assert all(m["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] == "2026-07-28" for m in sent)
        assert [m["id"] for m in sent] == [1, 2]
    finally:
        stop_servers(servers)
    assert servers[0]["process"].poll() is not None        # closing its input ended it


def test_sending_a_helper_never_asks_but_its_tools_do(project):
    use_script(project,
               pieces(calls=[("Agent", {"description": "fix", "prompt": "Write b.py",
                                        "subagent_type": "general"})]),
               pieces(calls=[("Write", {"file_path": "b.py", "content": "x = 1\n"})]),
               pieces(text="I couldn't write b.py."),
               pieces(text="The helper wasn't allowed to write."))
    asked, messages, settings = [], [], rules()
    ask = lambda *call: asked.append(call[0]) or "no"
    list(run_agent(messages, "fake", tools=TOOLS + helper_tools("fake", settings, ask), ask=ask, settings=settings))
    assert asked == ["Write"]                       # no question for Agent; one for the helper's Write
    assert not (project / "b.py").exists()


def test_a_deny_rule_still_stops_helpers(project):
    use_script(project, pieces(calls=[("Agent", {"description": "x", "prompt": "y"})]), pieces(text="ok"))
    messages = []
    settings = rules(deny=["Agent"])
    list(run_agent(messages, "fake", tools=TOOLS + helper_tools("fake", settings, None), settings=settings))
    assert "never" in messages[1]["content"]


def test_a_server_you_decline_never_starts(project):
    write_mcp_config(project)
    asked = []
    servers, mcp_tools, problems = load_servers(lambda name, config: asked.append(name) or False)
    assert asked == ["notes"] and servers == [] and mcp_tools == [] and problems == ["notes: not started"]
