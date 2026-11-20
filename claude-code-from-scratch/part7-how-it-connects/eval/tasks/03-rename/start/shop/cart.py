from .pricing import calc, recalc_discounts


def checkout(prices, discount=0):
    if discount:
        prices = recalc_discounts(prices, discount)
    return calc(prices)
