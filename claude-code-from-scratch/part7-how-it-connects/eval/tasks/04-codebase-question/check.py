"""Hidden check. Usage: python3 check.py WORKDIR  -> prints PASS or FAIL: why (exit 0 or 1)."""
import subprocess
import sys
from pathlib import Path

WORK = Path(sys.argv[1]).resolve()
START = Path(__file__).parent / "start"


def fail(why):
    print(f"FAIL: {why}")
    sys.exit(1)


def run(*args, **kw):
    return subprocess.run([sys.executable, *args], cwd=WORK, capture_output=True, text=True,
                          timeout=60, **kw)


path = WORK / "answer.txt"
if not path.exists():
    fail("no answer.txt")
answer = dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)
if answer.get("function", "").strip().strip("`()") != "qualifies_for_free_shipping":
    fail(f"function is {answer.get('function')!r}")
try:
    minimum = float(answer.get("minimum", "").strip().lstrip("$"))
except ValueError:
    fail(f"minimum is {answer.get('minimum')!r}")
if minimum != 75:
    fail(f"minimum is {minimum}, expected 75")
print("PASS")
