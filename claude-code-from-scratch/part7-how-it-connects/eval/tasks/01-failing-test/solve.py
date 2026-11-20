from pathlib import Path
p = Path("temperature.py")
p.write_text(p.read_text().replace("return fahrenheit - 32 * 5 / 9", "return (fahrenheit - 32) * 5 / 9"))
