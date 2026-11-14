"""Record every real number, stream and screen shown in Part 3, then freeze it.

    python record_part3.py --live     # calls OpenRouter (a few cents): two real Cato v0.3 sessions -> runs.json
    python record_part3.py --live-explain   # only re-record the first session (the streamed answer)
    python record_part3.py --live-v02       # only re-record Cato v0.2 answering the same question
    python record_part3.py --demos    # no API calls: replays those sessions through Cato's real code -> demos.json
    python record_part3.py            # just rebuild ../assets/data.js from runs.json + demos.json
                                      # (in the public philoai_codes folder: numbers.json)

Run it with a Python that has httpx, rich, prompt_toolkit and pytest (the series uses ~/.cache/cato-venv).

What it records:
  runs.json   (recorded once, then frozen)
    - "explain": Cato v0.3 (cato/parts/part3, unchanged) answers a question about the tiny shop. Every line of
      the stream is kept with the time it arrived, so the slides can replay it at its real speed.
    - "v02_wait": the exact same request, sent once more the Part 2 way (no streaming), to time the blank wait.
    - "fix": Cato v0.3 fixes the shop's bug in a fresh session, saved with --record so it can be replayed for free.
    - "pairing": a chat whose tool request has no answer, sent as is (the API refuses) and after repair() (it works).
  demos.json  (free, repeatable: everything here replays the "fix" recording through Cato's real code)
    - the same session replayed: same screen, $0
    - headless mode: cato -p ... --json
    - the cost limit: --max-cost stops the loop
    - Ctrl+C at the permission question, and the chat repair() leaves behind
    - Ctrl+C in Cato v0.2 (cato/parts/part2), for comparison
"""
import argparse
import contextlib
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
SERIES = HERE.parents[1]
PART3 = SERIES / "cato" / "parts" / "part3"
PART2 = SERIES / "cato" / "parts" / "part2"
PLAYGROUND = SERIES / "cato" / "examples" / "playground"
RUNS, DEMOS = HERE / "runs.json", HERE / "demos.json"
REC = HERE / "recordings"               # --record files: the raw answers, replayable
DATA_JS = HERE.parent / "assets" / "data.js"
PART1_FILES = sorted((SERIES / "cato" / "parts" / "part1").glob("*.py"))
if (HERE / "cato" / "ui.py").exists():        # the public philoai_codes folder: everything sits side by side
    PART3, PART2, PLAYGROUND = HERE, HERE.parent / "part2-tools", HERE / "shop"
    PART1_FILES = [HERE.parent / "part1-agent-loop" / "cato.py"]
    DATA_JS = HERE / "numbers.json"
MODEL = "sonnet"                        # anthropic/claude-sonnet-5.5, the model of Parts 1 and 2
EXPLAIN = ("Without using any tools, explain how a coding agent like you works, for a new teammate. "
           "Use a short heading and a few bullet points.")
FIX = "The tests in test_shop.py fail. Find the bug and fix it."

sys.path.insert(0, str(PART3))
from cato import agent, model, tools, ui  # noqa: E402  (cato/parts/part3, unchanged)

ui.console.width = 100                  # the width of the recorded screen, in characters
WORK = Path("/tmp/shop")                # one fixed, short folder: the screen needs no editing, and a replay finds the same files
MARK = ".made-by-record_part3"          # we only ever delete a /tmp/shop that this script made

os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]


@contextlib.contextmanager
def project(files=("shop.py", "test_shop.py")):
    """A fresh copy of the tiny shop in a temporary folder; Cato works in it."""
    if WORK.exists():
        if not (WORK / MARK).exists():
            sys.exit(f"{WORK} exists and wasn't made by this script; move it away first.")
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    (WORK / MARK).write_text("")
    work = WORK.resolve()
    for name in files:
        shutil.copy(PLAYGROUND / name, work / name)
    old = os.getcwd()
    os.chdir(work)
    tools.files_read.clear()
    try:
        yield work
    finally:
        os.chdir(old)
        shutil.rmtree(WORK, ignore_errors=True)


def tidy(text, work):
    """Nothing to tidy: the folder is always /tmp/shop (macOS shows it as /private/tmp/shop)."""
    return text


def key():
    keyfile = SERIES.parents[1] / "openrouter.txt"
    if "OPENROUTER_API_KEY" not in os.environ and keyfile.exists():
        for word in keyfile.read_text().split():
            if word.startswith("sk-or-"):
                os.environ["OPENROUTER_API_KEY"] = word


# ---------------------------------------------------------------- timing the stream, without changing Cato

streams = []                 # one entry per model call: the request, and every line with its arrival time
real_stream = httpx.stream


@contextlib.contextmanager
def timed_stream(method, url, **kwargs):
    start = time.perf_counter()
    entry = {"request": copy.deepcopy(kwargs.get("json")), "lines": [], "t0": start}
    streams.append(entry)
    with real_stream(method, url, **kwargs) as response:
        lines = response.iter_lines

        def iter_lines():
            for line in lines():
                entry["lines"].append([round(time.perf_counter() - start, 3), line])
                yield line
        response.iter_lines = iter_lines
        yield response


def timed_events(log, start):
    """Wrap the loop the screen listens to, and note when each event came out."""
    run = agent.run_agent

    def run_agent(*args, **kwargs):
        for event in run(*args, **kwargs):
            log.append([round(time.perf_counter() - start, 3), event])
            yield event
    return run_agent


def screen_session(tasks, record_to=None, replay_from=None, interrupt_at_ask=False, max_cost=None):
    """Run Cato's real screen (ui.repl) on the tasks, answering y to every question. Returns what it showed."""
    ui.console.export_text(clear=True)          # start this screen empty
    model.record_file, model.replay_file, model._recorded = record_to, replay_from, None
    model.replay_delay = 0
    queue, log, start = list(tasks), [], time.perf_counter()

    def read_line(session, prompt_text):
        if "Allow?" in prompt_text:
            if interrupt_at_ask:
                ui.console.print(f"{prompt_text}^C")
                raise KeyboardInterrupt
            ui.console.print(f"{prompt_text}y")
            return "y"
        if not queue:
            raise EOFError
        line = queue.pop(0)
        ui.console.print(f"{prompt_text}{line}")
        return line

    saved = ui.read_line, ui.run_agent
    ui.read_line, ui.run_agent = read_line, timed_events(log, start)
    sessions = []
    real_answer = ui.answer

    def answer(session, task):
        sessions.append(session)
        return real_answer(session, task)
    ui.answer = answer
    try:
        ui.repl(argparse.Namespace(model=MODEL, max_turns=agent.MAX_TURNS, max_cost=max_cost,
                                   inputs=os.devnull, svg=None))
    finally:
        ui.read_line, ui.run_agent, ui.answer = saved[0], saved[1], real_answer
        model.record_file = model.replay_file = None
    text = ui.console.export_text(clear=False)
    html = ui.console.export_html(theme=ui.PHILO_THEME, inline_styles=True, clear=True, code_format="{code}")
    session = sessions[-1] if sessions else {}
    return {"seconds": round(time.perf_counter() - start, 2), "text": text, "html": html, "events": log,
            "messages": session.get("messages", []), "cost": session.get("cost", 0),
            "tokens": session.get("tokens", 0)}


# ---------------------------------------------------------------- live: recorded once

def post(body):
    start = time.perf_counter()
    response = httpx.post(model.API_URL, json=body, timeout=300,
                          headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"})
    return response, round(time.perf_counter() - start, 2)


def live(only_explain=False):
    key()
    httpx.stream = timed_stream
    out = {"model": model.model_id(MODEL), "date": time.strftime("%Y-%m-%d"), "version": ui.__version__}
    if only_explain:
        out = json.loads(RUNS.read_text())
    REC.mkdir(exist_ok=True)

    # 1. a question with a long answer, streamed
    with project() as work:
        first = len(streams)
        shown = screen_session([EXPLAIN], record_to=str(REC / "explain.jsonl"))
        spread = streams[-1]["lines"][-1][0] - next(t for t, l in streams[-1]["lines"] if '"content":"' in l)
        print(f"\n[the last answer's words arrived over {spread:.2f} s]")
        out["explain"] = json.loads(tidy(json.dumps({**shown, "task": EXPLAIN, "calls": strip(streams[first:])}), work))
        # 2. the very same last request, sent the Part 2 way: no streaming, so nothing to show until it's done
        body = dict(streams[-1]["request"])
        body.pop("stream", None)
        response, seconds = post(body)
        data = response.json()
        out["v02_wait"] = {"seconds": seconds, "status": response.status_code,
                           "chars": len((data["choices"][0]["message"].get("content") or "")),
                           "usage": data.get("usage", {})}

    if only_explain:
        RUNS.write_text(json.dumps(out, indent=1, ensure_ascii=False))
        print(f"\nrecorded the explain session -> {RUNS}")
        return

    # 3. the bug fix, in a fresh session, recorded so the demos can replay it for free
    (REC / "fix.jsonl").unlink(missing_ok=True)
    with project() as work:
        first = len(streams)
        shown = screen_session([FIX], record_to=str(REC / "fix.jsonl"))
        tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                               capture_output=True, text=True, cwd=work)
        shown["tests_after"] = re.sub(r" in [\d.]+s$", "", tests.stdout.strip().splitlines()[-1])
        shown["shop_after"] = (work / "shop.py").read_text()
        out["fix"] = json.loads(tidy(json.dumps({**shown, "task": FIX, "calls": strip(streams[first:])}), work))

        # 4. the pairing rule: a tool request with no answer, then the same chat after repair()
        msgs = out["fix"]["messages"]
        cut = next(i for i, m in enumerate(msgs) if m.get("tool_calls"))
        broken = copy.deepcopy(msgs[:cut + 1]) + [{"role": "user", "content": "Stop. What does shop.py do?"}]
        body = {"model": model.model_id(MODEL), "messages": broken, "max_tokens": 60}
        response, _ = post(body)
        fixed = copy.deepcopy(msgs[:cut + 1])
        agent.repair(fixed)
        fixed.append({"role": "user", "content": "Stop. What does shop.py do?"})
        response2, _ = post(dict(body, messages=fixed))
        response3, _ = post(dict(body, model=model.model_id("terra")))      # the same broken chat, another API
        out["pairing"] = {"calls": len(msgs[cut]["tool_calls"]), "broken_status": response.status_code,
                          "broken_error": response.text[:4000], "fixed_status": response2.status_code,
                          "fixed_cost": response2.json().get("usage", {}).get("cost", 0),
                          "repair_added": fixed[cut + 1:-1],
                          "terra_status": response3.status_code, "terra_error": response3.text[:4000]}
    RUNS.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    total = sum(c["usage"].get("cost", 0) for k in ("explain", "fix") for c in out[k]["calls"])
    total += out["v02_wait"]["usage"].get("cost", 0) + out["pairing"]["fixed_cost"]
    print(f"\nrecorded, about ${total:.4f} -> {RUNS}")


V02_RUN = r"""
import io, json, sys, time
sys.path.insert(0, sys.argv[1])
from cato import __version__, agent
start, out = time.perf_counter(), []
class Clock(io.TextIOBase):
    def write(self, text):
        if text:
            out.append([round(time.perf_counter() - start, 3), text])
        return len(text)
messages = [{"role": "system", "content": agent.system_prompt()}, {"role": "user", "content": sys.argv[2]}]
real, sys.stdout = sys.stdout, Clock()
print(f"Cato v{__version__} · sonnet · type a task, or 'exit'")
print(f"\n> {sys.argv[2]}")
start = time.perf_counter()
print(agent.agent_loop(messages, "sonnet"))
sys.stdout = real
print(json.dumps({"printed": out, "seconds": round(time.perf_counter() - start, 2)}))
"""


def live_v02():
    """Cato v0.2 (cato/parts/part2, unchanged) gets the same question: what it prints, and when."""
    key()
    out = json.loads(RUNS.read_text())
    with project() as work:
        r = subprocess.run([sys.executable, "-c", V02_RUN, str(PART2), EXPLAIN], capture_output=True, text=True, cwd=work)
        out["v02_screen"] = json.loads(r.stdout.strip().splitlines()[-1])
    RUNS.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"recorded v0.2's screen -> {RUNS}")


def strip(calls):
    """Keep each call's lines, timings and usage; the request is kept only as its size."""
    out = []
    for c in calls:
        usage = {}
        for _, line in c["lines"]:
            if line.startswith("data:") and line[5:].strip() not in ("", "[DONE]"):
                usage = json.loads(line[5:]).get("usage") or usage
        times = [t for t, line in c["lines"] if '"content":"' in line and '"content":""' not in line]
        out.append({"lines": c["lines"], "usage": usage, "messages_sent": len(c["request"]["messages"]),
                    "first_line": c["lines"][0][0] if c["lines"] else None,
                    "first_text": times[0] if times else None, "last_line": c["lines"][-1][0] if c["lines"] else None})
    return out


# ---------------------------------------------------------------- demos: free, from the recording

def demos():
    out = {}
    fix = REC / "fix.jsonl"
    with project() as work:            # the same session, replayed through the real screen
        shown = screen_session([FIX], replay_from=str(fix))
        out["replay"] = json.loads(tidy(json.dumps({"text": shown["text"], "cost": shown["cost"]}), work))
    for name, extra in (("headless_json", []), ("cost_limit", ["--max-cost", "0.01"])):
        with project() as work:        # headless mode: the same loop, another listener (no key needed to replay)
            r = subprocess.run([sys.executable, "-m", "cato", "-p", FIX, "--replay", str(fix), "--yes", "--json", *extra],
                               capture_output=True, text=True, cwd=work,
                               env=dict(os.environ, PYTHONPATH=str(PART3), OPENROUTER_API_KEY="x"))
            out[name] = json.loads(r.stdout)
    out["headless_command"] = f'cato -p "{FIX}" --json --yes'
    with project() as work:            # Ctrl+C at the permission question
        shown = screen_session([FIX], replay_from=str(fix), interrupt_at_ask=True)
        msgs = shown["messages"]
        out["ctrl_c"] = json.loads(tidy(json.dumps({"text": shown["text"], "html": shown["html"], "last": msgs[-2:],
                                                    "roles": [m["role"] for m in msgs]}), work))
    # the slash commands, as the real screen prints them (after the fix: its tokens and cost)
    ui.console.export_text(clear=True)
    session = {"model": MODEL, "messages": [{"role": "system", "content": "…"}], "cost": shown_fix_cost(),
               "tokens": json.loads(RUNS.read_text())["fix"]["tokens"]}
    for line in ("/help", "/model", "/cost"):
        ui.console.print(f"[yellow]>[/] {line}")
        ui.run_command(session, line)
        ui.console.print()
    out["commands_html"] = ui.console.export_html(theme=ui.PHILO_THEME, inline_styles=True, clear=True, code_format="{code}")
    out["ctrl_c_v02"] = ctrl_c_v02()
    out["generator"] = generator_demo()
    out["codes"] = terminal_codes()
    out["stack_v03"] = ctrl_c_stack()
    out["files"] = {"part1": file_graph(PART1_FILES), "part2": file_graph(sorted((PART2 / "cato").glob("*.py"))),
                    "part3": file_graph(sorted((PART3 / "cato").glob("*.py")))}
    DEMOS.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"wrote {DEMOS}")


def shown_fix_cost():
    return json.loads(RUNS.read_text())["fix"]["cost"]


def terminal_codes():
    """The bytes rich really sends: a spinner, and a Live area redrawn with a growing answer."""
    import io
    from rich.console import Console
    from rich.live import Live
    from rich.markdown import Markdown
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=40, color_system=None)
    live = Live(console=console, auto_refresh=False, vertical_overflow="visible")
    live.start()
    frames = []
    for text in ["- **The lo", "- **The loop:** You give me a task"]:
        start = len(buf.getvalue())
        live.update(Markdown(text), refresh=True)
        frames.append({"markdown": text, "bytes": buf.getvalue()[start:]})
    live.stop()
    buf2 = io.StringIO()
    status = Console(file=buf2, force_terminal=True, width=40, color_system=None).status("Thinking…", spinner="dots")
    status.start()
    time.sleep(0.25)
    status.stop()
    from rich._spinners import SPINNERS
    return {"live": frames, "spinner": buf2.getvalue(), "spinner_frames": SPINNERS["dots"]["frames"],
            "spinner_ms": SPINNERS["dots"]["interval"], "status_fps": 12.5, "live_fps": 12}


def ctrl_c_stack():
    """Press Ctrl+C while the answer streams in: which functions is Cato inside, and who catches it?"""
    import traceback
    seen = {}

    def pieces_then_ctrl_c():
        seen["stack"] = [f.name for f in traceback.extract_stack()]
        raise KeyboardInterrupt
        yield  # a generator, like the real one
    with project():
        saved = model.replayed_pieces
        model.replayed_pieces, model.replay_file = pieces_then_ctrl_c, os.devnull
        ui.console.export_text(clear=True)
        queue = [FIX]
        real_read = ui.read_line
        ui.read_line = lambda session, prompt: queue.pop(0) if queue else (_ for _ in ()).throw(EOFError())
        try:
            ui.repl(argparse.Namespace(model=MODEL, max_turns=agent.MAX_TURNS, max_cost=None, inputs=os.devnull, svg=None))
        finally:
            model.replayed_pieces, model.replay_file, ui.read_line = saved, None, real_read
        shown = ui.console.export_text(clear=True)
    stack = seen["stack"]
    return {"stack": stack[stack.index("repl"):], "screen": shown}


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


V02_CTRL_C = r"""
import sys
sys.path.insert(0, sys.argv[1])
from cato import agent
def model_is_thinking(*args, **kwargs):
    raise KeyboardInterrupt        # you press Ctrl+C while the model is still thinking
agent.ask_model = model_is_thinking
sys.argv = ["cato", "--model", "sonnet"]
from cato.__main__ import main
main()
"""


def ctrl_c_v02():
    with project() as work:
        r = subprocess.run([sys.executable, "-c", V02_CTRL_C, str(PART2)], input="Explain this project.\n",
                           capture_output=True, text=True, cwd=work, env=dict(os.environ, OPENROUTER_API_KEY="x"))
        text = r.stdout + r.stderr
        text = text.replace(f'File "{PART2}/', 'File "')
        text = re.sub(r'File "[^"]*/(python[\d.]*/)?', 'File "', text)
        return {"text": tidy(text, work), "exit": r.returncode}


GENERATOR = '''def count_to(n):
    for i in range(1, n + 1):
        yield i            # hand out one value, then wait here

for number in count_to(3):
    print("got", number)'''


def generator_demo():
    out = io_capture(GENERATOR)
    return {"code": GENERATOR, "output": out}


def io_capture(code):
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(code, {})
    return buf.getvalue().rstrip("\n")


# ---------------------------------------------------------------- export: the small numbers the slides use

# rich's HTML export writes the theme's colours inline; the slides use palette classes instead
COLOR_CLASS = {"#00dffe": "k-cyan", "#7a7f86": "k-dim", "#ffb848": "k-yel", "#a7c9ff": "k-blue",
               "#ff6670": "k-red", "#45e891": "k-green", "#e8edf5": "k-ink"}


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


FRAME_WIDTH = 56          # columns of the narrow screens in the cold open


def live_frames(pieces, width, fps=12):
    """What Cato's screen draws while the answer streams in: rich redraws the Markdown so far, 12 times a second."""
    from rich.console import Console
    from rich.markdown import Markdown
    frames, start, end = [], pieces[0][0], pieces[-1][0]
    k = 0
    while True:
        t = round(start + k / fps, 3)
        text = "".join(p for when, p in pieces if when <= t)
        console = Console(width=width, record=True, file=open(os.devnull, "w"), color_system="truecolor")
        console.print(Markdown(text))
        frames.append([t, classed(console.export_html(theme=ui.PHILO_THEME, inline_styles=True, code_format="{code}"))])
        if t >= end:
            return frames
        k += 1


def data_lines(lines):
    for t, line in lines:
        if line.startswith("data:") and line[5:].strip() not in ("", "[DONE]"):
            yield t, json.loads(line[5:])


def export():
    runs = json.loads(RUNS.read_text())
    demos_ = json.loads(DEMOS.read_text()) if DEMOS.exists() else {}
    for key in ("commands_html",):
        if key in demos_:
            demos_[key] = classed(demos_[key])
    if "ctrl_c" in demos_ and "html" in demos_["ctrl_c"]:
        demos_["ctrl_c"]["html"] = classed(demos_["ctrl_c"]["html"])
    data = {"model": runs["model"], "date": runs["date"], "version": runs["version"], "demos": demos_}
    same = lambda text: re.sub(r" in [\d.]+s\b", " in …s", text or "")       # pytest times its own run
    data["replay_identical"] = same(demos_.get("replay", {}).get("text")) == same(runs["fix"]["text"])
    for name in ("explain", "fix"):
        run = runs[name]
        calls = [{"first_line": c["first_line"], "first_text": c["first_text"], "last_line": c["last_line"],
                  "in": c["usage"].get("prompt_tokens", 0), "out": c["usage"].get("completion_tokens", 0),
                  "cost": c["usage"].get("cost", 0), "pieces": sum(1 for _ in data_lines(c["lines"]))}
                 for c in run["calls"]]
        events = []
        for t, e in run["events"]:
            e = dict(e)
            if e["type"] == "usage":
                u = e.pop("usage")
                e.update(tokens_in=u.get("prompt_tokens", 0), tokens_out=u.get("completion_tokens", 0), cost=u.get("cost", 0))
            if e["type"] == "tool_end":
                e["output"] = e["output"][:400]
            events.append([t, e])
        data[name] = {"task": run["task"], "seconds": run["seconds"], "cost": round(run["cost"], 4),
                      "tokens": run["tokens"], "text": run["text"], "html": classed(run["html"]),
                      "calls": calls, "events": events, "asked": run["text"].count("Allow?"),
                      "turns": len(calls)}
    # the streamed answer: every piece of text with the time it arrived, and a few raw lines exactly as sent
    last = runs["explain"]["calls"][-1]
    pieces = [[t, ch["delta"]["content"]] for t, d in data_lines(last["lines"])
              for ch in d.get("choices", []) if (ch.get("delta") or {}).get("content")]
    data["explain"].update(pieces=pieces, first_word=pieces[0][0], last_word=pieces[-1][0],
                           raw_head=[line for _, line in last["lines"][:6]],
                           raw_tail=[line for _, line in last["lines"][-5:]])
    data["v02_wait"] = {"seconds": runs["v02_wait"]["seconds"], "chars": runs["v02_wait"]["chars"]}
    v02 = runs["v02_screen"]
    data["v02"] = {"printed": v02["printed"], "seconds": v02["seconds"],
                   "first_output": next(t for t, text in v02["printed"] if t > 0)}
    data["sooner"] = round(data["v02"]["first_output"] / pieces[0][0], 1)
    meter = re.search(r"\[(\d+) tokens in, (\d+) out, \$([\d.]+)\]", "".join(text for _, text in v02["printed"]))
    data["v02"]["meter"] = f"{int(meter.group(1)):,} in · {meter.group(2)} out · ${meter.group(3)}"
    c = data["explain"]["calls"][-1]
    data["explain"]["meter"] = f"{c['in']:,} in · {c['out']} out · ${c['cost']:.4f}"
    data["explain"]["status"] = next(l.strip() for l in runs["explain"]["text"].splitlines() if "tokens on the desk" in l)
    data["explain"]["frames"] = live_frames(pieces, width=FRAME_WIDTH)
    # the first call of the fix: two tool calls, arriving in fragments
    frags = []
    for t, d in data_lines(runs["fix"]["calls"][0]["lines"]):
        for ch in d.get("choices", []):
            for tc in (ch.get("delta") or {}).get("tool_calls") or []:
                fn = tc.get("function") or {}
                frags.append({"t": t, "index": tc.get("index", 0), "id": tc.get("id") or "",
                              "name": fn.get("name") or "", "args": fn.get("arguments") or ""})
    data["fix"]["fragments"] = frags
    data["fix"]["tests_after"] = runs["fix"]["tests_after"]
    costs = [c["cost"] for c in data["fix"]["calls"]]
    data["fix"]["cumulative"] = [round(sum(costs[:k + 1]), 4) for k in range(len(costs))]
    # the pairing rule, two ways an API can react
    pr = runs["pairing"]
    # the saved answers are the first 600 characters of each reply, so read the two quotes out of the text
    thought = re.search(r'"reasoning":"((?:[^"\\]|\\.)*)', pr["broken_error"]).group(1)
    thought = json.loads('"' + thought.rstrip("\\") + '"').split("\n")[0]
    terra = re.search(r'message\\": \\"([^\\]*)', pr["terra_error"]).group(1)
    data["pairing"] = {"calls": pr["calls"], "quiet_status": pr["broken_status"],
                       "quiet_thought": thought,
                       "strict_status": pr["terra_status"], "strict_error": terra,
                       "fixed_status": pr["fixed_status"], "repair_added": pr["repair_added"]}
    DATA_JS.parent.mkdir(exist_ok=True)
    if DATA_JS.suffix == ".json":
        DATA_JS.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    else:
        DATA_JS.write_text("/* Written by code/record_part3.py from code/runs.json and code/demos.json. Don't edit. */\n"
                           "window.DATA = " + json.dumps(data, indent=1, ensure_ascii=False) + ";\n")
    print(f"wrote {DATA_JS}")


if __name__ == "__main__":
    if "--live" in sys.argv or "--live-explain" in sys.argv:
        live(only_explain="--live-explain" in sys.argv)
    if "--live" in sys.argv or "--live-v02" in sys.argv:
        live_v02()
    if "--demos" in sys.argv:
        demos()
    export()
