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


GROUPS = {"images": ["holiday.jpg", "cat.png", "scan.PNG", "logo.svg"], "docs": ["report.pdf", "notes.txt", "letter.docx", "README.md"], "data": ["budget.csv", "data.json"]}
d = WORK / "downloads"
for folder, names in GROUPS.items():
    for name in names:
        moved = d / folder / name
        if not moved.exists():
            fail(f"{folder}/{name} is missing")
        if moved.read_bytes() != (START / "downloads" / name).read_bytes():
            fail(f"{name} was changed")
loose = sorted(p.name for p in d.iterdir() if p.is_file() and p.name != "INDEX.md")
if loose:
    fail(f"files left at the top: {loose}")
if not (d / "INDEX.md").exists():
    fail("no INDEX.md")
listed = [line.strip() for line in (d / "INDEX.md").read_text().splitlines() if line.strip().startswith("-")]
expected = sorted(f"- {folder}/{name}" for folder, names in GROUPS.items() for name in names)
if sorted(listed) != expected:
    fail(f"INDEX.md lists {listed}")
if listed != sorted(listed) and listed != sorted(listed, key=str.lower):
    fail("INDEX.md is not sorted")
print("PASS")
