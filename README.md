# Campaign Implementation Intelligence

Campaign Implementation Intelligence is a local proof of concept for building,
validating, and extending a campaign-analysis data foundation. It uses FastAPI,
SQLite, and a static HTML/CSS/Vanilla JavaScript frontend.

This repository contains the completed Phase 1 data foundation and Phase 2
historical campaign analysis. Users can inspect aggregate historical performance,
define a reproducible distinct-customer cohort, distinguish known-positive from
unlabeled customers, review aggregate profiles, and reopen saved analysis runs.

## Prerequisites

- Git and [Git LFS](https://git-lfs.com/)
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
data/                    Tracked source datasets/samples; ignored local SQLite files
data_generation_scripts/ Explicitly run synthetic-data generators
docs/                    Implementation and handoff documentation
frontend/                Static HTML, CSS, and Vanilla JavaScript UI
logs/                    Optional local logs
Prompts/                 Frozen implementation prompts and progress evidence
scripts/                 DB initialization, import, and reconciliation CLIs
tests/                   Unit, integration, API, and frontend contract tests
```

## One-time setup

For a fresh clone, install Git LFS support and materialize the tracked Phase 1
GZIP objects before importing data:

```powershell
git clone https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git
Set-Location .\Campaign-Implementation-Tool
git lfs install
git lfs pull
git lfs ls-files
```

On macOS or Linux, use `cd Campaign-Implementation-Tool`; the three `git lfs`
commands are otherwise the same.

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

Create or verify the current schema (version 2):

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

## Import Phase 1 data

The exact customer, campaign-sales, and demographic GZIP inputs are tracked with
Git LFS and can be imported directly after `git lfs pull`; generator execution is
not required for the normal setup flow.

### LFS data manifest

| File | Expected bytes | SHA-256 |
|---|---:|---|
| `customer_master_125000.csv.gz` | `6145052` | `5e80e1f25e433373f5f4b066e4d8d3a723cb4ae8d5af028895ea469d3c533a2e` |
| `campaign_sales_570000.csv.gz` | `6465596` | `16aace571676765f358ecb3e981ec273ae08653fc9397229856cc4e27dfd500c` |
| `usa_demographic_synthetic_5000000_rows.csv.gz` | `331342839` | `b5ff7051dda391f60188838ff91cb13e75c1cd855ef57461b2b0ad0a0786cd1d` |

Allow disk space for approximately 344 MB of compressed LFS inputs, about 2.9 GB
for the populated SQLite database, and additional working headroom for imports,
indexes, WAL files, tests, and temporary validation databases. Generated source
datasets, samples, masters, and summaries under `data/` are tracked; local
SQLite `.db`, `.db-wal`, and `.db-shm` files remain ignored.

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

Before any explicit replacement clears existing rows, every source is opened and
its header is checked. Replacement sources also receive a complete streaming
structural/readability pass, including all multipart files, so wrong headers,
malformed CSV structure, and truncated/corrupt GZIP streams preserve the existing
target data. This preflight remains memory-bounded and does not increment import
counters. Business-rule validation still occurs during the actual import pass.

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
approximate target with a configurable ±5% tolerance by default, while
campaign-sales and demographics counts require exact matches. Approximate bounds
are inclusive and deterministic: the minimum is rounded up with
`ceil(expected × (1 - tolerance/100))`, and the maximum is rounded down with
`floor(expected × (1 + tolerance/100))`. Counts outside that range are
`WARNING`. These policies can be changed through environment configuration
without changing SQL.

## Start the application

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open:

- Application: <http://127.0.0.1:8000/>
- API documentation: <http://127.0.0.1:8000/docs>
- Health endpoint: <http://127.0.0.1:8000/api/health>

The frontend is served by FastAPI; no frontend build command is required.

The Overview, Data Status, and Historical Analysis views display only API-backed
aggregate values. Empty datasets are labeled clearly, and backend failures show a
recoverable error with retry. Model Training, Audience Explorer, and Campaigns
remain disabled as later-phase work. A complete Data Status reconciliation scans
the 5-million-row prospect universe and may take about 30 seconds; the browser
reuses the completed result for five minutes unless the user explicitly reruns it.

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

## Phase 2 historical analysis

Schema version 2 is an additive, idempotent migration. It preserves every Phase 1
table and row, adds `historical_analysis_runs`, and adds a restrained set of
filter/list indexes. Application database initialization migrates version 1 to
version 2 transactionally; the metadata version advances only after migration
success.

Analysis is performed at distinct historical-customer grain. Matching
`campaign_sales` rows are observations. A selected customer is positive when any
matching observation satisfies the chosen definition; every other selected
customer is unlabeled. Unlabeled does not mean confirmed negative, and activity
outside the submitted filters cannot change the current label. Every completed
run enforces:

```text
positive_customer_count + unlabeled_customer_count = selected_customer_count
```

The supported conversion definitions are:

| Value | A matching observation is positive when |
|---|---|
| `ATTRIBUTED_PURCHASE` | `campaign_attributed_sale_flag = 1` and `purchase_flag = 1` |
| `ANY_PURCHASE` | `purchase_flag = 1` |
| `RESPONSE` | `response_flag = 1` |

`ATTRIBUTED_PURCHASE` and `contacted_only=true` are the defaults. Dates are
inclusive and must stay within the available history. An omitted date range is
normalized to the available minimum/maximum and persisted; the normalized end
date is also the deterministic age reference date.

Phase 2 exposes five aggregate-only endpoints:

- `GET /api/historical/options`
- `GET /api/historical/overview`
- `POST /api/historical/analyses`
- `GET /api/historical/analyses?limit=20&offset=0`
- `GET /api/historical/analyses/{analysis_run_id}`

Example requests:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/historical/options
Invoke-RestMethod http://127.0.0.1:8000/api/historical/overview

$body = @{
  analysis_name = "Email attributed purchasers"
  campaign_ids = @()
  product_ids = @()
  product_categories = @()
  campaign_channels = @("Email")
  campaign_types = @()
  contact_date_from = "2024-01-01"
  contact_date_to = "2025-12-31"
  contacted_only = $true
  conversion_definition = "ATTRIBUTED_PURCHASE"
} | ConvertTo-Json

Invoke-RestMethod http://127.0.0.1:8000/api/historical/analyses `
  -Method Post -ContentType "application/json" -Body $body
```

In the UI, open **Historical Analysis**, choose zero or more real filter values,
select the conversion meaning, and choose **Analyze population**. The synchronous
request saves a bounded aggregate snapshot and renders KPIs, trends, breakdowns,
four aggregate profile groups, and a recent-run list. Completed runs can be
reopened without recomputing them. No person-level rows or customer-ID list are
returned or stored as the Phase 3 handoff.

Local full-data Step 7 measurements on 570,000 observations were: options
4.44s first/3.84s repeat, overview 12.28s first/9.50s repeat, broad default
analysis 53.91s first/60.13s repeat, narrow campaign/product analysis 15.07s
first/14.40s repeat, recent list about 0.05s, and saved-run reopen about 0.05s.
Machine load and OS cache materially affect these synchronous POC timings. The
overview and broad analysis exceed the approximate warm targets. Query plans
show full scans and temporary aggregate B-trees for broad work; narrow filters
use the existing `(campaign_id, product_id, pu_label)` index. No additional
composite index was justified.

## Run tests

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app scripts tests
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
- `CUSTOMER_COUNT_TOLERANCE_PERCENT`
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
- **A GZIP file is about 130 bytes or starts with
  `version https://git-lfs.github.com/spec/v1`:** it is an unresolved Git LFS
  pointer, not compressed CSV data, and imports may report `Not a gzipped file`
  or a similar read error. Run `git lfs install`, then `git lfs pull`, and verify
  the materialized objects with `git lfs ls-files` and the manifest above.
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
- `GET /api/historical/options`
- `GET /api/historical/overview`
- `POST /api/historical/analyses`
- `GET /api/historical/analyses`
- `GET /api/historical/analyses/{analysis_run_id}`
- `GET /`

## Data generators

The shared environment contains the Python packages required by all three scripts
under `data_generation_scripts/`. The generators are optional reproducibility and
regeneration tools; they are not run automatically and are not required when the
committed Git LFS objects are present. If regeneration is explicitly needed, run
the scripts separately and validate the resulting files before replacement.

## Known limitations and Phase 3 boundary

- Historical analytics run synchronously in this local POC; broad full-history
  work can take about a minute on the reference machine.
- Saved results are aggregate snapshots and do not auto-refresh if source data
  changes.
- Unlabeled customers are not confirmed negatives.
- Analysis quality depends on synthetic historical data; no causal inference is
  claimed, and displayed metrics are descriptive rather than model-performance
  metrics.
- No model is trained, no prospect is scored, and no historical `customer_id` is
  linked or inferred to a demographic `person_id`.
- SQLite and the local single-process/single-user design are not production
  multi-user infrastructure.
- One upstream Starlette/httpx deprecation warning may appear in the test suite.

## Phase 3 handoff

The only authoritative handoff is an `analysis_run_id` referencing a valid
`COMPLETED` row. The saved filters define how a future approved Phase 3 may
reconstruct the distinct-customer cohort, while `results_json` is an explanatory
aggregate snapshot rather than a training matrix. Before any training, Phase 3
must recompute and reconcile selected/positive/unlabeled counts. Model design,
training, evaluation, artifact persistence, prospect scoring, audience selection,
campaign creation, and export remain outside this repository's implemented scope.
See `Prompts/phase2_prompt_pack/12_PHASE_3_HANDOFF_CONTRACT.md` for the frozen
contract.
