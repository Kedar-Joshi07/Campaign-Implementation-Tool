# STEP 3 — Chunked Data Import Pipeline

## Objective
Build robust CLI importers for customers, campaign sales, and the approximately 5M demographic dataset.

## Prompt to coding agent
Implement only Step 3 of Phase 1.

### General importer architecture
Create reusable import utilities but avoid over-generalization.
Suggested files:

```text
app/services/data_import_service.py
app/services/data_validation_service.py
scripts/import_customers.py
scripts/import_campaign_sales.py
scripts/import_demographics.py
```

### Supported inputs
- `.csv`
- `.csv.gz`
- demographic multi-part input through:
  - repeated `--file` values, OR
  - `--input-dir` + filename pattern

Do not require pandas for the import pipeline unless there is a compelling measured reason. Prefer Python `csv`, `gzip`, and batched `executemany` for predictable memory use.

### Mandatory import rules
1. Read rows as a stream.
2. Never hold the entire dataset in memory.
3. Validate header exactly against expected schema, allowing only documented normalization such as BOM removal.
4. Validate key IDs are nonblank.
5. Convert empty strings to NULL only where valid.
6. Normalize boolean/integer flags consistently.
7. Normalize ISO dates.
8. Use transaction batches.
9. Log progress every configurable N rows.
10. Record every import attempt in `data_import_runs`.
11. Store source path and timestamps.
12. Track rows read, inserted, rejected.
13. Fail with actionable error on schema mismatch.
14. Do not silently skip malformed rows.
15. Default behavior must not duplicate existing data.

### Replace/append behavior
Implement explicit modes:
- default: fail if target table already contains data
- `--replace`: explicitly clear and reload target table

For campaign sales `--replace`, clear campaign sales only, not customers.
For customers `--replace`, guard against breaking existing campaign foreign keys. If campaign sales exists, either refuse replacement or require an explicit safe sequence documented in README.

For demographics, `--replace` can clear and reload demographics because it is independent.

### Import order
Document and enforce logical import order:
1. customers
2. campaign_sales
3. demographics

### Customer validation
At minimum:
- exactly 22 expected columns
- unique/non-null `customer_id`
- valid ISO date_of_birth
- family_member_count >= 1 where provided
- nonnegative income

### Campaign sales validation
At minimum:
- exactly 38 expected columns
- unique/non-null `campaign_sales_id`
- non-null customer_id/campaign_id/product_id
- customer_id exists in customers
- start <= end
- contact_date within or reasonably related to campaign window; use generator semantics and reject only clearly impossible chronology
- purchase_flag 0/1
- pu_label 0/1
- if pu_label=1 then campaign_attributed_sale_flag must be 1
- if campaign_attributed_sale_flag=1 then purchase_flag must be 1
- if purchase_flag=1, order_id and purchase_date should be present
- if purchase_flag=0, transaction amounts should be zero/null according to source generator conventions

### Demographic validation
At minimum:
- exactly 28 columns
- unique/non-null person_id
- age in plausible range
- family_member_count >= 1
- children/adults nonnegative
- `number_of_children_in_family + number_of_adults_in_family == family_member_count`
- individual income nonnegative
- family income >= individual income

### Performance requirements
- configure batch size, default e.g. 5,000 or 10,000 rows
- use `executemany`
- avoid per-row commits
- optionally defer nonessential indexes until bulk import completes; if doing this, make index recreation reliable and documented

### Import metadata
Each import run should end in one of:
- RUNNING
- COMPLETED
- FAILED

On failure, update metadata with error details before exiting where possible.

### CLI examples to support

```bash
python scripts/import_customers.py --file ./source/customer_master_125000.csv.gz
python scripts/import_campaign_sales.py --file ./source/campaign_sales_570000.csv.gz
python scripts/import_demographics.py --input-dir ./source/demographics --pattern "*.csv.gz"
```

Add `--replace`, `--batch-size`, and optional `--progress-every`.

### Tests
Use small fixture CSVs to test:
- successful customer import
- campaign import with valid customer FK
- campaign import rejection for invalid FK
- demographic multi-file import
- schema mismatch rejection
- malformed family arithmetic rejection
- duplicate primary key behavior
- import metadata status
- replace behavior

### Step completion criteria
- all three importer types work on small fixtures
- streaming/batching implemented
- import metadata works
- README contains commands
- tests pass

Update progress tracker and stop.
