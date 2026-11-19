"""Record every real number, screen and request shown in Part 6, then freeze it.

    python record_part6.py --live     # calls OpenRouter: real Cato sessions -> runs.json
    python record_part6.py --demos    # no API calls: the MCP wire, the cards, the desk, replays -> demos.json
    python record_part6.py            # just rebuild ../assets/data.js from runs.json + demos.json
                                      # (in the public philoai_codes folder: numbers.json)

Run it with a Python that has httpx, rich and prompt_toolkit (the series uses ~/.cache/cato-venv).

What it records:
  runs.json   (recorded once, then frozen; every session is saved with --record, so it replays for free)
    - "alone":   a broad question about Python's asyncio package, then a follow-up. Cato can send a helper,
                 but the model chose to search by itself.
    - "helper_long": the same two messages, but the first asks for an explore helper to do the searching
                 (the first version of the explore card, which didn't limit the report).
    - "helper":  the same again, with the explore card that keeps its report under 250 words.
    - "small_alone" / "small_helper": a tiny question about the shop, answered directly, then with a helper.
    - "skill":   "add a product": the model loads the add-product skill and follows it.
    - "no_skill": a question the skill doesn't match: the card stays in its file.
    - "review":  /review shop.py, a command that sends the reviewer helper.
    - "notes":   an MCP server joins the tool list; saving a note goes through the same gate.
  demos.json  (free, repeatable)
    - the MCP wire: every line Cato and a server send each other, for a current and an older server
    - the cards: helpers, skills and commands, as files and as what Cato reads from them
    - what each piece costs on the desk: tool forms, the skill menu, a full card
    - the map of which file calls which, for Parts 5 and 6
    - replays of every live session through Cato's real screen
"""
import argparse
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERIES = HERE.parents[1]
PART6 = SERIES / "cato" / "parts" / "part6"
PART5 = SERIES / "cato" / "parts" / "part5"
PLAYGROUND = SERIES / "cato" / "examples" / "playground"
RUNS, DEMOS = HERE / "runs.json", HERE / "demos.json"
REC = HERE / "recordings"
DATA_JS = HERE.parent / "assets" / "data.js"
if (HERE / "cato" / "mcp.py").exists():   # the public philoai_codes folder: everything sits side by side
    PART6, PART5, PLAYGROUND = HERE, HERE.parent / "part5-memory", HERE / "shop"
    DATA_JS = HERE / "numbers.json"
MODEL = "sonnet"                       # anthropic/claude-sonnet-5.5, the model of Parts 1-5

BIG = ("This folder is Python's asyncio package. What happens between calling asyncio.run(main()) and the "
       "first line of main() running? Trace it step by step, with file names and line numbers.")
BIG_HELPER = BIG + " Send an explore helper to do the searching."
FOLLOW = "Now show me the exact lines where main() is wrapped in a task, and the line that finally starts it."
SMALL = "What does cart_total in shop.py return for 2 apples and 1 bread?"
SMALL_HELPER = SMALL + " Send a helper to find out."
COCOA = "Add a product called cocoa, for $4.25."
WHAT = "What does shop.py do? Two sentences."
NOTE = "Save a note for me: order more coffee beans on Friday."

# Cato reads ~/.cato too: point HOME at an empty folder, so only the project's files count.
os.environ["HOME"] = tempfile.mkdtemp(prefix="cato-home-")
os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]
sys.path.insert(0, str(PART6))
from cato import agent, cards, context, helpers, mcp, model, tools, ui  # noqa: E402

ui.console.width = 100
WORK = Path("/tmp/shop")               # the shop, as in Parts 3 to 5
PROJ = Path("/tmp/proj")               # a project holding a copy of Python's asyncio package
MARK = ".made-by-record_part6"
SHOP = ["shop.py", "test_shop.py", ".env", "CATO.md", ".cato/settings.json",
        ".cato/hooks/protect_files.py", ".cato/hooks/check_python.py",
        ".cato/agents/reviewer.md", ".cato/commands/review.md",
        ".cato/skills/add-product/SKILL.md", ".cato/skills/add-product/check_prices.py"]
MCP_FILES = [".mcp.json", "mcp/notes_server.py"]
FIXED = ("total += PRICES[product]\n", "total += PRICES[product] * count\n")   # Part 4 fixed the bug


def fresh(folder):
    if folder.exists():
        if not (folder / MARK).exists():
            sys.exit(f"{folder} exists and wasn't made by this script; move it away first.")
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    (folder / MARK).write_text("")


@contextlib.contextmanager
def inside(folder):
    old = os.getcwd()
    os.chdir(folder)
    tools.files_read.clear()
    try:
        yield folder
    finally:
        os.chdir(old)
        shutil.rmtree(folder, ignore_errors=True)


@contextlib.contextmanager
def shop(with_mcp=False):
    """A fresh copy of the playground in /tmp/shop, with Part 4's fix in place."""
    fresh(WORK)
    for name in SHOP + (MCP_FILES if with_mcp else []):
        dst = WORK / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(PLAYGROUND / name, dst)
    code = (WORK / "shop.py").read_text()
    (WORK / "shop.py").write_text(code.replace(*FIXED))
    with inside(WORK) as work:
        yield work


@contextlib.contextmanager
def project():
    """/tmp/proj/asyncio: a copy of the asyncio package from the Python that runs this script."""
    fresh(PROJ)
    shutil.copytree(Path(sysconfig.get_paths()["stdlib"]) / "asyncio", PROJ / "asyncio",
                    ignore=shutil.ignore_patterns("__pycache__"))
    with inside(PROJ) as work:
        yield work


def key():
    keyfile = SERIES.parents[1] / "openrouter.txt"
    if "OPENROUTER_API_KEY" not in os.environ and keyfile.exists():
        for word in keyfile.read_text().split():
            if word.startswith("sk-or-"):
                os.environ["OPENROUTER_API_KEY"] = word


def screen_session(tasks, answer_for=lambda name: "1", record_to=None, replay_from=None):
    """Run Cato's real screen (ui.repl) on the tasks. answer_for(tool name) answers each permission question.
    Every event is logged with its time, and a helper's events are marked "helper"."""
    ui.console.export_text(clear=True)
    model.record_file, model.replay_file, model._recorded = record_to, replay_from, None
    model.replay_delay = 0
    queue, log, start, asked, sessions = list(tasks), [], time.perf_counter(), [], []
    real = {"read_line": ui.read_line, "run_agent": ui.run_agent, "ask": ui.ask_permission, "answer": ui.answer,
            "helper_agent": helpers.run_agent}

    def ask_permission(session, screen, name, arguments, why):
        asked.append({"name": name, "arguments": arguments, "why": why})
        return real["ask"](session, screen, name, arguments, why)

    def read_line(session, prompt_text):
        if prompt_text.startswith("  "):                # a question: a permission, or starting a server
            if asked and "reply" not in asked[-1]:
                reply = answer_for(asked[-1]["name"])
                asked[-1]["reply"] = reply
            else:
                reply = "1"
                asked.append({"name": "start MCP server", "reply": reply})
            ui.console.print(f"{prompt_text}{reply}")
            return reply
        if not queue:
            raise EOFError
        line = queue.pop(0)
        ui.console.print(f"{prompt_text}{line}")
        log.append([round(time.perf_counter() - start, 3), {"type": "input", "text": line}])
        return line

    def logged(run, who):
        def wrapper(*args, **kwargs):
            for event in run(*args, **kwargs):
                log.append([round(time.perf_counter() - start, 3), {**event, "who": who}])
                yield event
        return wrapper

    def answer(session, task):
        sessions.append(session)
        return real["answer"](session, task)

    ui.read_line, ui.run_agent, ui.ask_permission, ui.answer = (read_line, logged(real["run_agent"], "main"),
                                                                ask_permission, answer)
    helpers.run_agent = logged(real["helper_agent"], "helper")
    try:
        ui.repl(argparse.Namespace(model=MODEL, max_turns=agent.MAX_TURNS, max_cost=None, mode=None,
                                   desk_limit=None, inputs=os.devnull, svg=None))
    finally:
        ui.read_line, ui.run_agent, ui.ask_permission, ui.answer = (real["read_line"], real["run_agent"],
                                                                    real["ask"], real["answer"])
        helpers.run_agent = real["helper_agent"]
        model.record_file = model.replay_file = None
    text = ui.console.export_text(clear=False)
    html = ui.console.export_html(theme=ui.PHILO_THEME, inline_styles=True, clear=True, code_format="{code}")
    session = sessions[-1] if sessions else {}
    return {"seconds": round(time.perf_counter() - start, 2), "text": text, "html": html, "events": log,
            "asked": asked, "messages": session.get("messages", []), "cost": session.get("cost", 0),
            "tokens": session.get("tokens", 0)}


def recorded_calls(path, events):
    """Every request in a recording, in order, with its usage, and who sent it (the main loop or a helper).
    The k-th usage event of the session belongs to the k-th request."""
    who = [e.get("who", "main") for _, e in events if e["type"] == "usage"]
    calls = []
    for k, line in enumerate(Path(path).read_text().splitlines()):
        usage = next((p["usage"] for p in reversed(json.loads(line)) if p.get("usage")), {})
        details = usage.get("prompt_tokens_details") or {}
        calls.append({"in": usage.get("prompt_tokens", 0), "out": usage.get("completion_tokens", 0),
                      "cached": details.get("cached_tokens", 0), "written": details.get("cache_write_tokens", 0),
                      "cost": usage.get("cost", 0), "who": who[k] if k < len(who) else "main"})
    return calls


def tool_calls(events):
    """The tool calls of a session, in order: who made them, the one-line view, and the output size."""
    out, starts = [], {}
    for t, e in events:
        if e["type"] == "tool_start":
            starts[e["id"]] = len(out)
            out.append({"t": t, "who": e.get("who", "main"), "name": e["name"],
                        "view": agent.describe(e["name"], e["arguments"]), "arguments": e["arguments"]})
        elif e["type"] == "tool_end" and e["id"] in starts:
            out[starts[e["id"]]].update(chars=len(e["output"]), ok=e["ok"], end=t)
    return out


# ---------------------------------------------------------------- live: recorded once

def live(only=None):
    key()
    out = json.loads(RUNS.read_text()) if RUNS.exists() else {}
    out.update({"model": model.model_id(MODEL), "date": time.strftime("%Y-%m-%d"), "version": ui.__version__,
                "pricing": pricing(), "python": sys.version.split()[0]})
    REC.mkdir(exist_ok=True)
    want = lambda name: not only or name in only

    def keep(name, shown, **extra):
        calls = recorded_calls(REC / f"{name}.jsonl", shown["events"])
        out[name] = {**shown, **extra, "calls": calls, "tool_calls": tool_calls(shown["events"])}
        print(f"\n[{name}: ${shown['cost']:.4f}, {len(calls)} requests, {shown['seconds']} s]\n")

    for name, first in (("alone", BIG), ("helper", BIG_HELPER)):
        if want(name):
            (REC / f"{name}.jsonl").unlink(missing_ok=True)
            with project():
                keep(name, screen_session([first, FOLLOW], record_to=str(REC / f"{name}.jsonl")), tasks=[first, FOLLOW])
    for name, task in (("small_alone", SMALL), ("small_helper", SMALL_HELPER)):
        if want(name):
            (REC / f"{name}.jsonl").unlink(missing_ok=True)
            with shop():
                keep(name, screen_session([task], record_to=str(REC / f"{name}.jsonl")), tasks=[task])
    if want("skill"):
        (REC / "skill.jsonl").unlink(missing_ok=True)
        with shop() as work:
            shown = screen_session([COCOA], lambda n: "2" if n in ("Edit", "Write") else "1",
                                   record_to=str(REC / "skill.jsonl"))
            tests = subprocess.run([sys.executable, "test_shop.py"], capture_output=True, text=True, cwd=work)
            keep("skill", shown, tasks=[COCOA], shop_after=(work / "shop.py").read_text(),
                 tests_after=(tests.stdout + tests.stderr).strip().splitlines()[-1:])
    if want("no_skill"):
        (REC / "no_skill.jsonl").unlink(missing_ok=True)
        with shop():
            keep("no_skill", screen_session([WHAT], record_to=str(REC / "no_skill.jsonl")), tasks=[WHAT])
    if want("review"):
        (REC / "review.jsonl").unlink(missing_ok=True)
        with shop():
            keep("review", screen_session(["/review shop.py"], record_to=str(REC / "review.jsonl")),
                 tasks=["/review shop.py"])
    if want("notes"):
        (REC / "notes.jsonl").unlink(missing_ok=True)
        with shop(with_mcp=True) as work:
            shown = screen_session([NOTE, "/mcp"], record_to=str(REC / "notes.jsonl"))
            notes = work / "notes.json"
            keep("notes", shown, tasks=[NOTE, "/mcp"], notes_after=json.loads(notes.read_text()) if notes.exists() else None)

    for run in out.values():                       # the messages are big and live in the recordings
        if isinstance(run, dict):
            run.pop("messages", None)
    RUNS.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    total = sum(r["cost"] for r in out.values() if isinstance(r, dict) and "cost" in r)
    print(f"recorded, about ${total:.4f} in all -> {RUNS}")


def pricing():
    """The model's price list, from OpenRouter, in dollars per million tokens."""
    import httpx
    for m in httpx.get("https://openrouter.ai/api/v1/models", timeout=30).json()["data"]:
        if m["id"] == model.model_id(MODEL):
            p = m["pricing"]
            return {k: round(float(p[k]) * 1e6, 4) for k in ("prompt", "completion", "input_cache_read", "input_cache_write")
                    if k in p} | {"context_length": m.get("context_length")}
    return {}


# ---------------------------------------------------------------- demos: free

def wire(config, steps):
    """Every line between Cato and one MCP server: what Cato sent (->) and what came back (<-)."""
    lines, real_send, real_read = [], mcp.send, mcp.read_message

    def send(server, message):
        lines.append(["->", message])
        real_send(server, message)

    def read(server, wait=mcp.WAIT):
        message = real_read(server, wait)
        lines.append(["<-", message])
        return message

    mcp.send, mcp.read_message = send, read
    try:
        server = mcp.start_server("notes", config)
        found = mcp.server_tools(server)
        results = []
        for name, arguments in steps:
            results.append(tools.run_tool(f"mcp__notes__{name}", json.dumps(arguments), found))
        mcp.stop_servers([server])
    finally:
        mcp.send, mcp.read_message = real_send, real_read
    return {"lines": lines, "version": server["version"], "results": results,
            "tools": [t.name for t in found], "exit_code": server["process"].returncode}


def demos():
    out = {}
    with shop(with_mcp=True) as work:
        notes = {"command": sys.executable, "args": ["mcp/notes_server.py"]}
        out["wire"] = wire(notes, [("add_note", {"text": "buy milk"}), ("list_notes", {}),
                                   ("add_note", {})])
        shutil.copy(HERE / "legacy_server.py", work / "legacy_server.py")
        out["wire_legacy"] = wire({"command": sys.executable, "args": ["legacy_server.py"]}, [])

        # the cards, as files and as what Cato reads from them
        out["cards"] = {}
        for rel in (".cato/agents/reviewer.md", ".cato/skills/add-product/SKILL.md", ".cato/commands/review.md"):
            header, body = cards.read_card(work / rel)
            out["cards"][rel] = {"text": (work / rel).read_text(), "header": header, "body": body}
        out["fill"] = cards.fill(cards.find_cards("commands")["review"]["body"], "shop.py")
        out["files_text"] = {rel: (work / rel).read_text() for rel in
                             (".cato/skills/add-product/check_prices.py", ".mcp.json")}
        out["menu"] = cards.skill_menu()
        out["reminder"] = context.reminders()

        # what each piece costs on the desk, by the rough count
        session = {"model": MODEL, "settings": {"mode": "default", "allow": [], "ask": [], "deny": [], "hooks": {}}}
        session["mcp_servers"], session["mcp_tools"], session["mcp_problems"] = mcp.load_servers()
        try:
            extra = helpers.helper_tools(MODEL, session["settings"], None)
            forms = {t.name: context.estimate_tokens(tools.tool_schemas([t])) for t in
                     tools.TOOLS + extra + session["mcp_tools"]}
            out["agent_form"] = tools.tool_schemas(extra[:1])[0]
            out["mcp_forms"] = tools.tool_schemas(session["mcp_tools"])
        finally:
            mcp.stop_servers(session["mcp_servers"])
        card = cards.find_cards("skills")["add-product"]
        out["desk"] = {"forms": forms, "menu": context.estimate_tokens(cards.skill_menu()),
                       "menu_line": context.estimate_tokens(cards.skill_menu().splitlines()[-1]),
                       "card": context.estimate_tokens(card["body"]),
                       "script": context.estimate_tokens((work / ".cato/skills/add-product/check_prices.py").read_text()),
                       "system": context.estimate_tokens(context.system_prompt())}
        out["helpers"] = {name: {k: v for k, v in c.items() if k != "path"} for name, c in helpers.all_helpers().items()}

    out["files"] = {"part5": file_graph(sorted((PART5 / "cato").glob("*.py"))),
                    "part6": file_graph(sorted((PART6 / "cato").glob("*.py")))}

    # replays of the live sessions, through the real screen, for $0
    if RUNS.exists():
        runs = json.loads(RUNS.read_text())
        out["replay"] = {}
        edits = lambda n: "2" if n in ("Edit", "Write") else "1"
        jobs = {"alone": (project, [BIG, FOLLOW], None), "helper": (project, [BIG_HELPER, FOLLOW], None),
                "helper_long": (project, [BIG_HELPER, FOLLOW], None), "small_alone": (shop, [SMALL], None),
                "small_helper": (shop, [SMALL_HELPER], None), "skill": (shop, [COCOA], edits),
                "no_skill": (shop, [WHAT], None), "review": (shop, ["/review shop.py"], None),
                "notes": (lambda: shop(with_mcp=True), [NOTE, "/mcp"], None)}
        for name, (where, tasks, policy) in jobs.items():
            if name in runs and (REC / f"{name}.jsonl").exists():
                with where():
                    shown = screen_session(tasks, policy or (lambda n: "1"), replay_from=str(REC / f"{name}.jsonl"))
                out["replay"][name] = {"text": shown["text"], "html": shown["html"], "cost": shown["cost"]}
    DEMOS.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"wrote {DEMOS}")


def file_graph(files):
    """Every file of one part of Cato: its functions and classes, and what it imports from the others."""
    import ast
    out = {}
    for f in files:
        if f.name == "__init__.py":
            continue
        tree = ast.parse(f.read_text())
        defs = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        imports = sorted({n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level == 1 and n.module})
        out[f.name] = {"defs": defs, "imports": [m + ".py" for m in imports]}
    return out


# ---------------------------------------------------------------- export: what the slides use

COLOR_CLASS = {"#00dffe": "k-cyan", "#7a7f86": "k-dim", "#ffb848": "k-yel", "#a7c9ff": "k-blue",
               "#ff6670": "k-red", "#45e891": "k-green", "#e8edf5": "k-ink", "#d98cff": "k-mag"}


def classed(html):
    def swap(m):
        style, classes = m.group(1), []
        color = re.search(r"(?<![-\w])color: (#[0-9a-f]{6})", style)
        if color:
            classes.append(COLOR_CLASS.get(color.group(1), "k-ink"))
        if "font-weight: bold" in style:
            classes.append("b")
        return f'<span class="{" ".join(classes)}">'
    return re.sub(r'<span style="([^"]*)">', swap, html)


def summary(run):
    """The numbers a slide needs from one session."""
    calls = run["calls"]
    main = [c for c in calls if c["who"] == "main"]
    side = [c for c in calls if c["who"] == "helper"]
    events = []
    for t, e in run["events"]:
        e = dict(e)
        if e["type"] == "text":
            continue
        if e["type"] == "usage":
            u = e.pop("usage")
            e.update(tokens_in=u.get("prompt_tokens", 0), cost=u.get("cost", 0))
        if e["type"] == "tool_end":
            e["output"] = e["output"][:400]
        events.append([t, e])
    answers = [e["text"] for _, e in run["events"] if e["type"] == "done" and e.get("who", "main") == "main"]
    inputs = [t for t, e in run["events"] if e["type"] == "input"]
    usage_t = [t for t, e in run["events"] if e["type"] == "usage"]
    per_task = [sum(1 for t in usage_t if a <= t < b) for a, b in zip(inputs, inputs[1:] + [1e9])]
    tools_per_task = [sum(1 for c in run["tool_calls"] if a <= c["t"] < b and c["who"] == "main")
                      for a, b in zip(inputs, inputs[1:] + [1e9])]
    reports = [e["output"] for _, e in run["events"] if e["type"] == "tool_end" and e["name"] == "Agent"]
    return {"tasks": run.get("tasks"), "seconds": run["seconds"], "cost": round(run["cost"], 4),
            "requests": len(calls), "main_requests": len(main), "helper_requests": len(side),
            "main_desk": [c["in"] for c in main], "helper_desk": [c["in"] for c in side],
            "read_total": sum(c["in"] for c in calls), "cached_total": sum(c["cached"] for c in calls),
            "main_cost": round(sum(c["cost"] for c in main), 4), "helper_cost": round(sum(c["cost"] for c in side), 4),
            "calls": calls, "tool_calls": run["tool_calls"], "asked": run["asked"], "answers": answers,
            "per_task": per_task, "main_tools_per_task": tools_per_task,
            "report_words": [len(r.split()) for r in reports], "report_chars": [len(r) for r in reports],
            "events": events, "text": run["text"], "html": classed(run["html"])}


def full_reports(name, calls):
    """Each helper's whole final report, from the recording: its last request before the main loop goes on."""
    path = REC / f"{name}.jsonl"
    if not path.exists():
        return []
    lines, out = path.read_text().splitlines(), []
    for k, c in enumerate(calls):
        if c["who"] == "helper" and (k + 1 == len(calls) or calls[k + 1]["who"] == "main"):
            pieces = json.loads(lines[k])
            text = "".join(((p.get("choices") or [{}])[0].get("delta") or {}).get("content") or "" for p in pieces)
            out.append({"words": len(text.split()), "chars": len(text)})
    return out


def export():
    runs = json.loads(RUNS.read_text()) if RUNS.exists() else {}
    demos_ = json.loads(DEMOS.read_text()) if DEMOS.exists() else {}
    data = {k: runs.get(k) for k in ("model", "date", "version", "pricing", "python")}
    for name in ("alone", "helper_long", "helper", "small_alone", "small_helper", "skill", "no_skill", "review", "notes"):
        if name in runs:
            data[name] = summary(runs[name])
            data[name]["full_reports"] = full_reports(name, runs[name]["calls"])
            for k in ("shop_after", "tests_after", "notes_after", "card_body", "note"):
                if k in runs[name]:
                    data[name][k] = runs[name][k]
    replay = demos_.pop("replay", {})
    for name, r in replay.items():                  # the slides show the replayed screen (same text, fixed times)
        if name in data:
            data[name]["html"] = classed(r["html"])
    data["demos"] = demos_
    DATA_JS.parent.mkdir(exist_ok=True)
    if DATA_JS.suffix == ".json":
        DATA_JS.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    else:
        DATA_JS.write_text("/* Written by code/record_part6.py from code/runs.json and code/demos.json. Don't edit. */\n"
                           "window.DATA = " + json.dumps(data, indent=1, ensure_ascii=False) + ";\n")
    print(f"wrote {DATA_JS}")


if __name__ == "__main__":
    if "--live" in sys.argv:
        only = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--only=")]
        live(only[0].split(",") if only else None)
    if "--demos" in sys.argv:
        demos()
    export()
