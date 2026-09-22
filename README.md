# Campaign Implementation Intelligence

Campaign Implementation Intelligence is a local FastAPI + SQLite proof of concept that implements the Phase 1 to Phase 11 synthetic marketing workflow:

1. Synthetic source data generation and ingestion.
2. Phase 1 data foundation and reconciliation.
3. Phase 2 historical cohort analysis at aggregate-only grain.
4. Phase 3 governed positive-unlabeled (PU) model training.
5. Phase 4 durable model/scoring job orchestration.
6. Phase 5 asynchronous 5M demographic prospect scoring.
7. Phase 6 Audience Explorer filtering, search, profile, and saved audiences.
8. Phase 7 Campaign Builder draft/finalize/currentness and deterministic target-list export.
9. Phase 8 system-browser release assurance, reproducibility, and repository freeze.
10. Phase 9 business-friendly campaign context, targeting, exact Target Group preview, and draft creation.
11. Phase 10 automatic compatibility-driven intelligence reuse/build orchestration.
12. Phase 11 simplified business search, durable smart result reuse, and governed omnichannel download.

All source data in this repository is synthetic. The historical customer universe and the demographic prospect universe are intentionally independent.

- Historical behavior uses customer_id.
- Prospect scoring and campaign export use person_id.
- The application does not create or infer a customer_id to person_id linkage.

## Product flow (Phase 1 to 11)

1. Load synthetic customer, campaign-sales, and demographic source files.
2. Import data into SQLite with strict schema/header validation.
3. Reconcile row counts, structural constraints, and required indexes.
4. Create historical analyses and persist aggregate-only snapshots.
5. Train governed PU models from historical customer cohorts.
6. Score the 5,000,000-row demographic prospect universe asynchronously.
7. Prepare audience rank boundaries and analytics snapshots.
8. Explore audiences, estimate/select cohorts, and save immutable audience definitions.
9. Build campaigns from current saved audiences, finalize, and export EMAIL or DIRECT_MAIL target lists.
10. Use Create Campaign for a guided business workflow that captures campaign context, applies explicit business targeting, compares exact match-strength counts, saves an immutable Target Group, and creates a Campaign Draft.
11. Use the three-tab business workflow: Home → Find Potential Customers → Results → Result Detail. Smart reuse runs automatically behind the submitted search; it is not a visible tab.
12. Download the immutable result through its saved governed omnichannel profile; contact PII is joined only at this boundary.

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

The Phase 11 runtime ownership path is HTTP → bounded Phase 11 coordinator → durable Phase 10 compatibility/reuse/build → immutable result snapshot → governed export. Application startup initializes the coordinator automatically, reconciles Phase 10 work, resumes durable `QUEUED`/`PROCESSING` Phase 11 searches, and reconciles stale export audits. Shutdown disconnects new submissions before closing the coordinator and existing model/scoring executor. See [Phase 11 runtime architecture](docs/PHASE_11_RUNTIME_ARCHITECTURE.md).

## Current versions and frozen contracts

- Application version default: 0.1.0
- Current SQLite schema version: 18
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
- Campaign targeting-context contract version: 1
- Targeting-segment contract version: 1
- Business match-strength contract version: 1
- Age-bucket and income-group contract versions: 1
- Targeting-intelligence resolution contract version: 1
- Target Group preview, saved Target Group, and Target Group campaign contract versions: 1
- Phase 11 search-run, result-cache, membership, result-export, and omnichannel-profile contract versions: 1
- Omnichannel export profiles:
  - EMAIL → EMAIL_CONTACT_V1
  - DIRECT_MAIL → DIRECT_MAIL_CONTACT_V1
  - SMS → SMS_CONTACT_V1
  - WHATSAPP → WHATSAPP_CONTACT_V1
  - TELEMARKETING → TELEMARKETING_CONTACT_V1
  - PAID_SOCIAL → PAID_SOCIAL_AUDIENCE_V1
  - PAID_SEARCH → PAID_SEARCH_AUDIENCE_V1
  - MOBILE_PUSH → MOBILE_PUSH_CONTACT_V1
  - DISPLAY → DISPLAY_AUDIENCE_V1
  - WEBSITE_ONSITE → WEBSITE_AUDIENCE_V1

## Repository layout

```text
app/                     FastAPI routers, schemas, services, repositories, DB code
artifacts/models/        Local model artifacts (ignored in git)
data/                    Canonical synthetic sources, references, and local SQLite file
data_generation_scripts/ Deterministic synthetic data generators
frontend/                Three-tab business UI plus retained hidden legacy/analyst modules
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

Checksum policy:

- Raw GZIP SHA-256: byte-level identity for the tracked compressed artifact.
- Decompressed content SHA-256: logical CSV identity independent of gzip metadata.
- LFS object ref: SHA-256 identity of the compressed object.
- Operational source currentness: the importer hashes each source filename, a NUL separator, all raw file bytes, and a final NUL; this checksum is persisted in `data_import_runs`. No contactability or identifier field is excluded.

| File | Expected rows | Bytes | Raw GZIP SHA-256 | Decompressed content SHA-256 | LFS object ref |
|---|---:|---:|---|---|---|
| data/customer_master_125000.csv.gz | 125,000 | 6,145,025 | 8a2c5601a96dc54708246a84cfd7715cf53e3d6f95e67472b1e2c2428bf0d18f | fa0e53b055e0340d0a7cfc6dfdd2fc8bcf18c606e7c8b2b13853ef9a561447bd | 8a2c5601a96dc54708246a84cfd7715cf53e3d6f95e67472b1e2c2428bf0d18f |
| data/campaign_sales_570000.csv.gz | 570,000 | 6,466,267 | 89e6f846a9b9de9bdb5a3945bd785dc7d83a98132ed5388e51072b7a44244116 | f0a391bbd2ef8262644b1f5c879f3ba1d473476889db8b48e6fde222ea640e0d | 89e6f846a9b9de9bdb5a3945bd785dc7d83a98132ed5388e51072b7a44244116 |
| data/usa_demographic_synthetic_5000000_rows.csv.gz | 5,000,000 | 512,842,205 | 27d8e2a978458a095e16fc51a682e1f3373e41b663a4e61defa47e2d1bdf8b1d | 5694d2048e96b270a3d522e2cc08c1af26561f6fd3c08f104e9957e76653612c | 27d8e2a978458a095e16fc51a682e1f3373e41b663a4e61defa47e2d1bdf8b1d |

Phase 11 Step 4 extends canonical demographics from 28 to 40 columns with deterministic contactability, consent, and nullable push/advertising/web identifiers. The original 28 columns remain byte-for-byte unchanged. Rates, identifier rules, and regeneration details are in [data/README.md](data/README.md).

The new canonical import checksum is `336cbef90fb601d84e2206b191a71b355810da282c918ec0b6e469528f70215f`. Prior Phase 10 scores are stale for this source; a new full scoring generation is required before current-source targeting/export. Historical/model reuse remains subject to existing Phase 10 compatibility gates because the 11 model features are unchanged. Step 4 does not run scoring.

If a .gz file is around 130 bytes and contains git-lfs pointer text, run git lfs pull before imports.

## Initialize and inspect the database

```powershell
.\.venv\Scripts\python.exe scripts\init_db.py
.\.venv\Scripts\python.exe scripts\init_db.py --inspect
```

Initialization is idempotent and creates/verifies schema version 18. The 15-to-16 migration appends source fields with false/null defaults. The 16-to-17 migration adds separate `campaign_search_runs`, `campaign_result_snapshots`, and `campaign_result_export_events` registries without modifying Phase 1–10 rows or legacy Campaign export semantics. The 17-to-18 migration adds a nullable, write-once future activation and outcome-lineage seam without implementing delivery, feedback ingestion, or retraining.

Phase 11 persists immutable business submissions separately from reusable, contact-PII-free result snapshots. Exact hits reuse a validated snapshot; otherwise the system reuses compatible Phase 10 intelligence or builds only missing layers, then atomically materializes one requested membership. Search-result exports have their own count/checksum/currentness audit records. See [smart reuse and snapshot contracts](docs/PHASE_11_RESULT_SNAPSHOTS_AND_SMART_REUSE.md).

Phase 11 limits normal navigation to **Home**, **Find Potential Customers**, and **Results**, governed by `frontend/js/view-contract.js`. Empty/unknown/hidden legacy fragments redirect to `#home`; `#overview` and `#campaign-planner` normalize to their business routes without adding history entries. Legacy views/modules and APIs remain intact. Results and Result Detail are connected to durable run/snapshot history. UI hiding is not authentication, authorization, or RBAC. See [business UI and navigation](docs/PHASE_11_BUSINESS_UI.md).

Phase 11 progressively enhances campaign-context and targeting multi-selects using one searchable, keyboard-accessible Vanilla-JS dropdown. Select All visible adds filtered available matches; Clear All removes all selections across the filter. Backend option values, native form validation, existing saved context/criteria, Region-to-State semantics, and retained legacy components remain authoritative.

**Find Potential Customers** is one business form while the hidden legacy planner and frozen Phase 9/10 semantics remain intact. Each valid intentional request durably records fresh context/criteria lineage and an immutable search run before execution. Results can rediscover and reopen the request after navigation, reload, or restart. Delivery/profile and prospect-filter changes do not alter Modeling Context.

The smart-reuse engine follows exact result → compatible Phase 10 intelligence → minimum new Phase 10 build. It validates exact cache hits without scanning scores, streams exact OR-branch Audience Engine membership in global rank order on a miss, and publishes an immutable snapshot atomically. Durable `PROCESSING` searches can resume after Phase 10 work or restart. There is no all-permutation precompute.

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

The normal application command automatically initializes the Phase 11 coordinator and result materializer. No test-only executor configuration is required. After a restart, durable `QUEUED` and `PROCESSING` searches are discovered and rescheduled without rewriting terminal history.

## UI navigation

Normal business navigation contains exactly:

- Home
- Find Potential Customers
- Results

Result Detail is a child of Results, not a fourth top-level tab. The implemented legacy/analyst surfaces—including Overview/Create Campaign, Saved Target Groups, Insights, Data Status, Historical Analysis, Model Training and Prospect Scoring, Audience Explorer, and Campaigns—remain in the codebase for backward compatibility but are not visible in normal navigation. Hiding these views is a presentation boundary only; authentication, authorization, and RBAC are not implemented.

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

Business Campaign Planner and Target Groups:

- GET /api/campaign-planner/context-options
- POST /api/campaign-planner/contexts
- GET /api/campaign-planner/contexts/{targeting_context_id}
- PUT /api/campaign-planner/contexts/{targeting_context_id}
- GET /api/campaign-planner/targeting-options
- GET /api/campaign-planner/contexts/{targeting_context_id}/targeting-criteria
- PUT /api/campaign-planner/contexts/{targeting_context_id}/targeting-criteria
- GET /api/campaign-planner/contexts/{targeting_context_id}/targeting-intelligence
- GET /api/campaign-planner/contexts/{targeting_context_id}/intelligence-plan
- POST /api/campaign-planner/contexts/{targeting_context_id}/targeting-intelligence/prepare
- GET /api/campaign-planner/contexts/{targeting_context_id}/targeting-intelligence/preparation
- POST /api/campaign-planner/contexts/{targeting_context_id}/targeting-intelligence/preparation/retry
- PUT /api/campaign-planner/contexts/{targeting_context_id}/targeting-intelligence
- DELETE /api/campaign-planner/contexts/{targeting_context_id}/targeting-intelligence
- GET /api/campaign-planner/contexts/{targeting_context_id}/target-group-preview
- GET /api/campaign-planner/contexts/{targeting_context_id}/match-strength-recommendation
- POST /api/campaign-planner/contexts/{targeting_context_id}/target-group-search
- POST /api/campaign-planner/contexts/{targeting_context_id}/save-target-group-and-create-draft
- GET /api/campaign-planner/contexts/{targeting_context_id}/campaign-draft

Phase 11 business workflow:

- GET /api/business/overview
- GET /api/business/recent-results
- GET /api/export-profiles
- GET /api/potential-customer-search/options
- POST /api/potential-customer-search/runs
- GET /api/potential-customer-search/runs
- GET /api/potential-customer-search/runs/{search_run_id}
- GET /api/potential-customer-search/runs/{search_run_id}/status
- GET /api/potential-customer-search/results
- GET /api/potential-customer-search/runs/{search_run_id}/result
- GET /api/potential-customer-search/runs/{search_run_id}/download

## Phase summary

- Phase 1: import, reconciliation, aggregate data/reference APIs.
- Phase 2: bounded historical cohort analysis and saved aggregate snapshots.
- Phase 3: governed PU training and artifact governance.
- Phase 4: asynchronous job orchestration groundwork.
- Phase 5: asynchronous prospect scoring and scoring-run lifecycle.
- Phase 6: audience rank boundaries, filters/search/profile, immutable saved audiences.
- Phase 7: campaign draft/finalize/currentness and deterministic export with audit events.
- Phase 8: system-browser release assurance, exhaustive control coverage, reproducibility, CI, and repository freeze.
- Phase 9: business-friendly campaign planning, deterministic targeting criteria, explicit intelligence-source gating, exact Target Group preview/recommendations, immutable Target Group save, and Campaign Draft creation.
- Phase 10: exact Modeling Context identity, automatic compatibility-driven reuse/build orchestration, durable progress and recovery, context-bound intelligence generations, and non-destructive lifecycle governance.
- Phase 11: three-tab business workflow, exact-result smart reuse, durable immutable result snapshots/history, and governed ten-profile omnichannel downloads.

## Phase 9 business targeting

The default Create Campaign path uses business language and keeps model/scoring identifiers behind explicit technical-detail disclosures. Campaign context describes the request; it does not silently change prospect filters, retrain a model, or select a “latest” scoring run. Exact preview and save remain blocked until an analyst or administrator explicitly links a compatible, current targeting-intelligence source. Saved Target Groups provides a business-facing list over immutable Saved Audiences, while Insights routes users to existing governed analysis capabilities.

Match Strength is an exact minimum-score rule: Very Strong `0.90+`, Strong `0.80+`, Good `0.70+`, and Broad `0.60+`. Recommendations compare exact counts and never claim purchase probability. The optional Region shortcut is backend-owned and expands only to currently available State values; immutable criteria remain exact, state-based, and auditable. Planning and preview exclude contact PII; contact fields remain available only through the governed, acknowledged Phase 7 finalized-campaign export profiles.

Phase 10 implements automatic analysis/model/scoring/rank compatibility, reuse/build/refresh orchestration, long-running durable progress, context-specific provenance, and scoring lifecycle/retention. Resolution is by exact Modeling Context and layered compatibility fingerprints; there is no “latest run wins” fallback. Delivery and descriptive Campaign fields plus prospect-targeting filters remain outside the Modeling Context, so those changes reuse valid intelligence. Analytical dimensions, source checksums, artifacts, governed policies, or score semantics invalidate the corresponding compatibility layer and trigger the minimum required rebuild.

The normal business path automatically prepares intelligence between Campaign Context and Target Group Preview. READY publication atomically binds the verified generation and exact scoring source back to the Phase 9 context. Lifecycle reconciliation classifies generations as CURRENT, REUSABLE, SUPERSEDED, STALE, RETIREMENT_ELIGIBLE, or PROTECTED without deleting analytical lineage. See `docs/PHASE_10_IMPLEMENTATION_SUMMARY.md` and `docs/evidence/phase10/README.md`.

## Phase 11 business search and smart reuse

The visible Phase 11 path is **Home → Find Potential Customers → Results → Result Detail → Download**. Smart reuse is automatic runtime behavior after submission, not a separate page or tab. Every submission is a durable history event. The system reuses a fully validated exact result when possible, otherwise filters compatible Phase 10 intelligence, otherwise builds only missing intelligence layers and materializes the requested result. Search history is distinct from snapshot identity, so repeated requests remain auditable without duplicating valid membership.

All ten omnichannel profiles are backend-owned and source-truthful. Membership snapshots and JSON/UI projections contain no contact PII. At download time, the engine revalidates lineage/currentness, joins only the profile-required fields in bounded chunks, enforces consent/contactability/targetability, and persists aggregate audit metadata. Paid-media profiles emit only SHA-256 match keys. See `docs/PHASE_11_IMPLEMENTATION_SUMMARY.md` and `docs/evidence/phase11/README.md`.

## Phase 8 release assurance

The final Phase 8 acceptance is `GO` for implementation SHA `f5d6f9ed047146f04ecdabca38e6d18793ac4eba`.

- System Chrome 152.0.7977.83 was used for browser assurance.
- All 111 actionable controls are accounted for: 104 PASS and 7 individually justified exclusive controls.
- Browser quality has zero unexplained console errors and zero unexplained critical network failures.
- Local regression completed with 477 passing tests and a bounded clean-room Phase 1 to 7 pass.
- Step 11 rebuilt the runtime, imported all canonical data, and completed browser-driven training and full 5M scoring in strict-fresh mode.
- GitHub Actions run 34306807259 passed all five required checks for the exact implementation SHA.
- Full details: `docs/PHASE_8_IMPLEMENTATION_SUMMARY.md` and `docs/evidence/phase8/PHASE8_FINAL_ACCEPTANCE.md`.

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

Legacy finalized-Campaign export profiles:

- EMAIL_CONTACT_V1: person_id, score/rank fields, name, email
- DIRECT_MAIL_CONTACT_V1: person_id, score/rank fields, name, mailing address fields

Prohibited fields include ethnicity, religion, occupation_industry, family_yearly_income, number_of_children_in_family, number_of_adults_in_family, and customer_id. Phone is prohibited in the legacy Email/Direct Mail profiles, not globally: the Phase 11 backend registry permits it only for SMS/WhatsApp/Telemarketing and emits only hashed match keys for paid media. All ten Phase 11 registry profiles have source-field support and are integrated into the current result-snapshot download engine.

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
$env:CHUNK = "200000"
$env:ID_OFFSET = "0"
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

Phase 11 Step 20 records 966 passing tests and successful full-5M certification. Normal CI excludes full-5M and performance work from the unit job, runs the bounded Phase 1–7 clean-room separately, and includes bounded Phase 9, Phase 10, and Phase 11 contract/UI/cache/profile suites. Phase 11 UI contracts use installed system Chrome with pinned browser-test-only dependencies. Full 5M scoring remains explicit release-certification work, not normal CI.

## Configuration

See .env.example for supported variables:

- APP_NAME, APP_VERSION, APP_ENV
- HOST, PORT
- DATABASE_PATH, DATABASE_BUSY_TIMEOUT_MS
- EXPECTED_CUSTOMER_ROWS, EXPECTED_CAMPAIGN_SALES_ROWS, EXPECTED_DEMOGRAPHIC_ROWS
- CUSTOMER_COUNT_EXACT_REQUIRED, CUSTOMER_COUNT_TOLERANCE_PERCENT
- CAMPAIGN_SALES_COUNT_EXACT_REQUIRED, DEMOGRAPHIC_COUNT_EXACT_REQUIRED
- MATCH_STRENGTH_RECOMMENDATION_MINIMUM_COUNT
- MATCH_STRENGTH_VERY_STRONG_MINIMUM_MULTIPLIER
- LOG_LEVEL

## POC limitations

- Single-node SQLite runtime and bounded single-worker compute execution profile.
- No customer-person identity resolution.
- No authentication, authorization, tenant isolation, or RBAC.
- No activation/send channel integrations.
- No provider feedback ingestion, automated outcome labeling, or retraining loop.
- Local artifact storage and local operational posture, not a multi-tenant deployment profile.
- Timing evidence is environment-dependent and not an SLA.
