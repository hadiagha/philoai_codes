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


import csv
if (WORK / "customers.csv").read_text() != (START / "customers.csv").read_text():
    fail("customers.csv was changed")
if not (WORK / "clean.csv").exists():
    fail("no clean.csv")
with open(WORK / "clean.csv", newline="") as f:
    rows = [[cell.strip() for cell in row] for row in csv.reader(f) if row]
expected = [["name", "email", "signup_date", "plan"],
            ["Ada Lovelace", "ada@example.com", "2024-03-01", "pro"],
            ["Alan Turing", "alan@example.com", "2024-03-15", "free"],
            ["Grace Hopper", "grace@example.com", "2024-04-02", "pro"],
            ["Barbara Liskov", "barbara@example.com", "2024-06-20", "free"],
            ["Edsger Dijkstra", "edsger@example.com", "2024-11-02", "pro"]]
if rows != expected:
    wrong = next((i for i, (a, b) in enumerate(zip(rows, expected)) if a != b), min(len(rows), len(expected)))
    fail(f"row {wrong} is {rows[wrong] if wrong < len(rows) else 'missing'}; expected {expected[wrong] if wrong < len(expected) else 'nothing'}")
print("PASS")
