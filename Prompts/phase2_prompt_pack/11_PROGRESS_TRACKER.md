# Phase 2 Progress Tracker

The coding agent must update this file at the end of every step. Preserve prior entries; append evidence rather than replacing history.

## Phase metadata

- Phase: 2 — Historical Campaign Analysis
- Required base SHA: `c6c9f41ea257aa33ae196b75cc8f76f8419431e7`
- Actual starting SHA: `c6c9f41ea257aa33ae196b75cc8f76f8419431e7`
- Branch: `main` (`0` ahead / `0` behind `origin/main`)
- Worktree initially clean: No — tracked tree clean; user-provided `Prompts/phase2_prompt_pack/` untracked
- Python version: 3.12.0
- Initial schema version: 1
- Initial full test result: 77 passed, 1 upstream Starlette deprecation warning in 30.99s
- Started at: 2026-08-20T21:12:00+05:30
- Current status: PHASE 2 COMPLETE — ACCEPTANCE AND HANDOFF VALIDATED

## Frozen decisions

- Analysis grain: distinct historical customer
- Default conversion definition: `ATTRIBUTED_PURCHASE`
- Default exposure rule: `contacted_only=true`
- Unlabeled meaning: selected customer with no qualifying positive event inside the submitted filters; not a confirmed negative
- Age reference: normalized analysis end date
- Saved handoff identifier: `analysis_run_id`
- Demographic population queried/joined in Phase 2: No
- Model training/scoring in Phase 2: No

## Step status

| Step | Description | Status | Focused tests | Full tests | Completed at |
|---:|---|---|---|---|---|
| 1 | Baseline and additive schema | COMPLETE | 52 passed, 1 warning | 82 passed, 1 warning | 2026-08-20T21:26:54+05:30 |
| 2 | Historical options and overview | COMPLETE | 6 passed | 88 passed, 1 warning | 2026-08-20T23:37:34+05:30 |
| 3 | Cohort analysis engine | COMPLETE | 24 passed | 106 passed, 1 warning | 2026-08-20T23:55:47+05:30 |
| 4 | Historical APIs | COMPLETE | 46 passed, 1 warning | 128 passed, 1 warning | 2026-08-21T00:14:32+05:30 |
| 5 | Overview analytics UI | COMPLETE | 15 passed, 1 warning | 133 passed, 1 warning | 2026-08-21T00:34:42+05:30 |
| 6 | Historical Analyzer UI | COMPLETE | 12 passed, 1 warning | 146 passed, 1 warning | 2026-08-21T00:57:58+05:30 |
| 7 | Hardening, performance, docs | COMPLETE | 12 passed | 158 passed | 2026-08-21T01:40:10+05:30 |

---

## Step 1 evidence — Baseline and additive schema

### Preconditions

- HEAD: `c6c9f41ea257aa33ae196b75cc8f76f8419431e7`
- `git status --short`: `?? Prompts/phase2_prompt_pack/`
- Remote/branch status: `main...origin/main`; `0` ahead / `0` behind
- `pip check`: `No broken requirements found.`
- Baseline pytest: 77 passed, 1 upstream Starlette deprecation warning in 30.99s
- Existing table counts: customers 125,000; campaign_sales 570,000; demographics 5,000,000; data_import_runs 3

### Work completed

- Added an explicit ordered migration registry from the accepted Phase 1 schema version 1 to current schema version 2.
- Made empty-database base creation and each schema migration transactional; schema metadata advances in the same transaction only after successful migration work.
- Added clear rejection for invalid, unsupported older, and future schema versions.
- Added `historical_analysis_runs` with the frozen status/conversion/count/rate constraints and no raw identifier or SQL columns.
- Added the newest-first analysis-run index and the three frozen simple campaign filter indexes; no composite analysis index was added.
- Extended the existing required-index creation/verification contract from 17 to 21 indexes.
- Made normal dependency-based first database access initialize/migrate the configured database; the existing initialization CLI, imports, reconciliation, and temporary-test paths continue to use the same initializer.
- Updated Phase 1 aggregate API assertions only for the expected schema-version value (`1` → `2`); endpoint shape and other behavior remain unchanged.

### Files changed

- `app/database/schema.py`
- `app/dependencies.py`
- `scripts/init_db.py`
- `tests/test_database_schema.py`
- `tests/test_data_api.py`
- `tests/test_data_reconciliation.py`
- `tests/test_health.py`
- `Prompts/phase2_prompt_pack/11_PROGRESS_TRACKER.md`

### Migration evidence

- Fresh DB version: 2; all six expected application tables created in a temporary fixture.
- Populated v1 → v2 preservation result: synthetic migration fixture preserved counts and a representative customer row exactly. Full local data then reconciled `OK` after migration with customers 125,000, campaign_sales 570,000, demographics 5,000,000, invalid customer references 0, and PU consistency violations 0.
- Repeated initialization result: temporary-fixture idempotence test passed; repeated `scripts/init_db.py` run completed at version 2 and retained all six tables and populated counts.
- Failure rollback/version result: forced migration failure rolled back its DDL and left stored version at 1.
- New table/index inspection: 14 required columns and the newest-first index present on `historical_analysis_runs`; campaign channel, product category, and campaign type indexes present; all 21 required indexes verified.

### Tests/checks

- Focused: `python -m pytest -q tests/test_database_schema.py tests/test_data_reconciliation.py tests/test_data_api.py tests/test_health.py` → 52 passed, 1 upstream warning in 17.67s. An earlier schema-only run exposed non-transactional SQLite DDL (13 passed, 1 failed); explicit `BEGIN IMMEDIATE` fixed it, and the schema-only rerun passed 14/14.
- Full: `python -m pytest -q` → 82 passed, 1 upstream Starlette deprecation warning in 40.90s.
- Compile: `python -m compileall -q app scripts tests` → passed with no output.
- Diff check: `git diff --check` → passed; only Git's informational LF→CRLF working-copy notices were emitted.
- Dependency check: `python -m pip check` → `No broken requirements found.`
- Full-data check: `python scripts/validate_data.py --json` → schema version 2, reconciliation `OK`, 21/21 required indexes present, 20.651s reconciliation query time.

### Findings / deferred

- SQLite DDL requires an explicit transaction start for reliable rollback; the migration path now uses `BEGIN IMMEDIATE` and has regression coverage.
- The existing environment emits one Starlette/httpx deprecation warning; it is unchanged from the Phase 1 baseline.
- Historical options, aggregates, cohort logic, APIs, and UI remain deferred; no Step 2 or later functionality was added.

### Next approved step

- Step 2 only

---

## Step 2 evidence — Historical options and overview

### Work completed

- Added a dedicated `HistoricalRepository` with fixed, aggregate-only SQLite queries for real filter options and full-history performance.
- Added `historical_service` response composition aligned with the frozen snake_case API shapes, without adding a router or public endpoint.
- Added real, deduplicated, deterministically ordered campaign, product, category, channel, and campaign-type options; null/blank values are excluded.
- Added stable canonical labels plus warning logs when a returned campaign/product ID has inconsistent source labels.
- Added frozen conversion-definition metadata and default filters using the actual available date range, `contacted_only=true`, and `ATTRIBUTED_PURCHASE`.
- Added summary metrics, monthly trends, channel/category performance, top campaigns/products, and descriptive observation-grain PU-label distribution.
- Implemented bounded category roll-up to `Other` in SQLite and added six synthetic-fixture tests covering semantics, ordering, bounds, empty/zero behavior, query scope, and response safety.

### Files changed

- `app/repositories/historical_repository.py`
- `app/services/historical_service.py`
- `tests/test_historical_service.py`
- `Prompts/phase2_prompt_pack/11_PROGRESS_TRACKER.md`

### Semantics recorded

- Rate denominators: engagement, response, purchase, and attributed-purchase numerators are divided by contacted observation count. Rates are fractions rounded to 6 decimals; zero contacted observations return `0.0` for every rate.
- Empty/zero behavior: empty history returns null available dates, empty option/breakdown arrays, zero integer counts, `0.0` money/rates, and no NaN/Infinity. Null financial values contribute zero; money is rounded to 2 decimals at the final response/roll-up boundary.
- Breakdown limits and ordering: monthly trend ≤120 months ascending; channel/category ≤10 rows ordered by observation count descending then label ascending, with overflow combined into `Other`; top campaigns/products ≤10 ordered by observation count descending then stable ID ascending; label distribution orders `pu_label=1` before `pu_label=0`.
- Option limits/order: campaigns ≤250 and products ≤250 ordered by stable ID; categories/channels/types ≤100 each ordered case-insensitively by value with a deterministic binary tie-break. All values come from `campaign_sales`; blanks/nulls are excluded.

### Reconciliation fixture results

- Counts: 5 observations, 4 contacted, 3 engaged, 2 responses, 2 purchases, 1 attributed purchase, 3 distinct customers/campaigns/products; PU distribution 1 known-positive observation and 4 unlabeled observations.
- Rates: engagement `0.75`, response `0.5`, purchase `0.5`, attributed purchase `0.25`; a zero-contact fixture returned all rates as `0.0` even with outcome flags present.
- Financials: net sales `150.0` and gross margin `60.0`; null financial values reconciled as zero.
- Monthly/breakdown totals: chronological monthly observation counts `[2, 2, 1]`; monthly, channel, and category observations/net sales each reconcile to summary totals. A forced two-row channel limit produced `Other=3` plus `Email=2` without losing observations.
- Query evidence: options use 6 fixed queries and overview uses 7 fixed queries, with no `demographics` reference. Representative fixture timings were 0.0621s and 0.0679s respectively.
- Full-data comparison: service and independent SQL both returned 570,000 observations; 563,240 contacted; 132,798 engaged; 76,557 responses; 54,450 purchases; 34,273 attributed purchases; 121,016 distinct customers; 96 campaigns; 36 products; net sales 10,894,336.96; gross margin 5,102,167.06; range 2024-01-01 through 2025-12-31.

### Tests/checks

- Focused: `python -m pytest -q tests/test_historical_service.py` → 6 passed in 5.66s.
- Full: `python -m pytest -q` → 88 passed, 1 upstream Starlette deprecation warning in 34.84s.
- Compile: `python -m compileall -q app scripts tests` → passed with no output.
- Diff check: `git diff --check` → passed; only Git's informational LF→CRLF working-copy notices were emitted.

### Findings / deferred

- Full-data timings are above the Phase 2 warm target: options cold/warm 11.821s/11.265s and overview cold/warm 33.026s/32.874s on this machine. Query plans show purposeful full or simple-index scans; no speculative composite index was added. Query-plan/timing optimization remains explicitly deferred to Step 7.
- The existing Starlette/httpx deprecation warning remains unchanged.
- Router/API exposure, frontend rendering, cohort semantics, and analysis-run persistence were not implemented in this step.

### Next approved step

- Step 3 only

---

## Step 3 evidence — Cohort analysis engine

### Work completed

- Added one strict Pydantic filter representation with forbidden extra fields, normalized names/lists/dates, frozen conversion definitions, per-list maxima, and deterministic filter serialization.
- Added the authoritative parameterized matching-observation/customer-label CTE. Filter columns and conversion expressions come only from fixed code-owned mappings.
- Added filtered summary, monthly, channel, category, campaign, and product aggregates plus eleven aggregate customer-profile dimensions for selected, positive, unlabeled, and historical-baseline groups.
- Added deterministic age derivation from the normalized analysis end date, stable age/income/family bands, bounded profile categories, shares, and top-N-plus-`Other` state handling.
- Added short-transaction RUNNING → COMPLETED/FAILED persistence, stable sorted JSON snapshots, newest-first pagination, safe reopen, internal failure diagnostics, and structural validation of decoded saved filters/results.
- Added safe domain exceptions for invalid filters, unloaded history, zero matches, inconsistent attributed labels, unknown/invalid runs, execution failures, and corrupt saved snapshots.
- Added 18 Step 3 tests covering the complete frozen cohort, profile, persistence, and safety contract.

### Files changed

- `app/repositories/historical_repository.py`
- `app/schemas/historical.py`
- `app/services/historical_analysis_service.py`
- `tests/test_historical_analysis_service.py`
- `Prompts/phase2_prompt_pack/11_PROGRESS_TRACKER.md`

### Cohort proof

- Multiple rows/customer test: three matching CMP_A observations across two customers produced `observation_count=3` and `selected_customer_count=2`.
- Positive if any matching row test: one qualifying row among multiple matching rows made that customer positive exactly once.
- Outside-filter activity test: a customer's attributed purchase under CMP_OUT did not make the same customer positive for the CMP_A attributed-purchase cohort.
- Contacted-only test: CMP_B returned one contacted/unlabeled observation by default; `contacted_only=false` included two observations and made the customer positive under `RESPONSE`.
- Inclusive dates test: `from=to=2025-01-01` included both boundary observations and two distinct customers.
- Positive + unlabeled invariant: asserted for every conversion-definition/filter case; fixture CMP_A attributed result was `1 + 1 = 2`. Full data was `25,502 + 95,384 = 120,886`.
- SQL-looking value test: `CMP_A') OR 1=1 --` was bound as a value, returned the stable zero-match domain error, persisted FAILED with no results, and left all tables/rows intact.
- Filter coverage: campaign, product, category, channel, and campaign-type filters each worked independently and in one combined request.

### Conversion-definition results

- Attributed purchase: CMP_A fixture selected 2 customers → 1 positive / 1 unlabeled.
- Any purchase: CMP_A fixture selected 2 customers → 2 positive / 0 unlabeled.
- Response: CMP_A fixture selected 2 customers → 2 positive / 0 unlabeled.
- Consistency guard: an injected `pu_label` versus attributed-purchase mismatch failed the run and persisted no partial `results_json`.

### Profiles and age

- Profile reconciliation: all 11 dimensions reconciled counts and finite shares for selected=3, positive=2, unlabeled=1, and historical baseline=4.
- Birthday-boundary result: using persisted end date 2025-06-15, DOB 2000-06-15 derived age 25 (`25–34`) while DOB 2000-06-16 derived age 24 (`18–24`); DOB 1960-06-15 derived `65+`.
- Category limits/Other handling: forced state limit 2 retained one deterministic top category plus `Other=3`; counts/shares still reconciled to baseline 4. State limit is 10 normally; other dimensions are bounded to 20.

### Persistence

- Completed reopen equality: created and reopened completed responses compared equal; filters JSON used stable key ordering and deduplicated/sorted lists.
- Failed-run diagnostics/public safety: full internal traceback containing a private path/SQL-like detail was stored only in `error_message`; `results_json` remained null and public create/fetch responses exposed only stable sanitized messages.
- Listing order/pagination: three same-second runs ordered by `created_at DESC, analysis_run_id DESC`; `limit=2, offset=1` returned the expected middle/oldest IDs. Limits 1–100 and nonnegative offsets are enforced.
- Corrupt saved JSON: non-finite/malformed or structurally inconsistent snapshots are logged internally and rejected with a stable saved-run error.
- Phase 3 handoff: local full-data validation persisted completed `analysis_run_id=1`; reopen matched the returned aggregate snapshot exactly. No customer-ID membership list or training matrix was stored.

### Tests/checks

- Focused: `python -m pytest -q tests/test_historical_service.py tests/test_historical_analysis_service.py` → 24 passed in 14.01s; Step 3-only rerun → 18 passed in 10.60s.
- Full: `python -m pytest -q` → 106 passed, 1 upstream Starlette deprecation warning in 41.29s.
- Compile: `python -m compileall -q app scripts tests` → passed with no output.
- Diff check: `git diff --check` → passed; only Git's informational LF→CRLF working-copy notices were emitted.
- Fixture timings: create 0.3536s, reopen 0.0687s, list 0.0551s.
- Full-data broad default: 29.237s; 563,240 contacted observations; 120,886 selected customers; 25,502 positive; 95,384 unlabeled; net sales 10,894,336.96; gross margin 5,102,167.06. Independent SQL matched every recorded count/financial total.

### Findings / deferred

- The broad full-data analysis is correct but exceeds the roughly 10-second target at 29.237s on this machine. Query-plan/index optimization remains deferred to Step 7; no speculative composite index was added.
- The populated ignored local database now contains one completed Step 3 validation run (`analysis_run_id=1`); no database file is tracked by Git.
- One unchanged upstream Starlette/httpx deprecation warning remains.
- No API router, UI, model training, scoring, demographic linkage/query, audience selection, campaign creation, or export was added.

### Next approved step

- Step 4 only

---

## Step 4 evidence — Historical APIs

### Work completed

- Added one bounded historical router with five OpenAPI operations under `/api/historical`, registered once in the existing FastAPI application.
- Exposed real Step 2 options and overview aggregates through strict response models with bounded arrays, finite-number rejection, non-negative counts, rate constraints, and ISO date/timestamp serialization.
- Exposed synchronous Step 3 analysis creation with HTTP 201, normalized saved filters, full completed snapshots, newest-first bounded summaries, and saved-run reopen.
- Mapped known service failures to one stable `detail` response: structural request/path/query errors use 422, unloaded history and zero-match/integrity domain failures use 400, unknown runs use 404, and sanitized execution/saved-snapshot failures use 500.
- Preserved failed-run metadata inspection while excluding internal `error_message`, traceback, SQL, and paths from public responses.
- Updated the application description to cover Phase 1 foundations and Phase 2 aggregate historical analysis without making model-training or scoring claims.
- Added 22 focused API tests covering endpoint contracts, all conversion definitions, validation, persistence, sanitization, injection-like values, empty history, OpenAPI, and Phase 1 route regressions.

### Files changed

- `app/main.py`
- `app/routers/historical.py`
- `app/schemas/historical.py`
- `tests/test_historical_api.py`
- `Prompts/phase2_prompt_pack/11_PROGRESS_TRACKER.md`

### Endpoint results

| Endpoint | Status/result | Notes |
|---|---|---|
| GET `/api/historical/options` | 200 | Real bounded options/defaults; stable null dates and empty arrays when unloaded |
| GET `/api/historical/overview` | 200 | Aggregate-only summary/breakdowns; stable finite zero/empty response when unloaded |
| POST `/api/historical/analyses` | 201 | Synchronous completed snapshot; 422 structural validation; stable 400 domain failures |
| GET `/api/historical/analyses` | 200 | Newest-first summaries; `limit` 1–100 and nonnegative `offset`; no full results/profiles |
| GET `/api/historical/analyses/{id}` | 200 | Full completed or sanitized failed metadata; 404 unknown; 422 non-positive/invalid ID |

### Validation/security evidence

- Bounds and invalid dates: invalid conversion enums, reversed dates, blank/121-character names, 26 campaign IDs, extra fields, non-positive/non-integer run IDs, limits 0/101, and negative offsets all returned 422.
- Zero match: an unknown campaign returned 400 with exactly `No campaign observations match the selected filters.`; the failed run contained no partial results.
- Unknown run: positive unknown ID returned 404 with exactly `Historical analysis run was not found.`.
- Injection-like values: `CMP_A') OR 1=1; SELECT * FROM customers --` was treated as a bound value, returned the stable zero-match response without reflection, and preserved all 4 customer and 7 campaign fixture rows.
- PII/internal-detail scan: completed responses contained no fixture customer IDs/person fields/absolute temporary paths/SQL; an injected private path and SQL detail was retained only in the database traceback while create/list/reopen returned the stable sanitized failure message.
- OpenAPI: exactly five historical operations were present across four paths, with typed request/response schemas, useful summaries, and the Phase 2 aggregate-only application description; `/docs` returned 200.
- Phase 1 endpoint regression: `/api/health`, `/api/version`, `/api/data/summary`, and `/api/reference/campaigns` all returned 200 in the focused API suite; the full Phase 1/2 suite passed.

### Tests/checks

- Focused: `python -m pytest -q tests/test_historical_service.py tests/test_historical_analysis_service.py tests/test_historical_api.py` → 46 passed, 1 upstream warning in 19.25s. Step 4-only run: 22 passed, 1 warning in 10.04s.
- Full: `python -m pytest -q` → 128 passed, 1 upstream Starlette deprecation warning in 44.57s.
- Compile: `python -m compileall -q app scripts tests` → passed with no output.
- Dependency check: `python -m pip check` → `No broken requirements found.`
- Diff check: `git diff --check` → passed; only Git's informational LF→CRLF working-copy notices were emitted.

### Findings / deferred

- The API is synchronous by the frozen POC contract and inherits the recorded full-data timings from Steps 2–3 (options about 11.3s, overview about 32.9s, broad analysis about 29.2s on this machine). Query-plan and evidence-based index optimization remain deferred to Step 7.
- The unchanged Starlette/httpx deprecation warning remains.
- No frontend, model training/scoring, demographic linkage/query, audience selection, campaign creation, export, background-job infrastructure, or Step 5+ functionality was added.

### Next approved step

- Step 5 only

---

## Step 5 evidence — Overview analytics UI

### Work completed

- Preserved the complete Phase 1 Overview and Data Status content while adding one restrained historical-performance section sourced only from `GET /api/historical/overview`.
- Added exactly three compact real-data visualizations: a native-SVG monthly attributed-purchase-rate trend, campaign-channel performance bars, and product-category performance bars.
- Added aggregate observation/rate/net-sales/date context using shared number, percentage, currency, and date formatting; no campaign KPI or chart value is hard-coded.
- Added accessible SVG title/description content, a complete screen-reader monthly text equivalent, visible percentage/count text for bars, keyboard-focusable trend points, safe long-label wrapping/tooltips, and non-color text meaning.
- Added explicit loading skeleton, unloaded-history empty state, partial-breakdown fallbacks, unavailable state, and force-refresh retry behavior through the existing API cache and Overview error banner.
- Made successful Overview retry restore the global backend status to online; any failed Overview dependency sets it offline and retains a stable retry path.
- Enabled Historical Analysis navigation and the Overview call to action only to a clearly marked Step 6 shell; no analysis filters, execution, saved-run UI, or profiles were implemented early.
- Kept Model Training, Audience Explorer, and Campaigns disabled and labeled as later phases.

### Files changed

- `frontend/index.html`
- `frontend/css/components.css`
- `frontend/js/app.js`
- `frontend/js/ui.js`
- `frontend/js/overview.js`
- `frontend/js/historical-overview.js`
- `tests/test_frontend.py`
- `Prompts/phase2_prompt_pack/11_PROGRESS_TRACKER.md`

### UI evidence

- Real API values: a live populated-database HTTP smoke request returned 570,000 observations, attributed-purchase rate `0.06085`, 24 monthly points, 9 channels, and 8 categories; the page shell and new module both returned HTTP 200.
- Loading: the historical section starts with an `aria-live` loading status plus summary and three-chart skeletons; content/empty/error regions remain hidden until resolution.
- Empty: zero observations produce the explicit `No campaign history is loaded yet` state without fabricated chart values.
- Error/retry: a failed historical request shows the unavailable region and the existing page-level Overview error; `Try again` forces all cached Overview requests, clears the banner before retry, and restores rendered content on success.
- Global backend status restoration: failed Overview dependencies dispatch `is-offline`; a fully successful retry dispatches `is-online` with the backend version.
- Accessibility: semantic headings/lists/definition list, SVG `title`/`desc`, complete visually-hidden monthly values, visible percentage and observation text for every bar, keyboard-focusable data points, and no color-only meaning.
- Desktop/narrow layout: responsive CSS provides three-column desktop, two-column intermediate, and one-column narrow layouts with horizontally scrollable monthly SVG and wrapping labels. Visual browser inspection could not be performed because the in-app browser runtime reported no connected browser.
- Later-phase navigation: Historical Analysis has one enabled navigation control plus one Overview CTA leading to an explicit Step 6 shell; Model Training, Audience Explorer, and Campaigns remain disabled.

### Tests/checks

- Focused: `python -m pytest -q tests/test_frontend.py` → 15 passed, 1 upstream warning in 5.23s. Combined frontend/API run: 37 passed, 1 warning in 12.58s.
- Full: `python -m pytest -q` → 133 passed, 1 upstream Starlette deprecation warning in 48.94s.
- Browser: in-app browser discovery returned no available browser, so desktop/narrow visual inspection was not possible. Live HTTP checks against the running app returned real aggregate data and HTTP 200 for `/` and `/static/js/historical-overview.js`.
- JavaScript syntax: standalone shell `node --check` was unavailable because Node.js is not installed; the served-module contract and safe-rendering patterns are covered by focused tests, but browser execution remains to be visually confirmed when a browser backend is connected.
- Compile: `python -m compileall -q app scripts tests` → passed with no output.
- Dependency check: `python -m pip check` → `No broken requirements found.`
- Diff check: `git diff --check` → passed; only Git's informational LF→CRLF working-copy notices were emitted.

### Findings / deferred

- Visual rendering at desktop and narrow widths remains unverified due to the unavailable browser backend; responsive layout and interaction hooks have static contract coverage.
- The live full-data historical Overview query took 8.751 seconds with a warm local database, while the earlier Step 2 cold/warm measurements were about 33 seconds; the visible loading state keeps the request understandable, while query optimization remains Step 7 work.
- The unchanged Starlette/httpx deprecation warning remains.
- No full Historical Analysis workflow, model training/scoring, demographic linkage/query, Audience Explorer, campaign creation, export, or Step 6+ behavior was added.

### Next approved step

- Step 6 only

---

## Step 6 evidence — Historical Analyzer UI

### Work completed

- Replaced the Step 5 shell with a complete hash-routed Historical Analysis workspace while keeping only Model Training, Audience Explorer, and Campaigns disabled.
- Added a real-options form for optional analysis name, five bounded native multi-selects, inclusive dates, contacted-only exposure, and the three frozen conversion definitions with permanent plain-language positive-label explanations.
- Added client-side name/date/range/list/conversion validation for usability while preserving backend validation as authoritative; errors receive focus and leave the submitted form intact.
- Added duplicate-submission prevention, visible synchronous running state, safe backend/domain messages, force-refresh retry, and correct global backend online/offline restoration without marking a 4xx zero-match domain response as an outage.
- Added full completed-run rendering for eight summary KPIs, saved run ID, server-normalized filters, monthly aggregate table, four keyboard-accessible performance breakdown tabs, and four keyboard-accessible profile population tabs across eleven dimensions.
- Added the permanent positive–unlabeled interpretation statement and rendered only bounded aggregate values; no person-level table, identifier, contact field, or demographic scoring request exists.
- Added bounded newest-first Recent Analyses with stable failed-run labels and completed-run reopen through the saved run endpoint; 4xx failed runs refresh into the list without exposing internal diagnostics.
- Extended the shared API helper to turn Pydantic validation arrays into stable readable messages while retaining response status for correct online/offline UI handling.
- Added 12 Step 6 contract and API-backed journey tests, including all conversion definitions, filtered submission, list/reopen equality, zero match, empty history, safe rendering, accessibility hooks, and forbidden-data scans.

### Files changed

- `frontend/index.html`
- `frontend/css/components.css`
- `frontend/js/api.js`
- `frontend/js/app.js`
- `frontend/js/historical-analysis.js`
- `tests/test_frontend.py`
- `tests/test_historical_ui.py`
- `Prompts/phase2_prompt_pack/11_PROGRESS_TRACKER.md`

### End-to-end scenarios

- Default analysis: browser fixture defaults produced 6 contacted observations, 3 selected customers, 2 known positives, 1 unlabeled, a 66.7% positive-customer rate, $305 net sales, and $115 gross margin; normalized dates were 2025-01-01 through 2025-06-15.
- Filtered campaign/product analysis: `CMP_A` + `PRD_1` produced 3 observations and 2 selected customers; selected form values and normalized result filters agreed.
- Attributed-purchase definition: default browser run produced 2 positive and 1 unlabeled customer from 3 selected customers.
- Any-purchase definition: filtered browser run produced 2 positive and 0 unlabeled customers from 2 selected customers, with saved run ID 3.
- Response definition: filtered browser run produced 2 positive and 0 unlabeled customers from 2 selected customers, with saved run ID 4.
- Zero match: incompatible `CMP_A` + `PRD_2` selection returned the actionable inline zero-match message, preserved `Zero match` in the form, kept the backend badge online, and appeared in Recent Analyses as FAILED with only the stable public failure label.
- Reopen saved run: browser reopened run 3 and restored `Filtered campaign and product`, its normalized filters, aggregates, breakdowns, and profiles; automated API-backed reopen matched the original full snapshot exactly.
- Backend unavailable/retry: stopping the local fixture server changed the page banner to `Unable to reach the backend: Failed to fetch` and the global badge to unavailable; restarting it and choosing Try again hid the banner, restored the workspace, and set the badge to online.
- Narrow viewport: browser validation at 375px showed usable stacked form/recent/results content. An initial hidden table-header label caused root overflow; after correction `documentWidth`, `bodyWidth`, and `viewportWidth` all measured 375px.
- Accessibility/focus/keyboard: labels exposed every control correctly; result/error headings receive focus; running announcements use `aria-live`; ArrowRight moved the profile tab from Selected to Known positive and updated its aggregate summary; Home/End/ArrowLeft hooks are covered by tests.
- No person-level data: browser and serialized API results contained aggregates only; focused tests rejected fixture customer IDs, person fields, phone/name markers, SQL text, demographic API requests, propensity/scoring references, and unsafe `innerHTML` rendering.

### Tests/checks

- Focused: `python -m pytest -q tests/test_historical_ui.py` → 12 passed, 1 upstream warning in 7.14s. Combined frontend/UI/API run: 50 passed, 1 warning in 22.43s.
- Full: `python -m pytest -q` → 146 passed, 1 upstream Starlette deprecation warning in 56.78s.
- Browser: Chrome extension against a temporary seven-observation/four-customer SQLite fixture completed every required journey listed above at normal and 375px widths. Desktop and narrow screenshots were inspected as local-only evidence and were not added to the repository.
- Compile: `python -m compileall -q app scripts tests` → passed with no output.
- Dependency check: `python -m pip check` → `No broken requirements found.`
- Diff check: `git diff --check` and trailing-whitespace scans of the two new Step 6 files passed; only Git's informational LF→CRLF working-copy notices were emitted.

### Findings / deferred

- Browser validation used a temporary small fixture so all conversion/error/reopen paths remained fast and reproducible. The populated 570K-row database was not used for another browser submission; its aggregate/cohort correctness and measured response times remain recorded in Steps 2–5.
- The native multi-selects are keyboard accessible and bounded but require Ctrl/Command for multiple values; helper text is permanent. A custom dependency-free picker was not necessary for the POC.
- Broad full-data synchronous analysis remains approximately 29 seconds from Step 3 evidence, and query-plan/index optimization remains Step 7 work.
- The unchanged Starlette/httpx deprecation warning remains.
- No model training/scoring, demographic linkage/query, propensity workflow, Audience Explorer, campaign creation, export, background jobs, schema changes, API endpoint changes, or Step 7 functionality was added.

### Next approved step

- Step 7 only

---

## Step 7 evidence — Hardening, performance, documentation

### Work completed

- Audited the complete Phase 1/2 schema, repository/service/router separation,
  aggregate-only API/UI contracts, customer-grain semantics, disabled later-phase
  navigation, public sanitization, dependency set, and data/LFS integrity.
- Closed the remaining date contract gap: submitted ranges must be inside the
  loaded historical contact-date range and return a stable 422 otherwise;
  inclusive in-range boundaries remain accepted.
- Made normalized historical filter predicates indexable by removing redundant
  `TRIM()` wrappers. Imported text is already stripped, and the full-data narrow
  plan now selects the existing campaign/product composite index.
- Added a dedicated hardening suite for every list exactly at/above its limit,
  out-of-range dates, indexable predicates, locked-database logging/sanitization,
  unexpected service failures, and corrupt saved JSON.
- Updated the README, added the complete Phase 2 implementation summary, completed
  all 115 acceptance items, and confirmed that the Phase 3 handoff document
  matches the implemented saved-run contract.
- Ran populated-database reconciliation, plan/timing evidence, every live Phase
  1/2 route, full-data browser rendering, and the backend outage/retry journey.

### Files changed

- `README.md`
- `app/repositories/historical_repository.py`
- `app/routers/historical.py`
- `app/services/historical_analysis_service.py`
- `tests/test_phase2_hardening.py`
- `docs/PHASE_2_IMPLEMENTATION_SUMMARY.md`
- `Prompts/phase2_prompt_pack/10_PHASE_2_ACCEPTANCE_CHECKLIST.md`
- `Prompts/phase2_prompt_pack/11_PROGRESS_TRACKER.md`

### Full-data reconciliation

- Database/table counts: schema version 2; customers 125,000; campaign sales
  570,000; demographics 5,000,000; all Phase 1 reconciliation statuses `OK`.
- Overview direct-SQL comparison: 570,000 observations; 563,240 contacted;
  132,798 engaged; 76,557 responses; 54,450 purchases; 34,273 attributed
  purchases; 121,016 customers; 96 campaigns; 36 products; $10,894,336.96 net
  sales; $5,102,167.06 gross margin; 2024-01-01 through 2025-12-31. Service and
  direct read-only SQL matched exactly.
- Monthly rollup: 24 direct month groups summed to every overview count and both
  financial totals exactly.
- Broad cohort comparison: default returned 563,240 observations, 120,886
  selected customers, 25,502 positives, and 95,384 unlabeled; saved service and
  independent SQL matched.
- Narrow cohort comparison: `CMP0086` + `PRD011` returned 14,037 observations and
  customers. Independent attributed/any-purchase/response positives were
  626 / 1,015 / 1,703, matching saved runs.
- Positive + unlabeled invariant: broad `25,502 + 95,384 = 120,886`; narrow
  attributed `626 + 13,411 = 14,037`, any purchase `1,015 + 13,022 = 14,037`,
  and response `1,703 + 12,334 = 14,037`.
- Saved snapshot check: response run 6 matched direct observation/customer and
  conversion counts plus $467,154.32 net sales / $252,749.20 gross margin at
  creation time; stored normalized filters matched the contract.

### Performance/query plans

| Operation | Cold | Warm | Query-plan/index notes |
|---|---:|---:|---|
| Options | 4.442s | 3.841s | Bounded fixed queries; existing simple indexes; repeat target met |
| Historical overview | 12.281s | 9.502s | Full scan plus temporary distinct/group B-trees; above ~5s target |
| Broad default analysis | 53.914s | 60.127s | Date index, materialized matches, customer/profile B-trees; above ~10s target |
| Narrow analysis | 15.069s | 14.398s | Existing campaign/product composite index; baseline profiles remain material |
| Recent list | 0.044s | 0.049s | Newest-first run index; bounded 20-row decode |
| Reopen saved run | 0.050s | 0.049s | Primary-key lookup and bounded snapshot validation |

- Composite index added: No.
- Evidence/rationale: removing `TRIM()` changed the representative 14,037-row
  narrow count from a contact-date scan (3.2799s) to the existing
  `idx_campaign_sales_campaign_product_pu` lookup (0.0274s). Broad work selects
  almost all rows and is dominated by grouped aggregates/profiles, so another
  composite index has no demonstrated benefit. A speculative full-range scan
  variant was measured and removed because its benefit was not stable.

### Failure-path results

- Empty DB: options/overview returned typed zero/empty responses; create returned
  the stable not-loaded 400 response.
- Invalid bounds/dates: all five lists accepted the exact maximum and rejected one
  above with 422; reversed and outside-available-range dates returned stable 422.
- Duplicate/blank options: deterministic de-duplication and exclusion passed.
- No matches/multiple rows/zero contacts/inconsistent labels: stable zero-match
  400, customer-grain semantics, finite zero-denominator rates, and failed
  no-results persistence passed.
- Locked DB: internal locked/path detail was logged; public response was the
  stable sanitized 503.
- Corrupt saved JSON: reopen returned only the stable sanitized 500; internal logs
  retained the diagnostic.
- Failed run reopening: list/reopen exposed only stable public failed metadata.
- Unexpected exception sanitization: private SQL/path detail was logged; the
  public response was exactly the generic 500 contract.
- Browser retry: backend stop produced the visible alert and `Backend unavailable`;
  restart plus `Try again` removed the alert, reloaded real data, preserved dates,
  and restored `Backend online`.

### Final commands

- `python -m pip check`: `No broken requirements found.`
- `python -m pytest -q`: 158 passed in 102.18s; no warnings reported.
- `python -m pytest -q tests/test_phase2_hardening.py`: 12 passed in 13.15s.
- `python -m compileall -q app scripts tests`: passed with no output.
- `git diff --check`: passed; only informational LF-to-CRLF notices.
- Runtime: `/`, `/docs`, all eight Phase 1 endpoints, and all five Phase 2
  operations returned expected 200/201 statuses.
- Data integrity: all three LFS objects and SHA-256 hashes match the frozen
  manifest; `git status --short -- data` remained empty.
- `git status --short`: implementation/docs remain uncommitted on the required
  base; ignored `data/campaign_poc.db` is absent from status.

### Acceptance summary

- Critical failures: None; 115/115 checklist items marked PASS.
- Other failures/partials: None. Approximate warm overview/broad targets are not
  met, with measured evidence and explicit documentation as allowed by acceptance.
- Residual risks: Medium — synchronous broad run near one minute and overview near
  ten seconds repeat. Low — SQLite single-writer/local architecture, synthetic
  data, snapshot staleness, and unlabeled interpretation.
- Phase 3 recommendation: Go, contingent on Phase 3 honoring completed-run
  reconstruction/reconciliation and not treating aggregate snapshots as a matrix.

---

## Post-completion validation evidence — 2026-08-21

### Acceptance checklist rerun

- Required/resulting HEAD remained
  `c6c9f41ea257aa33ae196b75cc8f76f8419431e7`; Phase 2 implementation and
  documentation remained uncommitted, and no `data/` worktree change appeared.
- Acceptance result: 115/115 checklist items PASS; zero failed, partial, or
  not-tested items; recommendation remains Go for Phase 3 subject to the recorded
  synchronous-performance and snapshot limitations.
- `python -m pip check`: `No broken requirements found.`
- `python -m pytest -q`: 158 passed in 54.73s; no warnings reported.
- `python -m compileall -q app scripts tests`: passed with no output.
- `git diff --check`: passed; informational LF-to-CRLF notices only.
- `python scripts/validate_data.py --json`: overall `OK` in 11.694s; customers
  125,000; campaign sales 570,000; demographics 5,000,000; zero invalid
  campaign-customer references; zero PU consistency violations; all 21 required
  indexes present.
- All three frozen dataset SHA-256/LFS object hashes matched the manifest.
- Scope scan found no model artifact, training/scoring dependency or
  implementation, demographic query in the historical-analysis path, or enabled
  later-phase navigation.

### Phase 3 handoff audit

- Latest completed local saved run: `analysis_run_id=10`, conversion definition
  `ATTRIBUTED_PURCHASE`.
- Stored and independently recomputed values matched: 14,037 observations;
  14,037 selected customers; 626 known positives; 13,411 unlabeled customers;
  `626 + 13,411 = 14,037`.
- Saved filters/results contained no `customer_id`, `person_id`, PII, raw SQL, or
  persisted customer-membership list. No model, score, audience table, or model
  artifact was present.
- Focused schema, persistence, and API handoff suite: 54 passed in 26.74s.
- Compile and diff checks passed. The audit made no implementation or data-file
  changes and did not begin Phase 3.

---

## Running decisions and deviations

Record every deviation from the prompt, who approved it, and why.

| Date | Decision/deviation | Reason | Approval/evidence |
|---|---|---|---|
| 2026-08-21 | None | Phase 2 implementation follows the frozen contract; measured performance misses are documented limitations, not unapproved scope deviations. | Acceptance checklist 115/115 PASS; Phase 3 handoff audit passed. |

## Final known limitations

- Analytics are synchronous in the POC.
- Results are snapshots and do not auto-refresh after source-data changes.
- Unlabeled customers are not confirmed negatives.
- Analysis quality depends on synthetic historical data.
- No causal inference is claimed; metrics are descriptive, not model metrics.
- No model is trained and no demographic prospect is scored.
- SQLite/local single-user architecture is not production multi-user infrastructure.
- Broad and overview repeat timings exceed the approximate local POC targets.

## Final changed-file manifest

- Schema/configuration: `app/database/schema.py`, `app/dependencies.py`,
  `scripts/init_db.py`.
- Historical backend/API: `app/repositories/historical_repository.py`,
  `app/services/historical_service.py`,
  `app/services/historical_analysis_service.py`, `app/schemas/historical.py`,
  `app/routers/historical.py`, `app/main.py`.
- Frontend: `frontend/index.html`, `frontend/css/components.css`,
  `frontend/js/api.js`, `frontend/js/app.js`, `frontend/js/ui.js`,
  `frontend/js/overview.js`, `frontend/js/historical-overview.js`,
  `frontend/js/historical-analysis.js`.
- Tests: `tests/test_database_schema.py`, `tests/test_data_api.py`,
  `tests/test_data_reconciliation.py`, `tests/test_health.py`,
  `tests/test_frontend.py`, `tests/test_historical_service.py`,
  `tests/test_historical_analysis_service.py`, `tests/test_historical_api.py`,
  `tests/test_historical_ui.py`, `tests/test_phase2_hardening.py`.
- Documentation/evidence: `README.md`, `docs/PHASE_2_IMPLEMENTATION_SUMMARY.md`,
  `Prompts/phase2_prompt_pack/10_PHASE_2_ACCEPTANCE_CHECKLIST.md`, and
  `Prompts/phase2_prompt_pack/11_PROGRESS_TRACKER.md`.
