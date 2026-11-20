from .config import FLAT_SHIPPING, FREE_SHIPPING_MIN


def qualifies_for_free_shipping(order):
    return order.total >= FREE_SHIPPING_MIN


def shipping_cost(order):
    return 0 if qualifies_for_free_shipping(order) else FLAT_SHIPPING
