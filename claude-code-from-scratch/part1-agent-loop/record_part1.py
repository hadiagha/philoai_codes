"""Record every real number and screen shown in Part 1, once, then freeze it.

    export OPENROUTER_API_KEY=sk-or-...
    python3 record_part1.py           # calls OpenRouter (a few cents), writes runs.json and numbers.json
    python3 record_part1.py --export  # no API calls: rebuild numbers.json from the frozen runs.json

What it records:
  1. hello_model.py as-is: the model alone, with no tools, asked to fix a bug it can't see.
  2. Forgetting: "My name is Hadi", then "What's my name?" sent alone, then sent with the history.
  3. The real Cato v0.1 (cato.py in this folder, unchanged) fixing the tiny shop bug,
     with every request, response, timing and the exact terminal output.
"""
import builtins
import contextlib
import io
import json
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
PART1 = HERE
PLAYGROUND = HERE / "shop"
RUNS = HERE / "runs.json"
NUMBERS = HERE / "numbers.json"
MODEL = "anthropic/claude-sonnet-5.5"
TASK = "The tests in test_shop.py fail. Find the bug and fix it."

calls = []          # every request and response, in order
real_post = httpx.post


def recording_post(url, **kwargs):
    start = time.time()
    response = real_post(url, **kwargs)
    calls.append({"request": kwargs["json"], "response": response.json(),
                  "seconds": round(time.time() - start, 2)})
    return response


def key():
    if "OPENROUTER_API_KEY" not in os.environ:
        sys.exit("Set OPENROUTER_API_KEY first (from openrouter.ai).")
    return os.environ["OPENROUTER_API_KEY"]


def chat(messages):
    response = recording_post("https://openrouter.ai/api/v1/chat/completions",
                              headers={"Authorization": f"Bearer {key()}"},
                              json={"model": MODEL, "messages": messages}, timeout=120)
    return response.json()["choices"][0]["message"]["content"]


class Tee(io.TextIOBase):
    """Print to the real terminal and keep a copy, so the slides show exactly what was printed."""
    def __init__(self, real):
        self.real, self.copy = real, io.StringIO()

    def write(self, text):
        self.real.write(text)
        self.copy.write(text)
        return len(text)


def record():
    key()
    httpx.post = recording_post
    out = {"model": MODEL, "date": time.strftime("%Y-%m-%d")}

    # 1. The model alone: hello_model.py, run unchanged.
    with contextlib.redirect_stdout(io.StringIO()):
        runpy.run_path(str(HERE / "hello_model.py"))
    out["alone"] = calls[-1]

    # 2. It forgets between calls.
    first = [{"role": "user", "content": "Hi! My name is Hadi."}]
    first.append({"role": "assistant", "content": chat(first)})
    alone = [{"role": "user", "content": "What's my name?"}]
    alone.append({"role": "assistant", "content": chat(alone)})
    together = first + [{"role": "user", "content": "What's my name?"}]
    together.append({"role": "assistant", "content": chat(together)})
    out["forget"] = {"first": first, "alone": alone, "together": together}

    # 3. Cato v0.1 on the tiny shop, in a fresh folder, saying yes to every command.
    work = Path(tempfile.mkdtemp(prefix="cato-part1-"))
    for name in ("shop.py", "test_shop.py"):
        shutil.copy(PLAYGROUND / name, work / name)
    os.chdir(work)
    os.environ["CATO_MODEL"] = MODEL
    os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]
    sys.path.insert(0, str(PART1))
    import cato                                        # cato.py in this folder, unchanged
    tee = Tee(sys.stdout)
    builtins.input = lambda prompt="": (tee.write(prompt + "y\n"), "y")[1]
    start_index = len(calls)
    messages = [{"role": "system", "content": cato.SYSTEM_PROMPT}, {"role": "user", "content": TASK}]
    tee.write(f"Cato v0.1 · {cato.MODEL} · type a task, or 'exit'\n\n> {TASK}\n")
    start = time.time()
    with contextlib.redirect_stdout(tee):
        answer = cato.agent_loop(messages)
        print(answer)
    seconds = round(time.time() - start, 1)
    tests = subprocess.run([sys.executable, "test_shop.py"], capture_output=True, text=True)
    out["run"] = {"task": TASK, "calls": calls[start_index:], "messages": messages,
                  "seconds": seconds, "terminal": tee.copy.getvalue(),
                  "tests_after": tests.stdout, "shop_after": (work / "shop.py").read_text()}
    RUNS.write_text(json.dumps(out, indent=1))
    print(f"\nrecorded {len(calls)} calls -> {RUNS}")


def export():
    """Turn the frozen runs.json into the numbers and texts shown on the slides."""
    runs = json.loads(RUNS.read_text())
    run = runs["run"]
    usage = [c["response"]["usage"] for c in run["calls"]]
    first_tool_msg = next(m for m in run["messages"] if m.get("tool_calls"))
    call = first_tool_msg["tool_calls"][0]
    result = next(m for m in run["messages"] if m.get("role") == "tool" and m["tool_call_id"] == call["id"])
    alone_usage = runs["alone"]["response"]["usage"]
    data = {
        "model": runs["model"], "date": runs["date"],
        "alone": {"answer": runs["alone"]["response"]["choices"][0]["message"]["content"],
                  "in": alone_usage["prompt_tokens"], "out": alone_usage["completion_tokens"],
                  "cost": alone_usage.get("cost", 0)},
        "forget": {k: [m["content"] for m in v] for k, v in runs["forget"].items()},
        "run": {
            "turns": len(run["calls"]), "seconds": run["seconds"],
            "cost": round(sum(u.get("cost", 0) for u in usage), 4),
            "tokens_in": [u["prompt_tokens"] for u in usage],
            "tokens_out": [u["completion_tokens"] for u in usage],
            "costs": [u.get("cost", 0) for u in usage],
            "call_seconds": [c["seconds"] for c in run["calls"]],
            "commands": [json.loads(tc["function"]["arguments"])["command"]
                         for m in run["messages"] for tc in (m.get("tool_calls") or [])],
            "terminal": run["terminal"], "tests_after": run["tests_after"],
            "first_call": {"id": call["id"], "arguments": call["function"]["arguments"],
                           "result": result["content"][:400]},
            "answer": run["messages"][-1].get("content") or "",
        },
    }
    NUMBERS.write_text(json.dumps(data, indent=1) + "\n")
    print(f"wrote {NUMBERS}: {data['run']['turns']} turns, {data['run']['seconds']} s, ${data['run']['cost']}")


if __name__ == "__main__":
    if "--export" not in sys.argv:
        record()
    export()
