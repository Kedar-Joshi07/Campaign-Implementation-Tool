# Data Folder Guide

Important: every name, email, phone, address, and other records in this repository is synthetic test data.

Identity boundary:

- customer_id belongs to historical customer/campaign data.
- person_id belongs to the independent demographic prospect universe.
- customer_id != person_id by design.
- No deterministic or inferred linkage between these identifiers is implemented.

## Canonical tracked inputs

These files are the baseline source inputs for reproducible setup.

| File | Purpose | Expected rows |
|---|---|---:|
| customer_master_125000.csv.gz | historical customer foundation | 125000 |
| campaign_sales_570000.csv.gz | historical campaign observations | 570000 |
| usa_demographic_synthetic_5000000_rows.csv.gz | independent prospect universe | 5000000 |

## Additional tracked references

- customer_master_sample_10000.csv
- campaign_sales_sample_10000.csv
- usa_demographic_synthetic_sample_10000.csv
- customer_master_summary.json
- campaign_sales_summary.json
- usa_demographic_synthetic_summary.json
- product_master.csv
- campaign_master.csv
- usa_demographic_state_reference.csv

## Local runtime file

- campaign_poc.db is the local SQLite runtime database.
- The database is environment/runtime state and should be treated as a local artifact.

## Regeneration notes

- Canonical .csv.gz files are tracked with Git LFS.
- Generators in data_generation_scripts can regenerate synthetic sources when needed.
- Regeneration should preserve schema compatibility and be followed by import + reconciliation validation.
