import re
from pathlib import Path
for p in Path(".").rglob("*.py"):
    s = p.read_text()
    s = re.sub(r"\bcalc\b(?!\.\))", "calculate_total", s)
    p.write_text(s)
