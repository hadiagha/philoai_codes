"""Print the sales total for each region."""
import json


def totals(sales):
    result = {}
    for sale in sales:
        result[sale["region"]] = result.get(sale["region"], 0) + sale["amount"]
    return result


def main():
    with open("sales.json") as f:
        sales = json.load(f)
    by_region = totals(sales)
    for region, total in sorted(by_region.items()):
        print(f"{region}: {total:.2f}")
    print(f"all: {sum(by_region.values()):.2f}")


if __name__ == "__main__":
    main()
