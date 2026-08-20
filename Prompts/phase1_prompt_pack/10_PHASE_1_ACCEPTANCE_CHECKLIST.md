# Phase 1 Acceptance Checklist

Use this checklist only after Steps 1–7 are complete.

## A. Architecture
- [x] Frontend uses HTML, CSS, Vanilla JS only.
- [x] Backend uses FastAPI + Python.
- [x] Database is SQLite.
- [x] FastAPI serves the frontend.
- [x] No unnecessary enterprise infrastructure has been introduced.
- [x] Repository has sensible router/service/repository/database separation.

## B. Database
- [x] SQLite database initializes from scratch.
- [x] `app_metadata` exists.
- [x] `data_import_runs` exists.
- [x] `customers` exists with exactly the frozen 22 columns.
- [x] `campaign_sales` exists with exactly the frozen 38 columns.
- [x] `demographics` exists with exactly the frozen 28 columns.
- [x] Primary keys are enforced.
- [x] Campaign -> customer foreign key is enforced.
- [x] No demographic -> customer linkage exists.
- [x] Foreign keys are enabled on connections.
- [x] Required indexes exist.

## C. Import pipeline
- [x] Customer CSV/CSV.GZ import works.
- [x] Campaign-sales CSV/CSV.GZ import works.
- [x] Demographic multi-part import works.
- [x] Imports are streamed/chunked.
- [x] Full files are not loaded into memory.
- [x] Header/schema validation exists.
- [x] Import metadata is persisted.
- [x] Progress is logged for large imports.
- [x] Default import does not silently duplicate existing data.
- [x] Explicit replace behavior is documented.
- [x] Invalid campaign customer FK is detected/rejected.
- [x] Malformed demographic household arithmetic is detected.

## D. Data reconciliation
- [x] Customer row count available.
- [x] Campaign-sales row count available.
- [x] Demographic row count available.
- [x] Distinct campaign count available.
- [x] Distinct product count available.
- [x] Historical date range available.
- [x] PU positive count available.
- [x] FK violation count available.
- [x] PU consistency violation count available.
- [x] Demographic family consistency violation count available.
- [x] CLI validation command works.

## E. APIs
- [x] `GET /api/health`
- [x] `GET /api/version`
- [x] `GET /api/data/status`
- [x] `GET /api/data/summary`
- [x] `GET /api/data/imports`
- [x] `GET /api/reference/states`
- [x] `GET /api/reference/campaigns`
- [x] `GET /api/reference/products`
- [x] API errors are structured/useful.
- [x] No endpoint dumps millions of rows.

## F. UI
- [x] `/` loads successfully.
- [x] Overview page is functional.
- [x] Data Status page is functional.
- [x] UI values come from APIs.
- [x] No fake/hard-coded KPI values.
- [x] Loading state exists.
- [x] Backend failure state exists.
- [x] Large numbers are formatted.
- [x] Future-phase navigation is visibly disabled/labeled.

## G. Testing
- [x] Health API tests pass.
- [x] DB initialization tests pass.
- [x] Schema tests pass.
- [x] FK tests pass.
- [x] Import tests pass.
- [x] Reconciliation tests pass.
- [x] Data API tests pass.
- [x] Full test suite passes.

## H. Documentation
- [x] README explains setup.
- [x] README explains import order.
- [x] README documents source file expectations.
- [x] README gives exact run commands.
- [x] README gives validation command.
- [x] README contains troubleshooting.
- [x] Phase 1 implementation summary exists.
- [x] Progress tracker is current.

## I. Scope control
- [x] No PU model implemented.
- [x] No propensity scoring implemented.
- [x] No audience explorer logic implemented.
- [x] No campaign builder implemented.
- [x] No authentication/RBAC implemented.
- [x] No CRM/activation integration implemented.
- [x] No Redis/Celery/microservices/cloud infrastructure implemented.

## Final acceptance statement
Phase 1 is accepted when the application can be set up from scratch, load/reconcile the three data domains, start successfully, expose reliable summary/status APIs, and display those real values in the functional Overview and Data Status UI.


---

## Step 7 acceptance evidence — 2026-08-20

- One shared `.venv` satisfies the root application/test requirements and the
  included generator requirements; `pip check` reported no broken dependencies.
- A new isolated database was initialized twice, then loaded from the real
  125,000-customer, 570,000-campaign-sales, and 5,000,000-demographic GZIP files.
  All three completed with zero rejected rows.
- The repeat customer import was refused before reading source rows, recorded as
  `FAILED`, and left the 125,000 existing rows unchanged.
- Reconciliation returned `OK`, all structural violation counts were zero, and
  all 17 required indexes were present. A repeated validation found every index
  already present with effectively zero creation time.
- The full automated suite passed: 56 tests. The only warning is an external
  Starlette deprecation notice for its current HTTPX test-client compatibility
  import; no test or runtime failure is associated with it.
- Browser verification against the isolated real database confirmed Overview and
  Data Status values, loading-to-ready behavior, import history, navigation, and
  disabled later-phase controls.
- Restarting FastAPI preserved counts `(125000, 570000, 5000000)`, four import
  audit rows, and the original `database_initialized_at` value.
- The isolated acceptance database was removed after validation; the primary
  `data/campaign_poc.db` and generated source files were not changed.
