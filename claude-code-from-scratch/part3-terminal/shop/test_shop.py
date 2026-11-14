"""Run with: python test_shop.py"""
from shop import apply_code, cart_total, receipt


def test_one_of_each():
    assert cart_total({"apple": 1, "milk": 1}) == 170


def test_counts_matter():
    assert cart_total({"apple": 3}) == 150


def test_code():
    assert apply_code(1000, "SAVE10") == 900
    assert apply_code(1000, "NOPE") == 1000


def test_receipt():
    assert receipt({"bread": 2}, "HALF") == "Total: $2.50"


if __name__ == "__main__":
    failed = 0
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            try:
                test()
                print(f"ok    {name}")
            except AssertionError:
                failed += 1
                print(f"FAIL  {name}")
    print(f"{failed} failed" if failed else "all passed")
    raise SystemExit(1 if failed else 0)
