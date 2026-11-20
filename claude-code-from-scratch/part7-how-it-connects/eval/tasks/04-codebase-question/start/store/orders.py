from dataclasses import dataclass, field

from .config import MAX_ITEMS, TAX_RATE


@dataclass
class Order:
    items: list = field(default_factory=list)   # (name, price) pairs

    @property
    def total(self):
        return sum(price for _, price in self.items)

    def with_tax(self):
        return round(self.total * (1 + TAX_RATE), 2)

    def add(self, name, price):
        if len(self.items) >= MAX_ITEMS:
            raise ValueError("too many items")
        self.items.append((name, price))
