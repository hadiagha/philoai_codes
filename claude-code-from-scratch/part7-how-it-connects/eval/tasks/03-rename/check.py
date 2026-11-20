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


import re
sources = {p: p.read_text() for p in WORK.rglob("*.py")}
for path, text in sources.items():
    if re.search(r"\bcalc\b", text.replace("(Not the same as calc.)", "")):
        fail(f"calc is still used in {path.relative_to(WORK)}")
pricing = (WORK / "shop" / "pricing.py").read_text()
if "def calculate_total(" not in pricing:
    fail("calculate_total is not defined in shop/pricing.py")
if "def recalc_discounts(" not in pricing or "recalc_discounts(prices, discount)" not in (WORK / "shop" / "cart.py").read_text():
    fail("recalc_discounts was changed")
out = run("main.py")
if out.stdout.split() != ["33.0", "16.5"]:
    fail(f"main.py prints {out.stdout.strip()!r} {out.stderr.strip()[-200:]}")
print("PASS")
