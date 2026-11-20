---
name: add-product
description: How to add a product to the shop or change a price, the way this team does it. Use it whenever a product is added or a price changes.
---
# Adding a product

1. Add it to PRICES in shop.py. The name is one lowercase word. The price is whole cents: 425, never 4.25.
2. Run the price check that comes with this skill:
   python3 .cato/skills/add-product/check_prices.py
   It must print "prices ok". If it doesn't, fix the price and run it again.
3. Run python3 test_shop.py.
4. Reply in two lines: what you added, and what the two checks printed.
