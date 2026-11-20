Clean customers.csv into a new file, clean.csv:

- the columns are name,email,signup_date,plan, with that header row first
- trim the spaces around every value
- emails in lower case, and plan in lower case
- dates as YYYY-MM-DD (the input mixes YYYY-MM-DD, MM/DD/YYYY and YYYY/MM/DD)
- drop rows that have no email
- drop duplicate customers (the same email): keep the first one
- otherwise keep the original order

Don't change customers.csv.
