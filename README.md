# Campaign Implementation Intelligence

Campaign Implementation Intelligence is a local FastAPI + SQLite proof of concept that implements a full Phase 1 to Phase 7 synthetic marketing workflow:

1. Synthetic source data generation and ingestion.
2. Phase 1 data foundation and reconciliation.
3. Phase 2 historical cohort analysis at aggregate-only grain.
4. Phase 3 governed positive-unlabeled (PU) model training.
5. Phase 5 asynchronous 5M demographic prospect scoring.
6. Phase 6 Audience Explorer filtering, search, profile, and saved audiences.
7. Phase 7 Campaign Builder draft/finalize/currentness and deterministic target-list export.

All source data in this repository is synthetic. The historical customer universe and the demographic prospect universe are intentionally independent.

- Historical behavior uses customer_id.
- Prospect scoring and campaign export use person_id.
- The application does not create or infer a customer_id to person_id linkage.

## Product flow (Phase 1 to 7)

1. Load synthetic customer, campaign-sales, and demographic source files.
2. Import data into SQLite with strict schema/header validation.
3. Reconcile row counts, structural constraints, and required indexes.
4. Create historical analyses and persist aggregate-only snapshots.
5. Train governed PU models from historical customer cohorts.
6. Score the 5,000,000-row demographic prospect universe asynchronously.
7. Prepare audience rank boundaries and analytics snapshots.
8. Explore audiences, estimate/select cohorts, and save immutable audience definitions.
9. Build campaigns from current saved audiences, finalize, and export EMAIL or DIRECT_MAIL target lists.

## Technology stack

- Backend: FastAPI
- Data store: SQLite
- ML stack: scikit-learn, pulearn, pandas, numpy, joblib
- Frontend: static HTML + CSS + vanilla JavaScript served by FastAPI
- Test stack: pytest

## Architecture

The runtime follows Router -> Schema -> Service -> Repository -> SQLite layering:

- Routers define HTTP contracts and map domain errors to stable status codes.
- Schemas define typed request/response shapes and enforce field contracts.
- Services implement domain logic, currentness checks, and workflow rules.
- Repositories own SQL reads/writes and persistence boundaries.
- Schema initialization/migrations are additive and idempotent.

## Current versions and frozen contracts

- Application version default: 0.1.0
- Current SQLite schema version: 12
- Feature contract version: 1
- Feature contract SHA-256: a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535
- Model role policy version: 2
- Evaluation contract version: 2
- Audience filter contract version: 1
- Audience rank contract version: 1
- Audience selection contract version: 1
- Audience analytics contract version: 1
- Campaign contract version: 1
- Campaign export contract version: 1
- Campaign member resolution contract version: 1
- Campaign export snapshot contract version: 1
- Export profiles:
  - EMAIL -> EMAIL_CONTACT_V1
  - DIRECT_MAIL -> DIRECT_MAIL_CONTACT_V1

## Repository layout

```text
app/                     FastAPI routers, schemas, services, repositories, DB code
artifacts/models/        Local model artifacts (ignored in git)
data/                    Canonical synthetic sources, references, and local SQLite file
data_generation_scripts/ Deterministic synthetic data generators
frontend/                Static UI for overview, analysis, modeling, audience, campaigns
docs/                    Phase implementation summaries and evidence indexes
logs/                    Local runtime logs
Prompts/                 Prompt packs and freeze workflows
scripts/                 Operational CLIs and validation tooling
tests/                   API, service, repository, and UI contract tests
```

## Prerequisites

- Git and Git LFS
- Python 3.11+
- Windows PowerShell examples are shown below

## One-time setup

```powershell
git clone https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git
Set-Location .\Campaign-Implementation-Tool
git lfs install
git lfs pull
git lfs ls-files

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Canonical synthetic source manifest

These files are authoritative tracked inputs for reproducible local setup.

| File | Expected rows | Bytes | SHA-256 |
|---|---:|---:|---|
| data/customer_master_125000.csv.gz | 125,000 | 6,145,052 | 5e80e1f25e433373f5f4b066e4d8d3a723cb4ae8d5af028895ea469d3c533a2e |
| data/campaign_sales_570000.csv.gz | 570,000 | 6,466,293 | d3997bf8e4d235dd002af3f50b3875532c93954ac94571da5ad007118fd84c4f |
| data/usa_demographic_synthetic_5000000_rows.csv.gz | 5,000,000 | 333,670,576 | 7f896e56e7d0b16149718111cabc53868ecd1584429a0f76e2480e4c6bfe9c35 |

If a .gz file is around 130 bytes and contains git-lfs pointer text, run git lfs pull before imports.

## Initialize and inspect the database

```powershell
.\.venv\Scripts\python.exe scripts\init_db.py
.\.venv\Scripts\python.exe scripts\init_db.py --inspect
```

Initialization is idempotent and creates/verifies schema version 12.

## Import data (enforced order)

```powershell
.\.venv\Scripts\python.exe scripts\import_customers.py --file .\data\customer_master_125000.csv.gz
.\.venv\Scripts\python.exe scripts\import_campaign_sales.py --file .\data\campaign_sales_570000.csv.gz
.\.venv\Scripts\python.exe scripts\import_demographics.py --file .\data\usa_demographic_synthetic_5000000_rows.csv.gz
```

Optional multipart demographics import:

```powershell
.\.venv\Scripts\python.exe scripts\import_demographics.py --input-dir .\data\demographic_parts --pattern "*.csv.gz"
```

Import guarantees:

- Strict header/schema validation before publish.
- Bounded streaming reads and batched writes.
- Explicit replacement required via --replace.
- Failed attempts are recorded and do not silently become published source.
- Completed source checksums are persisted for cross-phase currentness checks.

## Reconcile and verify data quality

```powershell
.\.venv\Scripts\python.exe scripts\validate_data.py
.\.venv\Scripts\python.exe scripts\validate_data.py --json
```

Default configured expected counts:

- Customers: 125000 (approximate target, tolerance-configurable)
- Campaign sales: 570000 (exact)
- Demographics: 5000000 (exact)

## Run the application

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

- App: http://127.0.0.1:8000/
- OpenAPI docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/api/health

## UI navigation

Current UI sections in frontend/index.html:

- Overview
- Data Status
- Historical Analysis
- Model Training & Prospect Scoring
- Audience Explorer
- Campaigns

## API surface

System and data:

- GET /api/health
- GET /api/version
- GET /api/data/status
- GET /api/data/summary
- GET /api/data/imports
- GET /api/reference/states
- GET /api/reference/campaigns
- GET /api/reference/products

Historical analysis:

- GET /api/historical/options
- GET /api/historical/overview
- POST /api/historical/analyses
- GET /api/historical/analyses
- GET /api/historical/analyses/{analysis_run_id}

Model training and scoring:

- POST /api/models/train
- POST /api/models/{model_run_id}/score
- GET /api/jobs/{job_id}
- GET /api/models/training-options
- GET /api/models
- GET /api/models/{model_run_id}
- GET /api/models/{model_run_id}/scoring-status
- GET /api/scoring-runs
- GET /api/scoring-runs/{scoring_run_id}

Audience Explorer and saved audiences:

- POST /api/audience/runs/{scoring_run_id}/prepare
- GET /api/audience/runs/{scoring_run_id}/preparation-status
- GET /api/audience/runs
- GET /api/audience/options
- POST /api/audience/estimate
- POST /api/audience/search
- POST /api/audience/profile
- POST /api/audiences
- GET /api/audiences
- GET /api/audiences/{audience_id}
- GET /api/audiences/{audience_id}/currentness

Campaign Builder and export:

- GET /api/campaigns/options
- POST /api/campaigns
- GET /api/campaigns
- GET /api/campaigns/{campaign_id}
- PATCH /api/campaigns/{campaign_id}
- GET /api/campaigns/{campaign_id}/currentness
- POST /api/campaigns/{campaign_id}/finalize
- GET /api/campaigns/{campaign_id}/exports
- GET /api/campaigns/{campaign_id}/export.csv?acknowledge_pii=true

## Phase summary

- Phase 1: import, reconciliation, aggregate data/reference APIs.
- Phase 2: bounded historical cohort analysis and saved aggregate snapshots.
- Phase 3: governed PU training and artifact governance.
- Phase 4: asynchronous job orchestration groundwork.
- Phase 5: asynchronous prospect scoring and scoring-run lifecycle.
- Phase 6: audience rank boundaries, filters/search/profile, immutable saved audiences.
- Phase 7: campaign draft/finalize/currentness and deterministic export with audit events.

## PU model methodology

Training cohort labels:

- Positive: customer has at least one matching converted observation under selected definition.
- Unlabeled: selected customer without matching converted observation.

The model uses exactly 11 prospect-compatible raw features in frozen order:

1. age
2. gender
3. state
4. individual_yearly_income
5. marital_status
6. education
7. employment_status
8. resident_status
9. resident_type
10. family_member_count
11. type_of_employment

Explicit feature exclusions include customer_id, person_id, names, contact fields, campaign/product behavior fields, and protected/extra demographic attributes not in the 11-feature contract.

## Phase 3 compatibility notes

- Schema version 3 introduced the model run lifecycle as the additive PU training boundary.
- CLI entrypoint for governed training is scripts\train_pu_model.py.
- The PU label semantics remain unlabeled, not a confirmed negative.
- Evaluation outputs are observed-label diagnostics and must be interpreted as ranking diagnostics, not calibrated probability claims.
- Reference artifact layout example: artifacts/models/model_run_000001/pu_model.joblib.
- Phase 4 handoff remains the boundary where asynchronous orchestration extends the training workflow.

## Scoring, ranking, and audience analytics

- Scoring runs snapshot demographic source provenance and model artifact governance state.
- Audience preparation persists exactly 100 rank boundaries for rank contract version 1.
- Audience analytics snapshots (contract version 1) power bounded options, estimate, profile, and saved-audience reopen workflows.
- Saved audiences are immutable definitions with resolved counts and persisted lineage checksums.

## Campaign lifecycle and export governance

Campaign states:

- DRAFT
- FINALIZED

Rules:

- Campaigns are created from current saved audiences only.
- Finalize requires currentness checks to pass.
- Export requires FINALIZED status and explicit acknowledge_pii=true.
- Export events persist metadata-only audit details (counts, checksums, currentness state).

Supported export profiles:

- EMAIL_CONTACT_V1: person_id, score/rank fields, name, email
- DIRECT_MAIL_CONTACT_V1: person_id, score/rank fields, name, mailing address fields

Prohibited fields include ethnicity, religion, occupation_industry, family_yearly_income, number_of_children_in_family, number_of_adults_in_family, customer_id, and phone_number.

Scope boundary: this POC stops at target-list export. It does not implement send/activation platform workflows.

## Synthetic data generators

The committed LFS sources are enough for normal setup. Generators are for controlled regeneration.

Customer generator (default seed 20260819):

```powershell
.\.venv\Scripts\python.exe data_generation_scripts\generate_us_customer_master.py --n-customers 125000 --seed 20260819 --outdir .\data
```

Campaign-sales generator (default seed 20260820):

```powershell
.\.venv\Scripts\python.exe data_generation_scripts\generate_campaign_sales.py --customer-file .\data\customer_master_125000.csv.gz --n-rows 570000 --seed 20260820 --outdir .\data
```

Demographic generator (env-driven, default seed 20260818):

```powershell
$env:SEED = "20260818"
$env:N_ROWS = "5000000"
$env:OUTDIR = (Resolve-Path .\data).Path
$env:OUT_NAME = "usa_demographic_synthetic_5000000_rows.csv.gz"
.\.venv\Scripts\python.exe data_generation_scripts\generate_us_demographic_synthetic.py
```

## Tests and validation gates

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q app scripts tests
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

Most recent full regression evidence records 457 passing tests in the freeze baseline artifacts.

## Configuration

See .env.example for supported variables:

- APP_NAME, APP_VERSION, APP_ENV
- HOST, PORT
- DATABASE_PATH, DATABASE_BUSY_TIMEOUT_MS
- EXPECTED_CUSTOMER_ROWS, EXPECTED_CAMPAIGN_SALES_ROWS, EXPECTED_DEMOGRAPHIC_ROWS
- CUSTOMER_COUNT_EXACT_REQUIRED, CUSTOMER_COUNT_TOLERANCE_PERCENT
- CAMPAIGN_SALES_COUNT_EXACT_REQUIRED, DEMOGRAPHIC_COUNT_EXACT_REQUIRED
- LOG_LEVEL

## POC limitations

- Single-node SQLite runtime and bounded single-worker compute execution profile.
- No customer-person identity resolution.
- No activation/send channel integrations.
- Local artifact storage and local operational posture, not a multi-tenant deployment profile.
- Timing evidence is environment-dependent and not an SLA.
