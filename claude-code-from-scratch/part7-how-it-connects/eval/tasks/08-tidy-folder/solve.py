from pathlib import Path
GROUPS = {"images": ["holiday.jpg", "cat.png", "scan.PNG", "logo.svg"], "docs": ["report.pdf", "notes.txt", "letter.docx", "README.md"], "data": ["budget.csv", "data.json"]}
d = Path("downloads")
lines = []
for folder, names in GROUPS.items():
    (d / folder).mkdir(exist_ok=True)
    for name in names:
        (d / name).rename(d / folder / name)
        lines.append(f"- {folder}/{name}")
(d / "INDEX.md").write_text("# Index\n\n" + "\n".join(sorted(lines)) + "\n")
