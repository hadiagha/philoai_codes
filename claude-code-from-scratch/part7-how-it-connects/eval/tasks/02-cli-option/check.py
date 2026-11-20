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


hidden = WORK / ".hidden_sample.txt"
hidden.write_text("one two three\nfour\n\nfive six\n")
try:
    words = run("wordcount.py", str(hidden))
    lines = run("wordcount.py", "--lines", str(hidden))
    helptext = run("wordcount.py", "--help")
finally:
    hidden.unlink()
if words.stdout.strip() != "6":
    fail(f"word count changed: {words.stdout.strip()!r} {words.stderr.strip()[-200:]}")
if lines.stdout.strip() != "4":
    fail(f"--lines printed {lines.stdout.strip()!r}, expected 4 {lines.stderr.strip()[-200:]}")
if "--lines" not in helptext.stdout:
    fail("--lines is missing from --help")
if not (WORK / "test_wordcount.py").exists():
    fail("no test_wordcount.py")
if "lines" not in (WORK / "test_wordcount.py").read_text():
    fail("test_wordcount.py doesn't test the new option")
tests = run("-m", "pytest", "-q", "-p", "no:cacheprovider", "test_wordcount.py")
if tests.returncode != 0:
    fail("test_wordcount.py fails: " + tests.stdout.strip().splitlines()[-1])
print("PASS")
