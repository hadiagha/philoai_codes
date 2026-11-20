"""Prices and totals."""


def calc(prices, tax=0.1):
    """The total of some prices, with tax added."""
    return round(sum(prices) * (1 + tax), 2)


def recalc_discounts(prices, percent):
    """Prices after a discount. (Not the same as calc.)"""
    return [round(p * (1 - percent / 100), 2) for p in prices]
