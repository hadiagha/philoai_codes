"""The small test: 8 tasks, each done in a fresh copy and checked by a script the agent never sees.

    python run_eval.py --verify                          the checks fail at the start and pass when solved (no AI)
    python run_eval.py --agents cato:terra --tasks 01    Cato with GPT-6.1 Terra on task 01
    python run_eval.py --agents cato:sonnet,cato:opus,cato:sol,cato:terra,cato:gemini,claude

Agents:
    cato:<model>   Cato (parts/part6) through OpenRouter, with --max-cost per run
    claude         the real Claude Code with Opus (claude -p), on your Claude account

Both run in "accept edits" mode with the same short list of allowed shell commands (COMMANDS).
Each run happens in a new temporary folder outside this repo. Results go to results/<time>.jsonl.
The OpenRouter spend of all Cato runs stops at --budget dollars.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS = HERE / "tasks"
CATO_PART = HERE.parent / "cato" / "parts" / "part6"
if not CATO_PART.exists():
    CATO_PART = HERE.parent                                   # the public folder: cato/ sits next to eval/
KEY_FILE = HERE.parents[2] / "openrouter.txt"
# Both agents get the same permissions: edits inside the folder, plus these shell commands. Anything else is refused.
COMMANDS = ["python3", "python", "pytest", "ls", "cd", "cat", "head", "tail", "wc", "grep", "find", "sort",
            "diff", "echo", "mkdir", "mv", "cp", "touch"]


def task_dirs(selection):
    tasks = sorted(p for p in TASKS.iterdir() if (p / "check.py").exists())
    if selection == "all":
        return tasks
    wanted = selection.split(",")
    return [t for t in tasks if any(t.name.startswith(w) for w in wanted)]


def fresh_copy(task):
    work = Path(tempfile.mkdtemp(prefix=f"cato-eval-{task.name[:2]}-"))
    shutil.copytree(task / "start", work, dirs_exist_ok=True)
    return work


def check(task, work):
    result = subprocess.run([sys.executable, str(task / "check.py"), str(work)],
                            capture_output=True, text=True, timeout=120)
    lines = (result.stdout.strip() or result.stderr.strip() or "FAIL: no output").splitlines()
    return result.returncode == 0, lines[-1]


def environment():
    """A PATH whose python3 and pytest work, plus the OpenRouter key for Cato."""
    env = dict(os.environ)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    if "OPENROUTER_API_KEY" not in env and KEY_FILE.exists():
        for word in KEY_FILE.read_text().split():
            if word.startswith("sk-or-"):
                env["OPENROUTER_API_KEY"] = word
                break
    return env


def run_agent(agent, prompt, work, max_cost, timeout, record=None):
    """Run one agent on one task. Returns its stats as a dict. record: a file for Cato's session (to replay it free)."""
    env = environment()
    if agent.startswith("cato:"):
        env["PYTHONPATH"] = str(CATO_PART)
        home = Path(tempfile.mkdtemp(prefix="cato-home-"))         # a clean ~/.cato with just the allow list
        (home / ".cato").mkdir()
        allow = [f"Bash({c})" for c in COMMANDS] + [f"Bash({c} *)" for c in COMMANDS]
        (home / ".cato" / "settings.json").write_text(json.dumps({"permissions": {"allow": allow}}))
        env["HOME"] = str(home)
        command = [sys.executable, "-m", "cato", "-p", prompt, "--model", agent.split(":", 1)[1], "--json",
                   "--mode", "acceptEdits", "--max-cost", str(max_cost), "--max-turns", "30"]
        if record:
            command += ["--record", str(record)]
    elif agent == "claude":
        command = [shutil.which("claude") or str(Path.home() / ".local/bin/claude"), "-p", prompt,
                   "--model", "opus", "--output-format", "json", "--permission-mode", "acceptEdits",
                   "--allowedTools", ",".join(["Read", "Edit", "Write", "Glob", "Grep"] + [f"Bash({c}:*)" for c in COMMANDS]),
                   "--no-session-persistence", "--setting-sources", "project", "--strict-mcp-config"]
    else:
        raise SystemExit(f"Unknown agent {agent}")
    start = time.time()
    try:
        result = subprocess.run(command, cwd=work, env=env, capture_output=True, text=True,
                                timeout=timeout)
        out = json.loads(result.stdout.strip().splitlines()[-1]) if result.stdout.strip() else {}
    except subprocess.TimeoutExpired:
        out = {"reason": "timeout"}
    except json.JSONDecodeError:
        out = {"reason": "bad output: " + result.stdout[-300:] + result.stderr[-300:]}
    seconds = round(time.time() - start, 1)
    if agent == "claude":  # Claude Code's own JSON result
        return {"turns": out.get("num_turns"), "cost": out.get("total_cost_usd", 0.0),
                "seconds": seconds, "reason": out.get("subtype", out.get("reason", "")),
                "answer": str(out.get("result", ""))[:500],
                "usage": out.get("usage"), "model_usage": out.get("modelUsage"),
                "api_seconds": round((out.get("duration_api_ms") or 0) / 1000, 1),
                "denied": [f'{d.get("tool_name")}: {json.dumps(d.get("tool_input"))[:160]}'
                           for d in out.get("permission_denials") or []]}
    return {"turns": out.get("turns"), "cost": out.get("cost", 0.0), "seconds": seconds, "tokens": out.get("tokens"),
            "reason": out.get("reason", ""), "answer": str(out.get("result", ""))[:500]}


def verify():
    """No AI: every check must fail on the starting files and pass on the reference solution."""
    good = True
    for task in task_dirs("all"):
        work = fresh_copy(task)
        before, why = check(task, work)
        subprocess.run([sys.executable, str(task / "solve.py")], cwd=work, check=True)
        after, why_after = check(task, work)
        ok = (not before) and after
        good &= ok
        print(f"{'ok ' if ok else 'BAD'} {task.name:22} start: {why[:60]:62} solved: {why_after}")
        shutil.rmtree(work)
    return good


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verify", action="store_true", help="test the checks themselves (free)")
    parser.add_argument("--agents", default="cato:terra", help="comma-separated, e.g. cato:sonnet,claude")
    parser.add_argument("--tasks", default="all", help="all, or prefixes like 01,04")
    parser.add_argument("--max-cost", type=float, default=0.50, help="OpenRouter dollars per Cato run")
    parser.add_argument("--budget", type=float, default=8.0, help="stop when Cato runs have spent this")
    parser.add_argument("--timeout", type=int, default=900, help="seconds per run")
    parser.add_argument("--keep", action="store_true", help="keep the work folders")
    args = parser.parse_args()
    if args.verify:
        sys.exit(0 if verify() else 1)

    results_dir = HERE / "results"
    results_dir.mkdir(exist_ok=True)
    out_path = results_dir / f"{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    spent, rows = 0.0, []
    for agent in args.agents.split(","):
        for task in task_dirs(args.tasks):
            if agent.startswith("cato") and spent >= args.budget:
                print(f"Budget of ${args.budget} reached. Stopping.")
                break
            work = fresh_copy(task)
            prompt = (task / "task.md").read_text().strip()
            record = results_dir / out_path.stem / f"{agent.replace(':', '-')}_{task.name}.jsonl"
            record.parent.mkdir(exist_ok=True)
            stats = run_agent(agent, prompt, work, args.max_cost, args.timeout, record)
            passed, why = check(task, work)
            if agent.startswith("cato"):
                spent += stats["cost"] or 0
            row = {"agent": agent, "task": task.name, "passed": passed, "check": why, **stats,
                   "date": time.strftime("%Y-%m-%d")}
            rows.append(row)
            with open(out_path, "a") as f:
                f.write(json.dumps(row) + "\n")
            print(f"{'PASS' if passed else 'FAIL'}  {agent:12} {task.name:22} turns={row['turns']} "
                  f"{row['seconds']:6.1f}s ${row['cost'] or 0:.4f}  {'' if passed else why[:80]}")
            if not args.keep:
                shutil.rmtree(work, ignore_errors=True)
    print(f"\nCato OpenRouter spend: ${spent:.3f}. Results: {out_path}")
    for agent in dict.fromkeys(r["agent"] for r in rows):
        mine = [r for r in rows if r["agent"] == agent]
        print(f"  {agent:12} {sum(r['passed'] for r in mine)}/{len(mine)} passed, "
              f"${sum(r['cost'] or 0 for r in mine):.3f}, {sum(r['seconds'] for r in mine):.0f}s")


if __name__ == "__main__":
    main()
