# Campaign Implementation Intelligence

Campaign Implementation Intelligence is a local proof of concept for building,
validating, and later extending a campaign-analysis data foundation. Phase 1 uses
FastAPI, SQLite, and a static HTML/CSS/Vanilla JavaScript frontend.

This repository contains the completed Phase 1 foundation: a functional
Overview/Data Status UI, summary and reference APIs, SQLite storage, a streaming
import pipeline, required indexes, reconciliation, tests, and operational
documentation.

## Prerequisites

- Python 3.11 or newer
- PowerShell commands below assume Windows

## Architecture

FastAPI serves both the JSON APIs and the static frontend. Routers handle HTTP,
services coordinate validation and reconciliation, repositories own read SQL,
and the database package owns connections and schema/index creation. SQLite is
the only runtime datastore. Imports use Python's streaming CSV/GZIP readers and
bounded `executemany` batches, so even the 5-million-row demographic file is not
loaded into memory at once.

The demographic prospect universe is deliberately independent from historical
customers. There is no `person_id` to `customer_id` mapping.

## Folder structure

```text
app/                     FastAPI routers, schemas, services, repositories, DB code
data/                    Generated source files and local SQLite DB (Git-ignored)
data_generation_scripts/ Explicitly run synthetic-data generators
docs/                    Implementation and handoff documentation
frontend/                Static HTML, CSS, and Vanilla JavaScript UI
logs/                    Optional local logs
Prompts/                 Frozen implementation prompts and progress evidence
scripts/                 DB initialization, import, and reconciliation CLIs
tests/                   Unit, integration, API, and frontend contract tests
```

## One-time setup

Create one environment for the application, tests, importers, and data generators:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The root `requirements.txt` includes
`data_generation_scripts/requirements_campaign_data.txt`, so a separate generator
environment or second dependency installation is not needed.

On macOS or Linux, activate the same setup with:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

## Initialize SQLite

Create or verify the empty Phase 1 database schema:

```powershell
.\.venv\Scripts\python.exe scripts\init_db.py
```

Initialization is idempotent and never deletes existing rows. To print the table
names, columns, indexes, and current row counts:

```powershell
.\.venv\Scripts\python.exe scripts\init_db.py --inspect
```

The default database path is `data/campaign_poc.db`. This step creates the schema
only; generated CSV/GZIP files are not imported yet.

## Import generated data

Import in the enforced order: customers, campaign sales, then demographics.

```powershell
.\.venv\Scripts\python.exe scripts\import_customers.py `
  --file .\data\customer_master_125000.csv.gz

.\.venv\Scripts\python.exe scripts\import_campaign_sales.py `
  --file .\data\campaign_sales_570000.csv.gz

.\.venv\Scripts\python.exe scripts\import_demographics.py `
  --file .\data\usa_demographic_synthetic_5000000_rows.csv.gz
```

For split demographic files, repeat `--file` or use a directory and pattern:

```powershell
.\.venv\Scripts\python.exe scripts\import_demographics.py `
  --input-dir .\data\demographic_parts `
  --pattern "*.csv.gz"
```

Every importer supports `--batch-size`, `--progress-every`, and explicit
`--replace`. Without `--replace`, a nonempty target table causes a clear failure
instead of duplicating data. Customer replacement is refused after campaign rows
exist; for a complete clean reload, initialize a new database path and import all
three datasets in order. Campaign replacement clears only campaign rows, and
demographic replacement clears only the independent demographic table.

Imports commit in bounded batches. If validation fails after earlier batches were
committed, the run is marked `FAILED` with its read/inserted/rejected counts. Fix
the source issue and use an explicit safe replacement rather than appending to the
partial table.

### Expected source schemas

Files may be UTF-8 `.csv` or `.csv.gz`. The first row must match the following
frozen headers exactly and in order. Dates use `YYYY-MM-DD`; flags use `0` or `1`;
identifiers required by the database cannot be blank.

`customers` (22 columns):

```text
customer_id, first_name, last_name, gender, date_of_birth, address_line_1,
address_line_2, street, postal_code, city, state, country, phone_number, email,
individual_yearly_income, family_member_count, resident_status, resident_type,
education, employment_status, type_of_employment, marital_status
```

`campaign_sales` (38 columns):

```text
campaign_sales_id, customer_id, campaign_id, product_id, order_id, campaign_name,
campaign_type, campaign_channel, campaign_start_date, campaign_end_date,
campaign_category, offer_type, offer_value, creative_id, target_segment,
product_name, product_category, product_subcategory, product_price, product_cost,
product_tier, product_launch_date, contact_date, contacted_flag, delivery_status,
engagement_flag, engagement_type, response_flag, purchase_flag, purchase_date,
quantity, gross_sales_amount, discount_amount, net_sales_amount,
gross_margin_amount, days_to_purchase, campaign_attributed_sale_flag, pu_label
```

`demographics` (28 columns):

```text
person_id, first_name, last_name, gender, age, address_line_1, address_line_2,
street, postal_code, city, state, country, phone_number, email,
individual_yearly_income, marital_status, education, employment_status,
resident_status, resident_type, family_member_count,
number_of_children_in_family, number_of_adults_in_family, ethnicity,
type_of_employment, occupation_industry, family_yearly_income, religion
```

Campaign `customer_id` values must exist in `customers`. For demographics,
children plus adults must equal `family_member_count`; no customer relationship
is expected or created.

## Index and reconcile imported data

After all three imports complete, create or verify the required indexes and run
the full reconciliation:

```powershell
.\.venv\Scripts\python.exe scripts\validate_data.py
```

The command is idempotent, reports the configured expected target beside each
actual count, records approximate query timings, and exits nonzero only when a
structural error is found. For machine-readable output:

```powershell
.\.venv\Scripts\python.exe scripts\validate_data.py --json
```

Statuses are `NOT_LOADED`, `OK`, `WARNING`, and `ERROR`. Customer count is an
approximate target by default, while campaign-sales and demographics counts
require exact matches. These policies can be changed through environment
configuration without changing SQL.

## Start the application

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open:

- Application: <http://127.0.0.1:8000/>
- API documentation: <http://127.0.0.1:8000/docs>
- Health endpoint: <http://127.0.0.1:8000/api/health>

The frontend is served by FastAPI; no frontend build command is required.

The Overview and Data Status views display only API-backed values. Empty datasets
are labeled `Not loaded`, and backend failures show an error banner with a retry
action. Later-phase navigation remains visibly disabled. A complete Data Status
reconciliation scans the 5-million-row prospect universe and may take about 30
seconds; the browser reuses the completed result for five minutes unless the user
explicitly runs the checks again.

## Data and reference APIs

The Phase 1 API exposes aggregate status and reference data only; it does not
provide customer- or person-level dump endpoints.

- `GET /api/data/status` — reconciliation and latest import state per dataset
- `GET /api/data/summary` — application-level counts and campaign coverage
- `GET /api/data/imports?limit=20&offset=0` — recent import history (`limit` 1–100)
- `GET /api/reference/states` — demographic counts by state
- `GET /api/reference/campaigns?limit=100&search=...` — campaign summaries
- `GET /api/reference/products?limit=100&search=...` — product summaries

Database and import source locations in responses are display-safe filenames,
not arbitrary filesystem paths. Interactive OpenAPI documentation remains
available at <http://127.0.0.1:8000/docs>.

## Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Configuration

Configuration is read from environment variables with safe local defaults. See
`.env.example` for supported values:

- `APP_NAME`
- `APP_VERSION`
- `APP_ENV`
- `HOST`
- `PORT`
- `DATABASE_PATH`
- `DATABASE_BUSY_TIMEOUT_MS`
- `EXPECTED_CUSTOMER_ROWS`
- `EXPECTED_CAMPAIGN_SALES_ROWS`
- `EXPECTED_DEMOGRAPHIC_ROWS`
- `CUSTOMER_COUNT_EXACT_REQUIRED`
- `CAMPAIGN_SALES_COUNT_EXACT_REQUIRED`
- `DEMOGRAPHIC_COUNT_EXACT_REQUIRED`
- `LOG_LEVEL`

The example file is documentation only; no secrets are required for this POC.

## Troubleshooting

- **PowerShell parser error near `.venv`:** separate environment assignment from
  execution: `$env:OUTDIR = (Resolve-Path .\data).Path`, then run
  `.\.venv\Scripts\python.exe ...` on the next line.
- **Source file does not exist/schema mismatch/corrupt gzip:** confirm the exact
  filename under `data/`, decompress or regenerate if necessary, and compare its
  header to the frozen schemas above. Failed attempts are recorded in
  `data_import_runs` when the database is writable.
- **Target already contains rows:** this is intentional duplicate protection.
  Use a new database for a clean load, or use `--replace` only after reviewing
  the documented dataset-specific behavior.
- **Foreign-key failure:** load customers before campaign sales and ensure every
  campaign `customer_id` exists in the customer file.
- **Database is locked/unavailable:** stop other writers, verify
  `DATABASE_PATH`, directory permissions, and free disk space, then retry. The
  browser health endpoint reports a degraded state instead of exposing raw DB
  details.
- **Data Status takes tens of seconds:** a full reconciliation intentionally
  scans data-quality rules across the 5-million-row universe. The UI displays a
  loading state and reuses the result for five minutes.
- **Port 8000 is in use:** set another port, for example
  `.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8001`.

## Current endpoints

- `GET /api/health`
- `GET /api/version`
- `GET /api/data/status`
- `GET /api/data/summary`
- `GET /api/data/imports`
- `GET /api/reference/states`
- `GET /api/reference/campaigns`
- `GET /api/reference/products`
- `GET /`

## Data generators

The shared environment contains the Python packages required by all three scripts
under `data_generation_scripts/`. Generators are not run automatically during
application setup. Generate source data explicitly before the real import flow.

## Phase 1 scope boundary

Phase 1 establishes the application, SQLite, data ingestion, reconciliation,
summary APIs, and the Overview/Data Status UI. PU learning, propensity scoring,
audience selection, campaign execution, authentication, and external activation
integrations are not part of this phase.

## Next phase

Phase 2 may build governed analytical or modeling workflows on this verified
foundation. Its design and implementation require a separate approved prompt;
no Phase 2 code is included here.
