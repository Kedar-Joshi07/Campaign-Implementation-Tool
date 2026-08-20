# Campaign Implementation Intelligence

Campaign Implementation Intelligence is a local proof of concept for building,
validating, and later extending a campaign-analysis data foundation. Phase 1 uses
FastAPI, SQLite, and a static HTML/CSS/Vanilla JavaScript frontend.

This repository currently contains the application shell and SQLite foundation.
Data import, reconciliation, and database-backed UI values are intentionally left
for the remaining Phase 1 steps.

## Prerequisites

- Python 3.11 or newer
- PowerShell commands below assume Windows

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

## Start the application

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open:

- Application: <http://127.0.0.1:8000/>
- API documentation: <http://127.0.0.1:8000/docs>
- Health endpoint: <http://127.0.0.1:8000/api/health>

The frontend is served by FastAPI; no frontend build command is required.

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
- `LOG_LEVEL`

The example file is documentation only; no secrets are required for this POC.

## Current endpoints

- `GET /api/health`
- `GET /api/version`
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
