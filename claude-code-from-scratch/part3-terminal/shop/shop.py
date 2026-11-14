"""A tiny shop: prices in cents, a cart, and a discount code."""

PRICES = {"apple": 50, "bread": 250, "milk": 120, "coffee": 899}

CODES = {"SAVE10": 10, "HALF": 50}


def cart_total(items):
    """Total price of a cart, in cents. items maps a product to how many."""
    total = 0
    for product, count in items.items():
        total += PRICES[product]
    return total


def apply_code(total, code):
    """Take a percent off the total. Unknown codes change nothing."""
    percent = CODES.get(code, 0)
    return total - total * percent // 100


def receipt(items, code=None):
    """A short text receipt."""
    total = cart_total(items)
    if code:
        total = apply_code(total, code)
    return f"Total: ${total / 100:.2f}"
