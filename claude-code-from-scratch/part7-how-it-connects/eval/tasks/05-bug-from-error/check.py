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


if (WORK / "sales.json").read_text() != (START / "sales.json").read_text():
    fail("sales.json was changed")
out = run("report.py")
if out.returncode != 0:
    fail("report.py still crashes: " + (out.stderr.strip().splitlines() or ["?"])[-1])
expected = ["east: 30.00", "north: 112.50", "south: 50.00", "all: 192.50"]
if out.stdout.strip().splitlines() != expected:
    fail(f"report.py printed {out.stdout.strip()!r}")
print("PASS")
