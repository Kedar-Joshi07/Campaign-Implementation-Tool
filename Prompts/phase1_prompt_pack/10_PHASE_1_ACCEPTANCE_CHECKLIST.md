# Phase 1 Acceptance Checklist

Use this checklist only after Steps 1–7 are complete.

## A. Architecture
- [ ] Frontend uses HTML, CSS, Vanilla JS only.
- [ ] Backend uses FastAPI + Python.
- [ ] Database is SQLite.
- [ ] FastAPI serves the frontend.
- [ ] No unnecessary enterprise infrastructure has been introduced.
- [ ] Repository has sensible router/service/repository/database separation.

## B. Database
- [ ] SQLite database initializes from scratch.
- [ ] `app_metadata` exists.
- [ ] `data_import_runs` exists.
- [ ] `customers` exists with exactly the frozen 22 columns.
- [ ] `campaign_sales` exists with exactly the frozen 38 columns.
- [ ] `demographics` exists with exactly the frozen 28 columns.
- [ ] Primary keys are enforced.
- [ ] Campaign -> customer foreign key is enforced.
- [ ] No demographic -> customer linkage exists.
- [ ] Foreign keys are enabled on connections.
- [ ] Required indexes exist.

## C. Import pipeline
- [ ] Customer CSV/CSV.GZ import works.
- [ ] Campaign-sales CSV/CSV.GZ import works.
- [ ] Demographic multi-part import works.
- [ ] Imports are streamed/chunked.
- [ ] Full files are not loaded into memory.
- [ ] Header/schema validation exists.
- [ ] Import metadata is persisted.
- [ ] Progress is logged for large imports.
- [ ] Default import does not silently duplicate existing data.
- [ ] Explicit replace behavior is documented.
- [ ] Invalid campaign customer FK is detected/rejected.
- [ ] Malformed demographic household arithmetic is detected.

## D. Data reconciliation
- [ ] Customer row count available.
- [ ] Campaign-sales row count available.
- [ ] Demographic row count available.
- [ ] Distinct campaign count available.
- [ ] Distinct product count available.
- [ ] Historical date range available.
- [ ] PU positive count available.
- [ ] FK violation count available.
- [ ] PU consistency violation count available.
- [ ] Demographic family consistency violation count available.
- [ ] CLI validation command works.

## E. APIs
- [ ] `GET /api/health`
- [ ] `GET /api/version`
- [ ] `GET /api/data/status`
- [ ] `GET /api/data/summary`
- [ ] `GET /api/data/imports`
- [ ] `GET /api/reference/states`
- [ ] `GET /api/reference/campaigns`
- [ ] `GET /api/reference/products`
- [ ] API errors are structured/useful.
- [ ] No endpoint dumps millions of rows.

## F. UI
- [ ] `/` loads successfully.
- [ ] Overview page is functional.
- [ ] Data Status page is functional.
- [ ] UI values come from APIs.
- [ ] No fake/hard-coded KPI values.
- [ ] Loading state exists.
- [ ] Backend failure state exists.
- [ ] Large numbers are formatted.
- [ ] Future-phase navigation is visibly disabled/labeled.

## G. Testing
- [ ] Health API tests pass.
- [ ] DB initialization tests pass.
- [ ] Schema tests pass.
- [ ] FK tests pass.
- [ ] Import tests pass.
- [ ] Reconciliation tests pass.
- [ ] Data API tests pass.
- [ ] Full test suite passes.

## H. Documentation
- [ ] README explains setup.
- [ ] README explains import order.
- [ ] README documents source file expectations.
- [ ] README gives exact run commands.
- [ ] README gives validation command.
- [ ] README contains troubleshooting.
- [ ] Phase 1 implementation summary exists.
- [ ] Progress tracker is current.

## I. Scope control
- [ ] No PU model implemented.
- [ ] No propensity scoring implemented.
- [ ] No audience explorer logic implemented.
- [ ] No campaign builder implemented.
- [ ] No authentication/RBAC implemented.
- [ ] No CRM/activation integration implemented.
- [ ] No Redis/Celery/microservices/cloud infrastructure implemented.

## Final acceptance statement
Phase 1 is accepted when the application can be set up from scratch, load/reconcile the three data domains, start successfully, expose reliable summary/status APIs, and display those real values in the functional Overview and Data Status UI.
