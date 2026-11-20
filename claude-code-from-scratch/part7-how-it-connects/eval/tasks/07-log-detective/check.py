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
answer = {k.strip(): v.strip() for k, v in (line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)}
expected = {"user": "omar", "time": "09:12:30", "errors": "3"}
for key, value in expected.items():
    if answer.get(key) != value:
        fail(f"{key} is {answer.get(key)!r}, expected {value}")
print("PASS")
