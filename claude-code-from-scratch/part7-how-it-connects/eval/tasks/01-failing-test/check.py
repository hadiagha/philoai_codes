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


if (WORK / "test_temperature.py").read_text() != (START / "test_temperature.py").read_text():
    fail("the tests were changed")
code = """
from temperature import c_to_f, f_to_c, describe
assert f_to_c(212) == 100 and f_to_c(32) == 0 and f_to_c(-40) == -40
assert abs(f_to_c(98.6) - 37) < 1e-9
assert c_to_f(0) == 32 and c_to_f(-40) == -40
assert [describe(t) for t in (-1, 10, 20, 30)] == ["freezing", "cold", "mild", "hot"]
"""
result = run("-c", code)
if result.returncode != 0:
    fail(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "wrong results")
print("PASS")
