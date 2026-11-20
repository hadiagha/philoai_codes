"""The shop's price check: every product is one lowercase word, and every price is whole cents."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from shop import PRICES  # noqa: E402

problems = []
for name, price in PRICES.items():
    if not (name.isalpha() and name.islower()):
        problems.append(f"{name!r}: use one lowercase word")
    if not isinstance(price, int) or isinstance(price, bool) or price <= 0:
        problems.append(f"{name!r}: {price!r} is not a whole number of cents")
    elif price > 10_000:
        problems.append(f"{name!r}: {price} cents is over $100; check it")
print("\n".join(problems) if problems else f"prices ok: {len(PRICES)} products")
sys.exit(1 if problems else 0)
