# STEP 4 — Indexing, Reconciliation, and Data Quality Checks

## Objective
Add appropriate SQLite indexes and reconciliation logic so the application can prove that imported data is structurally sound.

## Prompt to coding agent
Implement only Step 4 of Phase 1.

### Index management
Create index initialization/verification in the schema/database layer.

Required indexes from the Phase 1 freeze must exist.

Do not create redundant indexes where the primary key already supplies equivalent indexing.

### Reconciliation service
Create a service such as:
`app/services/data_reconciliation_service.py`

It must calculate and return:

#### Customers
- total rows
- distinct customer_id count
- min/max date_of_birth
- count of null/blank critical identifiers

#### Campaign sales
- total rows
- distinct campaign_sales_id
- distinct customer_id
- distinct campaign_id
- distinct product_id
- min/max contact_date
- purchase count
- attributed purchase count
- PU positive count
- invalid customer FK count using explicit reconciliation query as an extra safety check
- PU consistency violation count

#### Demographics
- total rows
- distinct person_id
- min/max age
- min/max individual income
- family arithmetic violation count
- family income < individual income violation count

### Dataset expected-count configuration
Allow expected counts to be configured, not hard-coded in SQL.
Suggested defaults:
- customers: 125000
- campaign_sales: 570000
- demographics: 5000000

Because user said approximate for customer count, expected customer count should be configurable and the UI should distinguish:
- expected target
- actual count
- exact-match required/not required

Campaign sales target is 570,000 by current generator default.
Demographics target is 5,000,000.

### Reconciliation status
Return statuses such as:
- NOT_LOADED
- OK
- WARNING
- ERROR

Examples:
- missing table data -> NOT_LOADED
- exact/acceptable counts and zero integrity violations -> OK
- count differs from configured expectation but integrity is sound -> WARNING
- PK/FK/consistency violations -> ERROR

### CLI reconciliation command
Create:
`python scripts/validate_data.py`

It should print a concise table-like summary and exit:
- 0 for OK/WARNING without structural error
- nonzero for ERROR

Add optional `--json` output.

### Query performance check
Record approximate execution time for key summary queries in development logs/tests.
Do not introduce complex benchmarking infrastructure.

### Tests
Test reconciliation against:
- empty DB
- valid small fixture DB
- deliberately broken fixture data where possible
- expected count mismatch warning

### Step completion criteria
- all required indexes exist
- reconciliation CLI works
- data integrity status is machine-readable
- tests pass

Update progress tracker and stop.
