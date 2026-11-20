import csv
from datetime import datetime
rows, seen = [], set()
with open("customers.csv", newline="") as f:
    reader = csv.reader(f)
    next(reader)
    for name, email, date, plan in reader:
        name, email, date, plan = name.strip(), email.strip().lower(), date.strip(), plan.strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                date = datetime.strptime(date, fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                pass
        rows.append([name, email, date, plan])
with open("clean.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["name", "email", "signup_date", "plan"])
    writer.writerows(rows)
