from shop.cart import checkout
from shop.pricing import calc

print(calc([10, 20]))
print(checkout([10, 20], discount=50))
