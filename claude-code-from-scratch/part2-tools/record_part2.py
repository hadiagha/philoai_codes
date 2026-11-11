"""Record every real number, output and screen shown in Part 2, then freeze it.

    python record_part2.py --demos    # no API calls: run Cato's real tools on copies of the shop -> demos.json
    python record_part2.py --live     # calls OpenRouter (a few cents): two real Cato v0.2 runs -> runs.json
    python record_part2.py            # just rebuild ../assets/data.js from demos.json + runs.json

Run it with a Python that has httpx and pytest (the series uses ~/.cache/cato-venv).

What it records:
  demos.json  (free, repeatable)
    - the exact script Cato v0.1 used to fix the bug in Part 1, run again on the "twin" shop, where the
      same line appears twice: it changes both
    - Read, Glob, Grep, Write and Edit outputs on a copy of the shop, including the three edit rules failing
    - run_tool's error paths, trimming a long output, a timeout, and how many characters each way of editing takes
  runs.json   (recorded once, then frozen)
    - Cato v0.2 (cato/parts/part2, unchanged) on the same tiny shop bug as Part 1, with the same model
    - Cato v0.2 on the twin shop, where the buggy line appears twice
"""
import builtins
import contextlib
import difflib
import io
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
PART2 = SERIES / "cato" / "parts" / "part2"
PLAYGROUND = SERIES / "cato" / "examples" / "playground"
TWIN = HERE / "twin"
PART1_RUNS = SERIES / "part1-agent-loop" / "code" / "runs.json"
DEMOS, RUNS = HERE / "demos.json", HERE / "runs.json"
DATA_JS = HERE.parent / "assets" / "data.js"
if (HERE / "cato" / "tools.py").exists():     # the public philoai_codes folder: everything sits side by side
    PART2, PLAYGROUND, TWIN = HERE, HERE / "shop", HERE / "twin"
    PART1_RUNS = HERE.parent / "part1-agent-loop" / "runs.json"
    DATA_JS = HERE / "numbers.json"
MODEL = "sonnet"                                   # anthropic/claude-sonnet-5.5, the model Part 1 used
TASK = "The tests in test_shop.py fail. Find the bug and fix it."

sys.path.insert(0, str(PART2))
from cato import tools  # noqa: E402  (cato/parts/part2/cato/tools.py, unchanged)

# `python` inside commands is this interpreter (it has pytest), like in Part 1's recording
os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]


@contextlib.contextmanager
def project(src, files=("shop.py", "test_shop.py")):
    """A fresh copy of a tiny project in a folder called shop/, as the current folder."""
    root = Path(tempfile.mkdtemp(prefix="cato-part2-"))
    work = root / "shop"
    work.mkdir()
    for name in files:
        shutil.copy2(src / name, work / name)
    old = os.getcwd()
    os.chdir(work)
    tools.files_read.clear()
    try:
        yield work
    finally:
        os.chdir(old)
        shutil.rmtree(root)


def tidy(text, work):
    """Shorten the temporary folder in printed paths to '…/shop' (the only change made to any output)."""
    return text.replace(str(work.resolve()), "…/shop").replace(str(work), "…/shop")


def call(name, args, work):
    """One tool call through the real run_tool path, as the model would send it."""
    text, ok = tools.run_tool(name, args if isinstance(args, str) else json.dumps(args))
    return {"tool": name, "args": args, "ok": ok, "out": tidy(text, work)}


# ---------------------------------------------------------------- demos: no model, no cost

def demos():
    out = {"python": sys.version.split()[0]}
    part1 = json.loads(PART1_RUNS.read_text())["run"]
    fix_script = next(json.loads(tc["function"]["arguments"])["command"]
                      for m in part1["messages"] for tc in (m.get("tool_calls") or [])
                      if "replace(" in json.loads(tc["function"]["arguments"])["command"])

    # 1. Part 1's own fix, run on the twin shop: replace() changes every match
    with project(TWIN) as work:
        before = (work / "shop.py").read_text()
        res = subprocess.run(fix_script, shell=True, capture_output=True, text=True, cwd=work)
        after = (work / "shop.py").read_text()
        changed = [(i + 1, a, b) for i, (a, b) in enumerate(zip(before.splitlines(), after.splitlines())) if a != b]
        out["twin_v01"] = {"script": fix_script, "output": tidy(res.stdout + res.stderr, work).strip(),
                           "changed": changed, "occurrences": before.count("total += PRICES[product]\n"),
                           "before": before}

    # 2. the three edit rules, on the twin shop, through the real Edit tool
    with project(TWIN) as work:
        rules = {"not_read": call("Edit", {"file_path": "shop.py", "old_string": "total += PRICES[product]",
                                           "new_string": "total += PRICES[product] * count"}, work)}
        call("Read", {"file_path": "shop.py"}, work)
        rules["not_exact"] = call("Edit", {"file_path": "shop.py", "old_string": "    12\t        total += PRICES[product]",
                                           "new_string": "        total += PRICES[product] * count"}, work)
        rules["not_once"] = call("Edit", {"file_path": "shop.py", "old_string": "total += PRICES[product]",
                                          "new_string": "total += PRICES[product] * count"}, work)
        good = {"file_path": "shop.py",
                "old_string": "    for product, count in items.items():\n        total += PRICES[product]",
                "new_string": "    for product, count in items.items():\n        total += PRICES[product] * count"}
        rules["good"] = call("Edit", good, work)
        tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                               capture_output=True, text=True, cwd=work)
        rules["tests_after"] = re.sub(r" in [\d.]+s$", "", tests.stdout.strip().splitlines()[-1])
        # someone changes the file after Cato read it (an editor save), then Cato tries to edit again
        time.sleep(0.05)
        (work / "shop.py").write_text((work / "shop.py").read_text() + "\n")
        rules["stale"] = call("Edit", {"file_path": "shop.py", "old_string": "HALF", "new_string": "HALF"}, work)
        out["rules"] = rules

    # 3. reading and finding, on the playground shop
    with project(PLAYGROUND, ("shop.py", "test_shop.py", "CATO.md")) as work:
        (work / "build").mkdir()
        shutil.copy2(PLAYGROUND / "build" / "app.bundle.js", work / "build" / "app.bundle.js")
        (work / ".git").mkdir()
        (work / ".git" / "config").write_text("[core]\n")
        os.utime(work / "shop.py")                    # shop.py was changed last, so it's the newest
        out["read"] = call("Read", {"file_path": "shop.py"}, work)
        out["read_page"] = call("Read", {"file_path": "shop.py", "offset": 8, "limit": 6}, work)
        out["read_dir"] = call("Read", {"file_path": "."}, work)
        out["glob_py"] = call("Glob", {"pattern": "**/*.py"}, work)
        out["glob_all"] = call("Glob", {"pattern": "**/*"}, work)
        out["grep_prices"] = call("Grep", {"pattern": "PRICES"}, work)
        out["grep_defs"] = call("Grep", {"pattern": r"def \w+", "glob": "*.py"}, work)
        out["grep_codes"] = call("Grep", {"pattern": "save10|half", "ignore_case": True}, work)
        out["write_new"] = call("Write", {"file_path": "notes.txt", "content": "Prices are in cents.\nNever use floats for money.\n"}, work)
        out["write_unread"] = call("Write", {"file_path": "CATO.md", "content": "# Notes\n"}, work)

    # 4. one path for every call: each way a tool call can go wrong
    with project(PLAYGROUND) as work:
        out["errors"] = {
            "no_tool": call("Delete", {"file_path": "shop.py"}, work),
            "bad_json": call("Read", '{"file_path": "shop.py"', work),
            "missing": call("Read", {"path": "shop.py"}, work),
            "wrong_type": call("Read", {"file_path": "shop.py", "limit": "ten"}, work),
            "crash": call("Read", {"file_path": "shop2.py"}, work),
            "timeout": call("Bash", {"command": "sleep 5", "timeout": 2}, work),
            "exit_code": call("Bash", {"command": "python test_shop.py"}, work),
        }
        long = tools.run_bash("seq 1 10000")
        trimmed = tools.trim(long)
        out["trim"] = {"command": "seq 1 10000", "chars": len(long), "kept": tools.MAX_OUTPUT,
                       "cut": len(long) - tools.MAX_OUTPUT, "head": trimmed[:40], "tail": trimmed[-40:],
                       "marker": f"... [{len(long) - tools.MAX_OUTPUT} characters cut] ..."}
    out["bool_is_int"] = isinstance(True, int)

    # 5. how much the model has to write, three ways, for the one-line fix in shop.py
    shop = (PLAYGROUND / "shop.py").read_text()
    fixed = shop.replace("total += PRICES[product]\n", "total += PRICES[product] * count\n")
    patch = "\n".join(difflib.unified_diff(shop.splitlines(), fixed.splitlines(), "a/shop.py", "b/shop.py", lineterm=""))
    edit = {"file_path": "shop.py", "old_string": "total += PRICES[product]\n",
            "new_string": "total += PRICES[product] * count\n"}
    big = Path(difflib.__file__)
    out["ways"] = {"rewrite": len(json.dumps({"file_path": "shop.py", "content": fixed})),
                   "patch": len(json.dumps({"patch": patch})), "edit": len(json.dumps(edit)),
                   "patch_text": patch, "file_chars": len(shop), "file_lines": len(shop.splitlines()),
                   "big_name": big.name, "big_chars": len(big.read_text())}
    DEMOS.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"wrote {DEMOS}")


# ---------------------------------------------------------------- live runs: Cato v0.2, recorded once

calls = []
real_post = httpx.post


def recording_post(url, **kwargs):
    start = time.time()
    response = real_post(url, **kwargs)
    calls.append({"request": kwargs["json"], "response": response.json(), "seconds": round(time.time() - start, 2)})
    return response


class Tee(io.TextIOBase):
    """Print to the real terminal and keep a copy, so the slides show exactly what was printed."""
    def __init__(self, real):
        self.real, self.copy = real, io.StringIO()

    def write(self, text):
        self.real.write(text)
        self.copy.write(text)
        return len(text)


def key():
    if "OPENROUTER_API_KEY" not in os.environ:
        for word in (SERIES.parents[1] / "openrouter.txt").read_text().split():
            if word.startswith("sk-or-"):
                os.environ["OPENROUTER_API_KEY"] = word


def live_run(src):
    from cato import __version__, agent
    with project(src) as work:
        tee = Tee(sys.stdout)
        builtins.input = lambda prompt="": (tee.write(prompt + "y\n"), "y")[1]
        first = len(calls)
        messages = [{"role": "system", "content": agent.system_prompt()}, {"role": "user", "content": TASK}]
        tee.write(f"Cato v{__version__} · {MODEL} · type a task, or 'exit'\n\n> {TASK}\n")
        start = time.time()
        with contextlib.redirect_stdout(tee):
            print(agent.agent_loop(messages, MODEL))
        seconds = round(time.time() - start, 1)
        tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                               capture_output=True, text=True, cwd=work)
        return json.loads(tidy(json.dumps({
            "task": TASK, "calls": calls[first:], "messages": messages, "seconds": seconds,
            "terminal": tee.copy.getvalue(), "tests_after": tests.stdout.strip().splitlines()[-1],
            "shop_after": (work / "shop.py").read_text()}), work))


def live():
    key()
    httpx.post = recording_post
    out = {"model": "anthropic/claude-sonnet-5.5", "date": time.strftime("%Y-%m-%d"),
           "shop": live_run(PLAYGROUND), "twin": live_run(TWIN)}
    RUNS.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    cost = sum(c["response"].get("usage", {}).get("cost", 0) for c in calls)
    print(f"\nrecorded {len(calls)} calls, ${cost:.4f} -> {RUNS}")


# ---------------------------------------------------------------- export: the small numbers the slides use

def summary(run):
    usage = [c["response"].get("usage", {}) for c in run["calls"]]
    tool_calls = [{"name": tc["function"]["name"], "args": json.loads(tc["function"]["arguments"] or "{}"), "id": tc["id"]}
                  for m in run["messages"] for tc in (m.get("tool_calls") or [])]
    results = {m["tool_call_id"]: m["content"] for m in run["messages"] if m.get("role") == "tool"}
    for tc in tool_calls:
        tc["result"] = results.get(tc["id"], "")
    # Cato prints each call as one line, Read(<path>), cut at 60 characters, so the temporary folder was cut
    # before tidy() could shorten it. Redraw those lines from the same calls with the short folder name.
    from cato.agent import describe
    lines, k = [], 0
    for line in run["terminal"].split("\n"):
        if line.startswith("● ") and k < len(tool_calls):
            line = "● " + describe(tool_calls[k]["name"], json.dumps(tool_calls[k]["args"]))
            k += 1
        lines.append(line)
    run = dict(run, terminal="\n".join(lines))
    return {"turns": len(run["calls"]), "seconds": run["seconds"],
            "cost": round(sum(u.get("cost", 0) for u in usage), 4),
            "tokens_in": [u.get("prompt_tokens", 0) for u in usage],
            "tokens_out": [u.get("completion_tokens", 0) for u in usage],
            "costs": [u.get("cost", 0) for u in usage], "call_seconds": [c["seconds"] for c in run["calls"]],
            "tools": tool_calls, "asked": run["terminal"].count("Allow? [y/n]"),
            "terminal": run["terminal"], "tests_after": re.sub(r" in [\d.]+s$", "", run["tests_after"]),
            "answer": run["messages"][-1].get("content") or ""}


def export():
    data = {"demos": json.loads(DEMOS.read_text())}
    part1 = json.loads(PART1_RUNS.read_text())["run"]
    p1_usage = [c["response"]["usage"] for c in part1["calls"]]
    data["v01"] = {"turns": len(part1["calls"]), "seconds": part1["seconds"],
                   "cost": round(sum(u.get("cost", 0) for u in p1_usage), 4),
                   "asked": part1["terminal"].count("Run it? [y/n]"),
                   "tokens_in": [u["prompt_tokens"] for u in p1_usage]}
    if RUNS.exists():
        runs = json.loads(RUNS.read_text())
        data.update(model=runs["model"], date=runs["date"], shop=summary(runs["shop"]), twin=summary(runs["twin"]))
        # the size of the edit the model really sent, next to the other two ways
        edit = next((t for t in data["shop"]["tools"] if t["name"] == "Edit"), None)
        if edit:
            data["demos"]["ways"]["edit_real"] = len(json.dumps(edit["args"]))
    if DATA_JS.suffix == ".json":
        DATA_JS.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    else:
        DATA_JS.write_text("/* Written by code/record_part2.py from code/demos.json and code/runs.json. Don't edit. */\n"
                           "window.DATA = " + json.dumps(data, indent=1, ensure_ascii=False) + ";\n")
    print(f"wrote {DATA_JS}")


if __name__ == "__main__":
    if "--demos" in sys.argv:
        demos()
    if "--live" in sys.argv:
        live()
    export()
