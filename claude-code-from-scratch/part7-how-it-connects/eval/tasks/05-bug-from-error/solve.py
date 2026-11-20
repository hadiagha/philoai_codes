from pathlib import Path
p = Path("report.py")
p.write_text(p.read_text().replace('+ sale["amount"]', '+ float(sale["amount"])'))
