"""Record every real number, screen and request shown in Part 5, then freeze it.

    python record_part5.py --live     # calls OpenRouter (about 55 cents): real Cato sessions -> runs.json
    python record_part5.py --demos    # no API calls: the desk, CATO.md, trimming, clearing, replays -> demos.json
    python record_part5.py            # just rebuild ../assets/data.js from runs.json + demos.json
                                      # (in the public philoai_codes folder: numbers.json)

Run it with a Python that has httpx, rich and prompt_toolkit (the series uses ~/.cache/cato-venv).

What it records:
  runs.json   (recorded once, then frozen; every session is saved with --record, so it replays for free)
    - "long":    Cato v0.5 traces a question through Python's own email package, then writes a test: a growing desk.
    - "squeeze": the same question with a small desk limit, so Cato has to clear its desk while it works.
    - "rules_v04" / "rules_v05": the same shop task for Cato v0.4 (no CATO.md) and v0.5 (reads CATO.md).
    - "compact": the email question, then /context, /compact, /context again, and a question about what came before.
    - "remember": "please remember this": Cato writes the note into CATO.md itself, then /memory.
    - "cache":   five tiny requests that show when the reread discount applies, and when it doesn't.
    - "pairs":   a chat with a tool request and its answer pulled apart, sent to two models: one API refuses,
                 the other patches the chat quietly and the model gets confused.
  demos.json  (free, repeatable)
    - the first page: the system prompt, the tool forms and CATO.md, measured
    - CATO.md files found folder by folder, and the reminder text
    - a big output saved to a file, old results cleared, the pairing rule checked
    - "about 4 characters per token" against the real counts
    - the map of which file calls which, for Parts 4 and 5
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
PART5 = SERIES / "cato" / "parts" / "part5"
PART4 = SERIES / "cato" / "parts" / "part4"
PLAYGROUND = SERIES / "cato" / "examples" / "playground"
RUNS, DEMOS = HERE / "runs.json", HERE / "demos.json"
REC = HERE / "recordings"
DATA_JS = HERE.parent / "assets" / "data.js"
if (HERE / "cato" / "context.py").exists():   # the public philoai_codes folder: everything sits side by side
    PART5, PART4, PLAYGROUND = HERE, HERE.parent / "part4-permissions", HERE / "shop"
    DATA_JS = HERE / "numbers.json"
MODEL = "sonnet"                       # anthropic/claude-sonnet-5.5, the model of Parts 1-4
LONG = ("The email folder here is Python's email package. When you call set_content on an EmailMessage "
        "with text that isn't plain ASCII, how does it choose the charset and the transfer encoding? "
        "Trace it from set_content to the final bytes, with file names and line numbers.")
FOLLOW = ("Now write test_charset.py with three tests: plain ASCII, accented text like café, and an emoji. "
          "Check the charset and the encoding of each. Run it with python3 and fix the tests until they all pass.")
RULES = "Add a product called tea, for $3.50. Then run the tests."
AFTER = "After all that: which file and which line pick the transfer encoding? One sentence, no tools."
REMEMBER = "Please remember this for next time: prices shown to people always have two decimals, like 3.50."
SQUEEZE_LIMIT = 10_000                 # a small desk, so we can watch Cato clear it

# Cato reads ~/.cato too: point HOME at an empty folder, so only the project's files count.
os.environ["HOME"] = tempfile.mkdtemp(prefix="cato-home-")
os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]

sys.path.insert(0, str(PART5))
from cato import agent, context, model, permissions, settings as settings_mod, tools, ui  # noqa: E402

ui.console.width = 100
WORK = Path("/tmp/shop")               # one fixed, short folder, as in Parts 3 and 4
MAIL = Path("/tmp/mail")               # a project holding a copy of Python's email package
MARK = ".made-by-record_part5"
SHOP = ["shop.py", "test_shop.py", ".env", "CATO.md", ".cato/settings.json",
        ".cato/hooks/protect_files.py", ".cato/hooks/check_python.py"]
FIXED = ("total += PRICES[product]\n", "total += PRICES[product] * count\n")   # Part 4 fixed the bug
# Your own note for every project, in ~/.cato/CATO.md. Exploring the project can't find it; only the walk does.
MY_NOTE = "# My notes, for every project\n- Every code change gets one line in CHANGELOG.md. Create the file if it's missing.\n"


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
def shop(files=SHOP, cato_md=True, my_note=False):
    """A fresh copy of the playground in /tmp/shop, with Part 4's fix in place (and maybe your own note)."""
    fresh(WORK)
    mine = Path(os.environ["HOME"]) / ".cato" / "CATO.md"
    mine.unlink(missing_ok=True)
    if my_note:
        mine.parent.mkdir(parents=True, exist_ok=True)
        mine.write_text(MY_NOTE)
    for name in files:
        if name == "CATO.md" and not cato_md:
            continue
        src, dst = PLAYGROUND / name, WORK / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dst)
    code = (WORK / "shop.py").read_text()
    (WORK / "shop.py").write_text(code.replace(*FIXED))
    with inside(WORK) as work:
        yield work


@contextlib.contextmanager
def json_package():
    """/tmp/mail with a copy of the json package, for the big-output demo."""
    fresh(MAIL)
    for f in sorted((Path(sysconfig.get_paths()["stdlib"]) / "json").glob("*.py")):
        shutil.copy(f, MAIL / f.name)
    with inside(MAIL) as work:
        yield work


@contextlib.contextmanager
def mail():
    """/tmp/mail/email: a copy of the email package from the Python that runs this script."""
    fresh(MAIL)
    shutil.copytree(Path(sysconfig.get_paths()["stdlib"]) / "email", MAIL / "email",
                    ignore=shutil.ignore_patterns("__pycache__"))
    with inside(MAIL) as work:
        yield work


def key():
    keyfile = SERIES.parents[1] / "openrouter.txt"
    if "OPENROUTER_API_KEY" not in os.environ and keyfile.exists():
        for word in keyfile.read_text().split():
            if word.startswith("sk-or-"):
                os.environ["OPENROUTER_API_KEY"] = word


def screen_session(tasks, answer_for=lambda name: "1", record_to=None, replay_from=None, desk_limit=None):
    """Run Cato's real screen (ui.repl) on the tasks. answer_for(tool name) answers each permission question."""
    ui.console.export_text(clear=True)
    model.record_file, model.replay_file, model._recorded = record_to, replay_from, None
    model.replay_delay = 0
    queue, log, start, asked, sessions = list(tasks), [], time.perf_counter(), [], []
    real = {"read_line": ui.read_line, "run_agent": ui.run_agent, "ask": ui.ask_permission, "answer": ui.answer}

    def ask_permission(session, screen, name, arguments, why):
        asked.append({"name": name, "arguments": arguments, "why": why})
        return real["ask"](session, screen, name, arguments, why)

    def read_line(session, prompt_text):
        if prompt_text.startswith("  "):                # the permission question
            reply = answer_for(asked[-1]["name"])
            asked[-1]["reply"] = reply
            ui.console.print(f"{prompt_text}{reply}")
            return reply
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

    ui.read_line, ui.run_agent, ui.ask_permission, ui.answer = read_line, run_agent, ask_permission, answer
    try:
        ui.repl(argparse.Namespace(model=MODEL, max_turns=agent.MAX_TURNS, max_cost=None, mode=None,
                                   desk_limit=desk_limit, inputs=os.devnull, svg=None))
    finally:
        ui.read_line, ui.run_agent, ui.ask_permission, ui.answer = (real["read_line"], real["run_agent"],
                                                                    real["ask"], real["answer"])
        model.record_file = model.replay_file = None
    text = ui.console.export_text(clear=False)
    html = ui.console.export_html(theme=ui.PHILO_THEME, inline_styles=True, clear=True, code_format="{code}")
    session = sessions[-1] if sessions else {}
    return {"seconds": round(time.perf_counter() - start, 2), "text": text, "html": html, "events": log,
            "asked": asked, "messages": session.get("messages", []), "cost": session.get("cost", 0),
            "tokens": session.get("tokens", 0)}


def recorded_calls(path):
    """Every request in a recording, in order, with its usage (the summary requests too)."""
    calls = []
    for line in Path(path).read_text().splitlines():
        usage = next((p["usage"] for p in reversed(json.loads(line)) if p.get("usage")), {})
        details = usage.get("prompt_tokens_details") or {}
        calls.append({"in": usage.get("prompt_tokens", 0), "out": usage.get("completion_tokens", 0),
                      "cached": details.get("cached_tokens", 0), "written": details.get("cache_write_tokens", 0),
                      "cost": usage.get("cost", 0)})
    return calls


def shop_state(work):
    tests = subprocess.run([sys.executable, "test_shop.py"], capture_output=True, text=True, cwd=work)
    return {"tests_after": (tests.stdout + tests.stderr).strip().splitlines()[-1:],
            "shop_after": (work / "shop.py").read_text(),
            "changelog_after": (work / "CHANGELOG.md").read_text() if (work / "CHANGELOG.md").exists() else None}


def bash_commands(messages):
    out = []
    for m in messages:
        for call in m.get("tool_calls") or []:
            if call["function"]["name"] == "Bash":
                out.append(json.loads(call["function"]["arguments"] or "{}").get("command", ""))
    return out


# ---------------------------------------------------------------- live: recorded once

def live(only=None):
    key()
    out = json.loads(RUNS.read_text()) if RUNS.exists() else {}
    out.update({"model": model.model_id(MODEL), "date": time.strftime("%Y-%m-%d"), "version": ui.__version__,
                "pricing": pricing()})
    REC.mkdir(exist_ok=True)
    edits_ok = lambda name: "2" if name in ("Edit", "Write") else "1"
    want = lambda name: not only or name in only

    if want("long"):
        (REC / "long.jsonl").unlink(missing_ok=True)
        with mail():
            shown = screen_session([LONG, FOLLOW], edits_ok, record_to=str(REC / "long.jsonl"))
        out["long"] = {**shown, "task": LONG, "follow": FOLLOW, "calls": recorded_calls(REC / "long.jsonl"),
                       "python": sys.version.split()[0]}
        print(f"\n[long: ${shown['cost']:.4f}, {shown['seconds']} s]\n")

    if want("squeeze"):
        (REC / "squeeze.jsonl").unlink(missing_ok=True)
        with mail():
            shown = screen_session([LONG, FOLLOW], edits_ok, record_to=str(REC / "squeeze.jsonl"), desk_limit=SQUEEZE_LIMIT)
        out["squeeze"] = {**shown, "task": LONG, "follow": FOLLOW, "calls": recorded_calls(REC / "squeeze.jsonl"),
                          "desk_limit": SQUEEZE_LIMIT}
        print(f"\n[squeeze: ${shown['cost']:.4f}, {shown['seconds']} s]\n")

    if want("rules_v05"):
        (REC / "rules_v05.jsonl").unlink(missing_ok=True)
        with shop(my_note=True) as work:
            shown = screen_session([RULES], edits_ok, record_to=str(REC / "rules_v05.jsonl"))
            out["rules_v05"] = {**shown, **shop_state(work), "task": RULES, "bash": bash_commands(shown["messages"]),
                                "calls": recorded_calls(REC / "rules_v05.jsonl")}
        print(f"\n[rules v0.5: ${shown['cost']:.4f}]\n")

    if want("rules_v04"):
        # Cato v0.4 has no CATO.md: run it as its own program, from Part 4's folder, on the same shop.
        (REC / "rules_v04.jsonl").unlink(missing_ok=True)
        with shop(my_note=True) as work:
            env = {**os.environ, "PYTHONPATH": str(PART4), "PYTHONDONTWRITEBYTECODE": "1"}
            start = time.perf_counter()
            r = subprocess.run([sys.executable, "-m", "cato", "-p", RULES, "--model", MODEL, "--yes", "--json",
                                "--record", str(REC / "rules_v04.jsonl")], capture_output=True, text=True, env=env)
            result = json.loads(r.stdout)
            calls = [json.loads(line) for line in (REC / "rules_v04.jsonl").read_text().splitlines()]
            commands = []
            for pieces in calls:
                args = {}
                for p in pieces:
                    for c in (p.get("choices") or [{}])[0].get("delta", {}).get("tool_calls") or []:
                        slot = args.setdefault(c.get("index", 0), {"name": "", "arguments": ""})
                        slot["name"] += (c.get("function") or {}).get("name") or ""
                        slot["arguments"] += (c.get("function") or {}).get("arguments") or ""
                commands += [json.loads(a["arguments"] or "{}").get("command", "") for a in args.values()
                             if a["name"] == "Bash"]
            out["rules_v04"] = {**shop_state(work), "task": RULES, "result": result, "bash": commands,
                                "seconds": round(time.perf_counter() - start, 2),
                                "calls": recorded_calls(REC / "rules_v04.jsonl")}
        print(f"\n[rules v0.4: ${result['cost']:.4f}]\n")

    if want("compact"):
        (REC / "compact.jsonl").unlink(missing_ok=True)
        with mail():
            shown = screen_session([LONG, "/context", "/compact", "/context", AFTER], record_to=str(REC / "compact.jsonl"))
            out["compact"] = {**shown, "calls": recorded_calls(REC / "compact.jsonl")}
        print(f"\n[compact: ${shown['cost']:.4f}]\n")

    if want("remember"):
        (REC / "remember.jsonl").unlink(missing_ok=True)
        with shop() as work:
            before = (work / "CATO.md").read_text()
            shown = screen_session([REMEMBER, "/memory"], edits_ok, record_to=str(REC / "remember.jsonl"))
            out["remember"] = {**shown, "task": REMEMBER, "cato_md_before": before,
                               "cato_md_after": (work / "CATO.md").read_text(),
                               "calls": recorded_calls(REC / "remember.jsonl")}
        print(f"\n[remember: ${shown['cost']:.4f}]\n")

    if want("cache"):
        out["cache"] = cache_experiment()
    if want("pairs"):
        out["pairs"] = pairs_experiment()

    RUNS.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    names = ("long", "squeeze", "rules_v05", "compact", "remember")
    total = sum(out[k]["cost"] for k in names if k in out) + out.get("rules_v04", {}).get("result", {}).get("cost", 0)
    total += sum(c["cost"] for c in out.get("cache", {}).get("calls", []))
    total += sum(v.get("cost", 0) for v in out.get("pairs", {}).values())
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


def one_call(messages, schemas):
    for piece in model.stream_model(messages, schemas, MODEL):
        if piece[0] == "reply":
            usage = piece[2]
            d = usage.get("prompt_tokens_details") or {}
            return {"in": usage.get("prompt_tokens", 0), "cached": d.get("cached_tokens", 0),
                    "written": d.get("cache_write_tokens", 0), "out": usage.get("completion_tokens", 0),
                    "cost": usage.get("cost", 0), "text": piece[1].get("content") or ""}


def cache_experiment():
    """The same start twice, then a changed first line, then a changed last line."""
    with shop():
        schemas = tools.tool_schemas(tools.TOOLS)
        # A tag of our own at the end, so no earlier run (still in the 5-minute cache) can answer for us.
        system = context.system_prompt() + f"\n<run>{time.time_ns()}</run>"
        ask = lambda text: {"role": "user", "content": text}
        steps = [
            ("first", "the first request", [{"role": "system", "content": system}, ask("Say ok.")]),
            ("same", "the very same start again", [{"role": "system", "content": system}, ask("Say ok.")]),
            ("top", "the time added as the first line", [{"role": "system", "content": f"Time: {time.strftime('%H:%M:%S')}\n" + system},
                                                        ask("Say ok.")]),
            ("edit", "the same start, the last message changed", [{"role": "system", "content": system}, ask("Say yes.")]),
            ("grow", "the first request, plus a reply and a new message", [{"role": "system", "content": system}, ask("Say ok."),
                                                                         {"role": "assistant", "content": "ok."}, ask("Say yes.")]),
        ]
        calls = []
        for name, label, messages in steps:
            result = one_call(messages, schemas)
            calls.append({"name": name, "label": label, **result})
            time.sleep(1)
        return {"calls": calls, "first_line": steps[2][2][0]["content"].splitlines()[0]}


def pairs_experiment():
    """A tool request and its answer belong together. Pull them apart, and the API says no (for free)."""
    call = {"id": "toolu_read_1", "type": "function", "function": {"name": "Read", "arguments": '{"file_path": "shop.py"}'}}
    chat = [{"role": "system", "content": "You are Cato, a coding assistant."},
            {"role": "user", "content": "What does shop.py do?"},
            {"role": "assistant", "content": None, "tool_calls": [call]},
            {"role": "tool", "tool_call_id": "toolu_read_1", "content": "PRICES = {'apple': 50}"},
            {"role": "assistant", "content": "It holds the prices."},
            {"role": "user", "content": "Thanks. Say ok."}]
    schemas = tools.tool_schemas(tools.TOOLS)
    cases = {"request_dropped": chat[:2] + chat[3:],      # an answer with no request
             "answer_dropped": chat[:3] + chat[4:]}       # a request with no answer
    global MODEL
    out, mine = {"whole": {"pairs_ok": context.pairs_ok(chat)}}, MODEL
    try:
        for family in ("sonnet", "terra"):
            MODEL = family
            for name, messages in cases.items():
                try:
                    reply = one_call(messages, schemas)
                    out[f"{family}/{name}"] = {"model": model.model_id(family), "pairs_ok": context.pairs_ok(messages),
                                               "error": None, "reply": reply["text"], "cost": reply["cost"]}
                except model.ModelError as e:
                    out[f"{family}/{name}"] = {"model": model.model_id(family), "pairs_ok": context.pairs_ok(messages),
                                               "error": str(e), "cost": 0}
    finally:
        MODEL = mine
    return out


# ---------------------------------------------------------------- demos: free

def demos():
    out = {}
    with shop() as work:
        schemas = tools.tool_schemas(tools.TOOLS)
        sp = context.system_prompt()
        note = context.reminders()
        out["first_page"] = {
            "instructions": context.INSTRUCTIONS, "environment": context.environment().replace(str(work.resolve()), "/tmp/shop"),
            "reminder": note.replace(str(work.resolve()), "/tmp/shop"),
            "tokens": {"instructions": context.estimate_tokens(context.INSTRUCTIONS),
                       "environment": context.estimate_tokens(context.environment()),
                       "tool forms": context.estimate_tokens(schemas), "CATO.md": context.estimate_tokens(note)},
            "stable": context.system_prompt() == sp}


    # CATO.md files, found folder by folder
    root = Path(tempfile.mkdtemp(prefix="cato-tree-")).resolve()
    home = root / "home"
    (home / ".cato").mkdir(parents=True)
    (home / ".cato" / "CATO.md").write_text("I like short answers.\n")
    (home / "code").mkdir()
    (home / "code" / "CATO.md").write_text("All my projects use tabs.\n")
    (home / "code" / "shop" / "src").mkdir(parents=True)
    (home / "code" / "shop" / "CATO.md").write_text("Run the tests with: python3 test_shop.py\n")
    old_home, old = os.environ["HOME"], os.getcwd()
    os.environ["HOME"] = str(home)
    os.chdir(home / "code" / "shop" / "src")
    try:
        tilde = lambda text: str(text).replace(str(home), "~")
        found = [tilde(p) for p in context.memory_files()]
        looked = [tilde(home / ".cato" / "CATO.md")] + [tilde(f / "CATO.md") for f in reversed([Path.cwd(), *Path.cwd().parents])
                                                        if str(f).startswith(str(home))]
        reminder = tilde(context.reminders())
    finally:
        os.environ["HOME"] = old_home
        os.chdir(old)
        shutil.rmtree(root, ignore_errors=True)
    out["tree"] = {"found": found, "looked": looked, "reminder": reminder}

    # a big output: the start and the end come back, all of it is saved to a file
    with json_package() as work:
        output, ok = tools.run_tool("Bash", json.dumps({"command": "cat encoder.py"}), tools.TOOLS)
        saved = sorted((work / ".cato" / "outputs").glob("*.txt"))
        out["big_output"] = {"command": "cat encoder.py", "chars": len((work / "encoder.py").read_text()),
                             "returned": len(output), "limit": tools.MAX_OUTPUT,
                             "note": re.search(r"\.\.\. \[.*?\] \.\.\.", output, re.S).group(0),
                             "head": output[:300], "tail": output[-200:],
                             "saved_chars": len(saved[0].read_text()) if saved else 0}

    # clearing old results, and the pairing rule, on the real long session
    if RUNS.exists():
        runs = json.loads(RUNS.read_text())
        if "long" in runs:
            messages = json.loads(json.dumps(runs["long"]["messages"]))
            schemas = tools.tool_schemas(tools.TOOLS)
            before = context.estimate_tokens(messages) + context.estimate_tokens(schemas)
            results = [len(m["content"]) for m in messages if m["role"] == "tool"]
            cleared = context.clear_old_results(messages)
            after = context.estimate_tokens(messages) + context.estimate_tokens(schemas)
            naive = runs["long"]["messages"][:2] + runs["long"]["messages"][3:]
            out["clearing"] = {"before": before, "after": after, "cleared": cleared, "kept": context.KEEP_RESULTS,
                               "results": results, "pairs_ok_after": context.pairs_ok(messages),
                               "naive_pairs_ok": context.pairs_ok(naive), "note": context.CLEARED}
            # about 4 characters per token, against the real count of each request
            msgs, checks = runs["long"]["messages"], []
            calls = runs["long"]["calls"]
            ends = [i for i, m in enumerate(msgs) if m["role"] == "assistant"]
            for k, i in enumerate(ends[:len(calls)]):
                guess = context.estimate_tokens(msgs[:i]) + context.estimate_tokens(schemas)
                checks.append({"turn": k + 1, "guess": guess, "real": calls[k]["in"]})
            out["estimate"] = checks

    # the map of which file calls which
    out["files"] = {"part4": file_graph(sorted((PART4 / "cato").glob("*.py"))),
                    "part5": file_graph(sorted((PART5 / "cato").glob("*.py")))}

    # replays of the live sessions, through the real screen, for $0
    if RUNS.exists():
        runs = json.loads(RUNS.read_text())
        out["replay"] = {}
        edits = lambda n: "2" if n in ("Edit", "Write") else "1"
        jobs = {"long": (mail, [LONG, FOLLOW], edits, None), "squeeze": (mail, [LONG, FOLLOW], edits, SQUEEZE_LIMIT),
                "compact": (mail, [LONG, "/context", "/compact", "/context", AFTER], None, None),
                "rules_v05": (lambda: shop(my_note=True), [RULES], lambda n: "2" if n in ("Edit", "Write") else "1", None)}
        for name, (where, tasks, policy, limit) in jobs.items():
            if name in runs and (REC / f"{name}.jsonl").exists():
                with where():
                    shown = screen_session(tasks, policy or (lambda n: "1"), replay_from=str(REC / f"{name}.jsonl"),
                                           desk_limit=limit)
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


def full_price(calls, price):
    """What the same requests would cost with no reread discount: every input token at the full price."""
    return sum(c["in"] * price["prompt"] + c["out"] * price["completion"] for c in calls) / 1e6


def export():
    runs = json.loads(RUNS.read_text()) if RUNS.exists() else {}
    demos_ = json.loads(DEMOS.read_text()) if DEMOS.exists() else {}
    price = runs.get("pricing", {})
    data = {"model": runs.get("model"), "date": runs.get("date"), "version": runs.get("version"),
            "pricing": price, "demos": demos_, "squeeze_limit": SQUEEZE_LIMIT, "my_note": MY_NOTE}
    for name in ("long", "squeeze", "rules_v05", "compact", "remember"):
        if name not in runs:
            continue
        run = runs[name]
        events = []
        for t, e in run["events"]:
            e = dict(e)
            if e["type"] == "usage":
                u = e.pop("usage")
                d = u.get("prompt_tokens_details") or {}
                e.update(tokens_in=u.get("prompt_tokens", 0), tokens_out=u.get("completion_tokens", 0),
                         cached=d.get("cached_tokens", 0), cost=u.get("cost", 0))
            if e["type"] == "tool_end":
                e["output"] = e["output"][:300]
            if e["type"] == "text":
                continue
            events.append([t, e])
        calls = run["calls"]
        data[name] = {"task": run.get("task"), "follow": run.get("follow"), "seconds": run["seconds"], "cost": round(run["cost"], 4),
                      "tokens": run["tokens"], "text": run["text"], "html": classed(run["html"]), "events": events,
                      "asked": run["asked"], "calls": calls, "turns": len(calls),
                      "read_total": sum(c["in"] for c in calls), "cached_total": sum(c["cached"] for c in calls),
                      "full_price": round(full_price(calls, price), 4) if price else None}
        for k in ("tests_after", "shop_after", "changelog_after", "bash", "desk_limit", "python", "cato_md_before", "cato_md_after"):
            if k in run:
                data[name][k] = run[k]
    if "rules_v04" in runs:
        r = runs["rules_v04"]
        data["rules_v04"] = {k: r[k] for k in ("task", "tests_after", "shop_after", "changelog_after", "bash", "seconds", "calls")}
        data["rules_v04"]["cost"] = round(r["result"]["cost"], 4)
        data["rules_v04"]["answer"] = r["result"]["result"]
        data["rules_v04"]["turns"] = r["result"]["turns"]
    if "compact" in data and "compact" in demos_.get("replay", {}):
        data["compact"]["text"] = demos_["replay"]["compact"]["text"]
        data["compact"]["html"] = classed(demos_["replay"]["compact"]["html"])
    for r in demos_.get("replay", {}).values():
        r.pop("html", None)
    for k in ("cache", "pairs"):
        if k in runs:
            data[k] = runs[k]
    # would the rules have asked about each test command? (the same gate in v0.4 and v0.5)
    rules = {"mode": "default", "allow": ["Bash(python3 test_shop.py)", "Bash(ls *)", "Bash(cat *)", "Bash(git status)"],
             "ask": ["Bash(git push *)"], "deny": ["Bash(rm *)", "Read(.env)", "Edit(.env)", "Write(.env)"]}
    for name in ("rules_v04", "rules_v05"):
        if name in data:
            data[name]["decisions"] = [[c, permissions.decide("Bash", {"command": c}, tools.find_tool("Bash", tools.TOOLS),
                                                               rules)[0]] for c in data[name]["bash"]]
    same = lambda text: re.sub(r"\d+\.\d+s\b|in [\d.]+s|[A-Z][a-z]{2} +\d+ \d\d:\d\d|output-\d+", "…", text or "")
    data["replay_identical"] = {k: same(v["text"]) == same(runs[k]["text"])
                                for k, v in demos_.get("replay", {}).items() if k in runs}
    DATA_JS.parent.mkdir(exist_ok=True)
    if DATA_JS.suffix == ".json":
        DATA_JS.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    else:
        DATA_JS.write_text("/* Written by code/record_part5.py from code/runs.json and code/demos.json. Don't edit. */\n"
                           "window.DATA = " + json.dumps(data, indent=1, ensure_ascii=False) + ";\n")
    print(f"wrote {DATA_JS}")


if __name__ == "__main__":
    if "--live" in sys.argv:
        only = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--only=")]
        live(only[0].split(",") if only else None)
    if "--demos" in sys.argv:
        demos()
    export()
