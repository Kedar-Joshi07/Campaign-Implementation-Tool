# Campaign Implementation Intelligence

Campaign Implementation Intelligence is a local proof of concept for building,
validating, and extending a campaign-analysis data foundation. It uses FastAPI,
SQLite, and a static HTML/CSS/Vanilla JavaScript frontend.

This repository contains implemented and frozen Phase 1 through Phase 5
capabilities: data foundation, historical campaign analysis, governed
positive-unlabeled (PU) modeling, asynchronous training/scoring orchestration,
and bounded 5-million-row prospect scoring. Users can inspect aggregate
historical performance, define reproducible distinct-customer cohorts,
distinguish known-positive from unlabeled customers, reopen saved analyses,
train governed local look-alike models, and execute provenance-aware prospect
scoring runs.

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
artifacts/models/        Ignored local Phase 3 joblib model artifacts
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

Create or verify the current schema (version 8):

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
| `usa_demographic_synthetic_5000000_rows.csv.gz` | `333670576` | `7f896e56e7d0b16149718111cabc53868ecd1584429a0f76e2480e4c6bfe9c35` |

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

Completed imports persist source checksums and row counts. The current runtime
uses this provenance in historical-analysis, training, and scoring workflows to
enforce source-currentness and to prevent silent reuse of stale completed runs
after source drift.

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
recoverable error with retry. Model Training is enabled in Phase 4 for
asynchronous governed training orchestration; Audience Explorer and Campaigns
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

## Phase 3 PU modeling

Schema version 3 additively and transactionally migrates version 2 and adds the
governed `model_runs` lifecycle. It does not add a model BLOB or propensity-score
table. A model run references exactly one valid `COMPLETED` Phase 2
`analysis_run_id`; current source rows are reconstructed with the saved Phase 2
filters and counts must reconcile before training can continue.

One training row represents one distinct historical customer. The PU label is:

- `1`: known positive under the saved conversion definition;
- `0`: unlabeled, not a confirmed negative.

Campaign behavior determines cohort membership and the PU label only. It is not
used as a predictive feature. The versioned feature contract contains exactly 11
prospect-compatible attributes, in this order:

```text
age, gender, state, individual_yearly_income, marital_status, education,
employment_status, resident_status, resident_type, family_member_count,
type_of_employment
```

`age` uses the saved analysis end date, never the current date. Customer IDs,
names, contact details, ZIP/address fields, campaign/product behavior, response,
spend, margin, `pu_label`, and independent-prospect attributes are excluded from
model inputs and artifacts. Numeric imputation/scaling and categorical one-hot
encoding are fitted on the training partition only; unknown future categories
are ignored safely.

The default deterministic split uses seed `42`, a 20% validation partition, and
stratification on the PU label. Under model-role policy version 2, Phase 3 fits:

- bounded Bagging PU as the mandatory PRIMARY genuine-PU candidate;
- Elkan–Noto logistic regression as CHALLENGER_1;
- a naive logistic baseline that treats unlabeled as negative for diagnostic
  comparison only and is never eligible for official selection.

The tested local environment uses Python 3.12.0, NumPy 2.3.3, pandas 2.3.3,
scikit-learn 1.7.1, pulearn 0.0.12, and joblib 1.5.2. Exact runtime versions are
persisted per model run. scikit-learn and pulearn use permissive BSD-style
licenses, and joblib uses BSD 3-Clause; these libraries introduce no commercial
runtime service requirement.

### Train a model

First create or reuse a completed Phase 2 analysis, then run:

```powershell
.\.venv\Scripts\python.exe scripts\train_pu_model.py `
  --analysis-run-id 10 `
  --model-name "Holiday Electronics Lookalike" `
  --json
```

Useful options are `--random-seed`, `--validation-fraction`,
`--run-elkan-challenger`/`--no-run-elkan-challenger`, and `--database-path`. The CLI
initializes schema v3, creates a `RUNNING` row, reconstructs and reconciles the
cohort, trains/evaluates candidates, atomically writes and reload-verifies the
artifact, persists SHA-256 plus a relative path, and marks the row `COMPLETED`.
An unrecoverable post-insert error removes the incomplete artifact, records a
bounded internal diagnostic locally, marks the run `FAILED`, and returns nonzero.
JSON mode is bounded and does not expose the internal traceback or absolute
filesystem paths.

Artifacts have this ignored runtime layout:

```text
artifacts/models/model_run_000001/pu_model.joblib
```

The payload contains only the artifact/feature-contract versions and hash, raw
feature order, fitted preprocessor, selected fitted genuine-PU estimator, and
selected-candidate name. It contains no raw training rows, customer-ID list,
PII, or validation score vector. Loading verifies the relative path, file
SHA-256, payload contract, and selected candidate before returning the model.

### Evaluation caveat and reproducibility

Unlabeled rows may contain unknown positives, so ordinary accuracy, specificity,
or “true precision” would be misleading. Evaluation explicitly labels ROC-AUC
and average precision as observed-label diagnostics. Under role-governed policy
version 2, the valid nonconstant PRIMARY Bagging candidate is selected while
challenger and diagnostic metrics/deltas are persisted for comparison. These are
synthetic-POC ranking diagnostics, not real-world population-performance or
calibrated-probability claims.

Full-data same-seed runs from analysis 10 produced identical split fingerprints,
feature-contract hash, selected `BAGGING_PU` candidate, non-runtime metrics,
bounded-sample scores, and artifact SHA-256. Exact timings vary with machine load
and are recorded as evidence rather than an SLA.

## Phase 5 asynchronous model training and prospect scoring

Schema version 5 additively extends version 4 with prospect-scoring persistence
(`scoring_runs`, `propensity_scores`) and scoring-specific job stages, while
preserving all earlier tables and rows. The application uses a lazy
`ProcessPoolExecutor(max_workers=1)` and enforces one active compute job at a
time across training and scoring. Job lifecycle state is durable (`QUEUED`,
`RUNNING`, `COMPLETED`, `FAILED`) with monotonic progress and safe public
messages.

On startup, stale active jobs left in `QUEUED` or `RUNNING` are reconciled to
`FAILED` with bounded restart messages; stale `RUNNING` scoring runs are also
failed defensively. Terminal rows remain unchanged. Failures in executor
submission, worker execution, delegated training, scoring, or artifact
verification all transition cleanly to `FAILED` without fake-success states.

Phase 5 model/scoring API endpoints:

- `POST /api/models/train`
- `POST /api/models/{model_run_id}/score`
- `GET /api/jobs/{job_id}`
- `GET /api/models`
- `GET /api/models/{model_run_id}`
- `GET /api/models/{model_run_id}/scoring-status`
- `GET /api/models/training-options`
- `GET /api/scoring-runs`
- `GET /api/scoring-runs/{scoring_run_id}`

Contract highlights:

- Submit returns `202 Accepted` with persisted queued snapshot details.
- When a compute job is already active, conflicting submit calls return `409 Conflict`.
- Model detail verifies persisted artifact existence and SHA-256 safely.
- Scoring status/list/detail expose aggregate-only readiness and run summaries.
- Artifact drift is surfaced as verification failure in detail payloads.
- No customer- or person-level raw rows are returned by training/job/model/scoring APIs.

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
- `POST /api/models/train`
- `POST /api/models/{model_run_id}/score`
- `GET /api/jobs/{job_id}`
- `GET /api/models`
- `GET /api/models/{model_run_id}`
- `GET /api/models/{model_run_id}/scoring-status`
- `GET /api/models/training-options`
- `GET /api/scoring-runs`
- `GET /api/scoring-runs/{scoring_run_id}`
- `GET /`

## Data generators

The shared environment contains the Python packages required by all three scripts
under `data_generation_scripts/`. The generators are optional reproducibility and
regeneration tools; they are not run automatically and are not required when the
committed Git LFS objects are present. If regeneration is explicitly needed, run
the scripts separately and validate the resulting files before replacement.

## Known limitations and Phase 5 boundary

### Post-Phase-3 algorithm-role policy update (2026-08-21)

New model runs use model-role policy version 2 and evaluation contract version 2:

- **PRIMARY:** `BAGGING_PU` with a Logistic Regression base estimator. It is
  mandatory, cannot be disabled by challenger controls, and is the selected
  artifact whenever it satisfies the finite, nonconstant primary contract.
- **CHALLENGER_1:** `ELKAN_NOTO_LOGISTIC` with Logistic Regression. It runs by
  default and can be disabled with `--no-run-elkan-challenger`. Its metrics and
  deltas are recorded, but it cannot silently replace the governed primary.
- **DIAGNOSTIC_CONTROL:** `NAIVE_PU_LABEL_BASELINE`. It temporarily treats
  unlabeled observations as negative for diagnostic comparison only and is
  permanently ineligible for official selection.

Unlabeled still means unlabeled, not a confirmed negative. All observed-label
diagnostics measure separation from unlabeled observations, not true-negative
performance. The output is a look-alike/PU ranking score, not a guaranteed
calibrated purchase probability. Historical role-policy-v1 rows and artifacts
remain unchanged and loadable.

- Historical analytics run synchronously in this local POC; broad full-history
  work can take about a minute on the reference machine.
- Saved results are aggregate snapshots and do not auto-refresh if source data
  changes.
- Unlabeled customers are not confirmed negatives.
- Analysis quality depends on synthetic historical data; no causal inference is
  claimed. Phase 3 evaluation measures synthetic observed-label ranking, not
  ground-truth population performance or calibrated conversion probability.
- Phase 3 trains and persists a customer-history-derived PU model, but no
  prospect is scored and no historical `customer_id` is linked or inferred to a
  demographic `person_id`.
- SQLite and the local single-process/single-user design are not production
  multi-user infrastructure.
- Asynchronous training is intentionally bounded to one worker process and one
  active training job at a time; this is a correctness/safety profile, not a
  high-throughput scheduler.
- Model artifacts use local joblib serialization and must be treated as trusted
  local files; the verified loader rejects missing, corrupt, or incompatible
  artifacts but is not a remote model registry.

## Phase 5 handoff

This Phase 5 handoff supersedes the earlier Phase 4 handoff wording while
preserving all Phase 4 safety and boundary constraints.

The authoritative Phase 5 input is a `model_run_id` whose row is `COMPLETED`,
references a valid completed `analysis_run_id`, matches the frozen feature
contract, and has an existing checksum-verified artifact. For role-policy-v2
runs, `BAGGING_PU` remains PRIMARY and selected, while challenger/diagnostic
metrics are retained for governance review.

Step 7 hardening was rerun after demographic age-contract remediation and
completed successfully through the real scoring API path. For preserved
historical evidence, `model_run_id=7`, `job_id=16`, and `scoring_run_id=5`
completed with exact 5M reconciliation and deterministic sample verification.

The current canonical pre-Phase-6 baseline is the source-current completed run
for `model_run_id=8`: `job_id=21`, `scoring_run_id=8`,
`demographic_import_id=5`, and
`demographic_source_checksum=7d57a02add836f448ed2d937e60bb6c0d38402c3c82e6f219b54e904e0e0c2db`.

Before any Phase 6 audience workflow, consumers must verify the scoring run is
canonical for the currently loaded demographics source: completed status,
source-checksum match, demographic envelope/count match, and preserved model
artifact/feature-governance compatibility. Stale completed scoring runs remain
audit history only.

Before any prospect scoring phase, consumers must verify artifact path, SHA-256,
payload compatibility, feature-contract version/hash, and selected estimator.
Phase 5 boundary constraints remain in force: no customer/person linkage and no
automatic addition of Audience Explorer, campaign construction/persistence,
export, or activation adapters unless separately approved. See
`Prompts/phase4_prompt_pack/13_PHASE_5_HANDOFF_CONTRACT.md` and
`docs/PHASE_4_IMPLEMENTATION_SUMMARY.md`.
