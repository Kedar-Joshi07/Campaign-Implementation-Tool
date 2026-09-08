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

## Canonical checksum and LFS manifest

Raw GZIP SHA-256 identifies the exact compressed artifact. Decompressed content SHA-256 identifies semantic content independent of gzip container metadata.

| File | Bytes | Raw GZIP SHA-256 | Decompressed content SHA-256 | LFS object ref |
|---|---:|---|---|---|
| customer_master_125000.csv.gz | 6145025 | 8a2c5601a96dc54708246a84cfd7715cf53e3d6f95e67472b1e2c2428bf0d18f | fa0e53b055e0340d0a7cfc6dfdd2fc8bcf18c606e7c8b2b13853ef9a561447bd | 0cedbaa5d5 |
| campaign_sales_570000.csv.gz | 6466267 | 89e6f846a9b9de9bdb5a3945bd785dc7d83a98132ed5388e51072b7a44244116 | f0a391bbd2ef8262644b1f5c879f3ba1d473476889db8b48e6fde222ea640e0d | 6d84305c09 |
| usa_demographic_synthetic_5000000_rows.csv.gz | 333670533 | adb33ce1daf92b547171960f69f893fec93296d3d514ac7e1bdffbf5c736ac71 | a664b1a3904079a3c8b5c398de10009d52e8fd2ec6b4751a5caebb4512cb7dba | abaf51153c |

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
