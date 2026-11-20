"""Record the one request Part 7 follows through every box, then freeze it.

    python record_part7.py --live     # calls OpenRouter once: a real Cato v0.6 session -> runs.json + recordings/
    python record_part7.py --trace    # no API calls: replay it and log every Cato function it passes -> trace.json
    python record_part7.py            # just rebuild ../assets/data.js from runs.json, trace.json and the test results
                                      # (in the public philoai_codes folder: numbers.json)

Run it with a Python 3.12+ that has httpx, rich and prompt_toolkit (the series uses ~/.cache/cato-venv).

What it records:
  runs.json   the request "Add a product called tea, for $3.50. Then run the tests." typed into Cato's real
              screen, in a fresh copy of the shop (its CATO.md, rules, hooks, helper card, skill and command).
              Every event with its time, every request the model got (what was on it, how big), the screen.
  trace.json  the same session replayed from its recording: every Cato function that started, in order,
              with its file, its first line, and the line that called it (sys.monitoring, PY_START).
              Replay runs the same code as the live run, except the network call itself.
  the test    ../../eval/results/*.jsonl (python run_eval.py), copied here as eval.jsonl when it's final.
"""
import argparse
import ast
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERIES = HERE.parents[1]
PART6 = SERIES / "cato" / "parts" / "part6"
PLAYGROUND = SERIES / "cato" / "examples" / "playground"
RUNS, TRACE, EVAL = HERE / "runs.json", HERE / "trace.json", HERE / "eval.jsonl"
REC = HERE / "recordings"
DATA_JS = HERE.parent / "assets" / "data.js"
if (HERE / "cato" / "mcp.py").exists():   # the public philoai_codes folder: everything sits side by side
    PART6, PLAYGROUND = HERE, HERE / "shop"
    DATA_JS = HERE / "numbers.json"
MODEL = "sonnet"                       # anthropic/claude-sonnet-5.5, the model of Parts 1-6
TASK = "Add a product called tea, for $3.50. Then run the tests."

os.environ["HOME"] = tempfile.mkdtemp(prefix="cato-home-")     # only the project's files count, not ~/.cato
os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]
sys.path.insert(0, str(PART6))
from cato import agent, context, helpers, model, tools, ui  # noqa: E402

ui.console.width = 100
WORK = Path("/tmp/shop")
MARK = ".made-by-record_part7"
SHOP = ["shop.py", "test_shop.py", ".env", "CATO.md", ".cato/settings.json",
        ".cato/hooks/protect_files.py", ".cato/hooks/check_python.py",
        ".cato/agents/reviewer.md", ".cato/commands/review.md",
        ".cato/skills/add-product/SKILL.md", ".cato/skills/add-product/check_prices.py"]
FIXED = ("total += PRICES[product]\n", "total += PRICES[product] * count\n")   # Part 4 fixed the bug


def shop():
    """A fresh copy of the playground in /tmp/shop, with Part 4's fix in place. Returns the folder."""
    if WORK.exists():
        if not (WORK / MARK).exists():
            sys.exit(f"{WORK} exists and wasn't made by this script; move it away first.")
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    (WORK / MARK).write_text("")
    for name in SHOP:
        dst = WORK / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(PLAYGROUND / name, dst)
    (WORK / "shop.py").write_text((WORK / "shop.py").read_text().replace(*FIXED))
    return WORK


def key():
    keyfile = SERIES.parents[1] / "openrouter.txt"
    if "OPENROUTER_API_KEY" not in os.environ and keyfile.exists():
        for word in keyfile.read_text().split():
            if word.startswith("sk-or-"):
                os.environ["OPENROUTER_API_KEY"] = word


def screen_session(tasks, record_to=None, replay_from=None):
    """Run Cato's real screen (ui.repl) on the tasks, saying yes (1) to every question.
    Logs every event with its time, every question, and the size of every request sent to the model."""
    ui.console.export_text(clear=True)
    model.record_file, model.replay_file, model._recorded = record_to, replay_from, None
    model.replay_delay = 0
    queue, log, asked, bodies, sessions = list(tasks), [], [], [], []
    start = time.perf_counter()
    real = {"read_line": ui.read_line, "run_agent": ui.run_agent, "ask": ui.ask_permission, "answer": ui.answer,
            "body": model.request_body}

    def ask_permission(session, screen, name, arguments, why):
        asked.append({"name": name, "arguments": arguments, "why": why})
        return real["ask"](session, screen, name, arguments, why)

    def read_line(session, prompt_text):
        if prompt_text.startswith("  "):                # a permission question
            if asked:
                asked[-1]["reply"] = "1"
            ui.console.print(f"{prompt_text}1")
            log.append([round(time.perf_counter() - start, 3), {"type": "reply", "text": "1"}])
            return "1"
        if not queue:
            raise EOFError
        line = queue.pop(0)
        ui.console.print(f"{prompt_text}{line}")
        log.append([round(time.perf_counter() - start, 3), {"type": "input", "text": line}])
        return line

    def run_agent(*args, **kwargs):
        for event in real["run_agent"](*args, **kwargs):
            log.append([round(time.perf_counter() - start, 3), event])
            yield event

    def answer(session, task):
        sessions.append(session)
        return real["answer"](session, task)

    def request_body(messages, schemas, model_name):
        body = real["body"](messages, schemas, model_name)
        bodies.append(describe_body(body))
        log.append([round(time.perf_counter() - start, 3), {"type": "request", "n": len(bodies)}])
        return body

    ui.read_line, ui.run_agent, ui.ask_permission, ui.answer = read_line, run_agent, ask_permission, answer
    model.request_body = request_body
    try:
        ui.repl(argparse.Namespace(model=MODEL, max_turns=agent.MAX_TURNS, max_cost=None, mode=None,
                                   desk_limit=None, inputs=os.devnull, svg=None))
    finally:
        ui.read_line, ui.run_agent, ui.ask_permission, ui.answer = (real["read_line"], real["run_agent"],
                                                                    real["ask"], real["answer"])
        model.request_body = real["body"]
        model.record_file = model.replay_file = None
    text = ui.console.export_text(clear=False)
    html = ui.console.export_html(theme=ui.PHILO_THEME, inline_styles=True, clear=True, code_format="{code}")
    session = sessions[-1] if sessions else {}
    return {"seconds": round(time.perf_counter() - start, 2), "text": text, "html": html, "events": log,
            "asked": asked, "bodies": bodies, "messages": session.get("messages", []),
            "cost": session.get("cost", 0), "tokens": session.get("tokens", 0)}


def describe_body(body):
    """What one request carries: the messages by role and size, the tool forms, the flags."""
    msgs = body.get("messages", [])
    as_text = lambda m: m["content"] if isinstance(m.get("content"), str) else json.dumps(m.get("content"))
    return {"model": body.get("model"), "stream": body.get("stream"),
            "messages": [{"role": m["role"], "chars": len(as_text(m) or "") + len(json.dumps(m.get("tool_calls") or "")),
                          "tools": [c["function"]["name"] for c in m.get("tool_calls") or []]} for m in msgs],
            "tools": [t["function"]["name"] for t in body.get("tools", [])],
            "tool_chars": len(json.dumps(body.get("tools", []))),
            "cache_marks": json.dumps(body).count("cache_control"),
            "keys": sorted(body)}


def recorded_calls(path):
    """Every request in a recording, in order, with its usage."""
    calls = []
    for line in Path(path).read_text().splitlines():
        usage = next((p["usage"] for p in reversed(json.loads(line)) if p.get("usage")), {})
        details = usage.get("prompt_tokens_details") or {}
        calls.append({"in": usage.get("prompt_tokens", 0), "out": usage.get("completion_tokens", 0),
                      "cached": details.get("cached_tokens", 0), "written": details.get("cache_write_tokens", 0),
                      "cost": usage.get("cost", 0)})
    return calls


def tool_calls(events):
    out, starts = [], {}
    for t, e in events:
        if e["type"] == "tool_start":
            starts[e["id"]] = len(out)
            out.append({"t": t, "name": e["name"], "view": agent.describe(e["name"], e["arguments"]),
                        "arguments": e["arguments"]})
        elif e["type"] == "tool_end" and e["id"] in starts:
            out[starts[e["id"]]].update(chars=len(e["output"]), ok=e["ok"], end=t, output=e["output"][:600])
    return out


def pricing():
    import httpx
    for m in httpx.get("https://openrouter.ai/api/v1/models", timeout=30).json()["data"]:
        if m["id"] == model.model_id(MODEL):
            p = m["pricing"]
            return {k: round(float(p[k]) * 1e6, 4) for k in ("prompt", "completion", "input_cache_read", "input_cache_write")
                    if k in p}
    return {}


# ---------------------------------------------------------------- live: recorded once

def live():
    key()
    REC.mkdir(exist_ok=True)
    rec = REC / "tea.jsonl"
    rec.unlink(missing_ok=True)
    work = shop()
    old = os.getcwd()
    os.chdir(work)
    tools.files_read.clear()
    try:
        shown = screen_session([TASK], record_to=str(rec))
        after = {"shop": (work / "shop.py").read_text(),
                 "tests": __import__("subprocess").run([sys.executable, "test_shop.py"], cwd=work,
                                                      capture_output=True, text=True).stdout}
    finally:
        os.chdir(old)
        shutil.rmtree(work, ignore_errors=True)
    run = {**shown, "task": TASK, "calls": recorded_calls(rec), "tool_calls": tool_calls(shown["events"]), "after": after}
    out = {"model": model.model_id(MODEL), "date": time.strftime("%Y-%m-%d"), "version": ui.__version__,
           "pricing": pricing(), "python": sys.version.split()[0], "tea": run}
    RUNS.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"\n[tea: ${run['cost']:.4f}, {len(run['calls'])} requests, {run['seconds']} s] -> {RUNS}")


# ---------------------------------------------------------------- trace: free

def trace():
    """Replay the live session and log every Cato function that starts (not a generator resuming)."""
    root = str((PART6 / "cato").resolve())
    calls, lock = [], threading.Lock()
    mon = sys.monitoring
    tool_id = mon.PROFILER_ID

    def started(code, offset):
        if not code.co_filename.startswith(root):
            return mon.DISABLE                       # stop asking about code outside Cato
        frame = sys._getframe(1)
        back = frame.f_back
        while back is not None and not back.f_code.co_filename.startswith(root):
            back = back.f_back                       # skip library frames (a thread pool, rich) in between
        with lock:
            calls.append({"n": len(calls), "file": Path(code.co_filename).name, "fn": code.co_qualname,
                          "line": code.co_firstlineno, "thread": threading.current_thread() is not threading.main_thread(),
                          "from": None if back is None else {"file": Path(back.f_code.co_filename).name,
                                                            "fn": back.f_code.co_qualname, "line": back.f_lineno}})

    work = shop()
    old = os.getcwd()
    os.chdir(work)
    tools.files_read.clear()
    mon.use_tool_id(tool_id, "record_part7")
    mon.register_callback(tool_id, mon.events.PY_START, started)
    mon.set_events(tool_id, mon.events.PY_START)
    try:
        shown = screen_session([TASK], replay_from=str(REC / "tea.jsonl"))
    finally:
        mon.set_events(tool_id, 0)
        mon.register_callback(tool_id, mon.events.PY_START, None)
        mon.free_tool_id(tool_id)
        os.chdir(old)
        shutil.rmtree(work, ignore_errors=True)
    files = sorted({c["file"] for c in calls})
    out = {"calls": calls, "files": files, "screen_text": shown["text"],
           "graph": file_graph(sorted((PART6 / "cato").glob("*.py")))}
    TRACE.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"trace: {len(calls)} function starts in {len(files)} files -> {TRACE}")


def file_graph(files):
    """Every file of Cato v0.6: its functions, and what it imports from the others."""
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


def latest_eval():
    """The test results: the frozen copy here, or else the newest run in ../../eval/results."""
    if EVAL.exists():
        path = EVAL
    else:
        found = sorted((SERIES / "eval" / "results").glob("*.jsonl"))
        if not found:
            return []
        path = found[-1]
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def request_sizes(rows):
    """Average tokens per request, per agent: what each harness sends the model every turn."""
    out = {}
    for agent_name in dict.fromkeys(r["agent"] for r in rows):
        mine = [r for r in rows if r["agent"] == agent_name and r.get("turns")]
        if agent_name == "claude":
            per = [sum(u.get(k, 0) for k in ("inputTokens", "cacheReadInputTokens", "cacheCreationInputTokens"))
                   / r["turns"] for r in mine for name, u in (r.get("model_usage") or {}).items() if "opus" in name]
        else:
            per = [r["tokens"] / r["turns"] for r in mine if r.get("tokens")]
        out[agent_name] = round(sum(per) / len(per)) if per else None
    return out


def growth():
    """For each file of Cato v0.6: in which part it appeared, and in which later parts it changed."""
    def part(n):        # this repo: cato/parts/partN; the public philoai_codes folder: ../partN-*/
        here = SERIES / "cato" / "parts" / f"part{n}"
        return here if here.exists() else next(iter(sorted(HERE.parent.glob(f"part{n}-*"))), here)
    if not (part(6) / "cato").exists():
        return {}
    files = sorted(f.name for f in (part(6) / "cato").glob("*.py") if f.name != "__init__.py")
    out = {}
    for name in files:
        row, before = [], None
        for n in range(1, 7):
            f = part(n) / "cato" / name
            text = f.read_text() if f.exists() else None
            if n == 1 and name in ("agent.py", "model.py", "tools.py", "__main__.py"):
                text = (part(1) / "cato.py").read_text()         # Part 1 is one file
                row.append("new"); before = None; continue
            row.append("none" if text is None else "new" if before is None and (not row or row[-1] == "none") else
                       "same" if text == before else "changed")
            before = text
        out[name] = row
    return out


def export():
    runs = json.loads(RUNS.read_text()) if RUNS.exists() else {}
    data = {k: runs.get(k) for k in ("model", "date", "version", "pricing", "python")}
    if "tea" in runs:
        tea = runs["tea"]
        data["tea"] = {k: tea[k] for k in ("task", "seconds", "cost", "tokens", "asked", "bodies", "calls",
                                           "tool_calls", "after")}
        data["tea"]["events"] = [[t, {k: v for k, v in e.items() if k in ("type", "name", "id", "reason", "turns", "how")}]
                                 for t, e in tea["events"] if e["type"] != "text"]
        data["tea"]["html"] = classed(tea["html"])
        data["tea"]["answer"] = next((e.get("text", "") for _, e in reversed(tea["events"]) if e["type"] == "done"), "")
        data["tea"]["status"] = next((l.strip() for l in reversed(tea["text"].splitlines()) if "tokens on the desk" in l), "")
    if TRACE.exists():
        tr = json.loads(TRACE.read_text())
        data["trace"] = {"calls": tr["calls"], "files": tr["files"], "graph": tr["graph"]}
    data["eval"] = latest_eval()
    data["eval_refusals"] = json.loads((HERE / "eval_refusals.json").read_text()) if (HERE / "eval_refusals.json").exists() else {}
    data["eval_sizes"] = request_sizes(data["eval"])
    data["growth"] = growth()
    runner = SERIES / "eval" / "run_eval.py"
    if not runner.exists():
        runner = HERE / "eval" / "run_eval.py"                   # the public folder
    m = re.search(r"COMMANDS = \[(.*?)\]", runner.read_text(), re.S) if runner.exists() else None
    data["eval_commands"] = re.findall(r'"([^"]+)"', m.group(1)) if m else []
    DATA_JS.parent.mkdir(exist_ok=True)
    if DATA_JS.suffix == ".json":
        DATA_JS.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    else:
        DATA_JS.write_text("/* Written by code/record_part7.py from code/runs.json, trace.json and the test. Don't edit. */\n"
                           "window.DATA = " + json.dumps(data, indent=1, ensure_ascii=False) + ";\n")
    print(f"wrote {DATA_JS}")


if __name__ == "__main__":
    if "--live" in sys.argv:
        live()
    if "--trace" in sys.argv:
        trace()
    export()
