# Phase 1 Implementation Summary

## Delivered scope

Phase 1 delivers a local Campaign Implementation Intelligence foundation using
FastAPI, SQLite, and a static HTML/CSS/Vanilla JavaScript frontend. It includes:

- idempotent database/schema/index initialization;
- streaming and batched CSV/CSV.GZ imports for customers, campaign sales, and
  the independent demographic prospect universe;
- persistent import audit records and fail-fast validation;
- reconciliation and data-quality reporting;
- aggregate status, summary, import-history, and reference APIs;
- functional Overview and Data Status views with loading, empty, failure, and
  retry behavior; and
- automated schema, import, reconciliation, API, UI-contract, failure-path,
  idempotency, and restart coverage.

No Phase 2 modeling, scoring, selection, activation, or production-platform work
is included.

## Architecture decisions

- One project virtual environment installs the root `requirements.txt`, which
  also includes all generator dependencies.
- The three canonical GZIP datasets are delivered through Git LFS; local SQLite
  database, WAL, and SHM files remain ignored.
- FastAPI serves both the API and static frontend; there is no frontend build
  toolchain.
- Routers own HTTP behavior, services own orchestration/business validation,
  repositories own read SQL, and the database package owns connections/schema.
- SQLite connections are operation-scoped, foreign keys are enabled, and a busy
  timeout plus WAL mode support safe local use.
- Large imports use standard-library streaming readers and bounded 10,000-row
  batches. Complete source files are never materialized in Python memory.
- Secondary indexes are created after bulk imports and all 17 are idempotent.
- Reference APIs return bounded aggregate results; no person/customer dump API
  exists.
- The 5-million-row demographic population has no key, foreign key, or inferred
  mapping to historical customers.

## Database schema

| Table | Purpose | Important constraints |
|---|---|---|
| `app_metadata` | Schema/application initialization metadata | Primary key on `key` |
| `data_import_runs` | RUNNING/COMPLETED/FAILED import audit | Checked status and nonnegative counters |
| `customers` | Frozen 22-column customer master | `customer_id` primary key |
| `campaign_sales` | Frozen 38-column history | Primary key plus enforced customer foreign key |
| `demographics` | Frozen 28-column prospect universe | `person_id` primary key; no customer linkage |

The schema also checks nonnegative numeric values and valid binary flags where
applicable. Reconciliation adds explicit FK, PU-label, and demographic household
arithmetic checks.

## APIs

- `GET /` — Phase 1 application UI
- `GET /docs` — generated OpenAPI documentation
- `GET /api/health` — lightweight connectivity/schema health
- `GET /api/version` — application identity and version
- `GET /api/data/status` — complete reconciliation and dataset import state
- `GET /api/data/summary` — aggregate application counts and coverage
- `GET /api/data/imports` — bounded, paginated import history
- `GET /api/reference/states` — indexed demographic counts by state
- `GET /api/reference/campaigns` — bounded/searchable campaign aggregates
- `GET /api/reference/products` — bounded/searchable product aggregates

SQLite and unexpected API exceptions are logged server-side and returned to
clients as stable, sanitized error responses.

## Import behavior

The required order is customers, campaign sales, then demographics. Headers must
exactly match the frozen 22/38/28-column schemas. Dates, numbers, flags, primary
keys, campaign customer references, and demographic household arithmetic are
validated. Both plain CSV and GZIP input are supported; demographics may be a
single file or deterministically ordered parts.

Imports refuse a nonempty target by default. `--replace` is explicit and scoped;
customer replacement is blocked while campaign rows exist. Each attempt records
its source and counters when the database is writable. A malformed row fails the
run instead of being skipped silently. Because batches commit incrementally, a
late failure can leave an auditable partial load that must be deliberately
replaced or loaded into a fresh database.

Replacement sources are preflighted before target deletion. Every part receives
a complete memory-bounded CSV/GZIP structural pass, so unreadable input, wrong
headers, malformed field counts, and truncated streams preserve existing rows.

## Test and validation coverage

The automated suite covers exact schemas, constraints, indexes, initialization
idempotency, all import formats/modes, duplicate prevention, failure metadata,
missing/wrong/corrupt input, invalid dates/FKs/household arithmetic, locked and
unavailable databases, reconciliation states, every API, frontend contracts,
startup behavior, and sanitized errors. The final acceptance run also exercises
the documented commands against the real generated files and restarts the
application against an existing database without data mutation.

## Measured real-data results

The Phase 1 dataset contains 125,000 customers, 570,000 campaign-sales rows, and
5,000,000 demographic rows. It contains 96 campaigns, 36 observed products, and
34,273 known-positive/attributed purchase records spanning 2024-01-01 through
2025-12-31.

Initial measured import times on the local development machine were:

| Operation | Time |
|---|---:|
| Customer import | 2.82 seconds |
| Campaign-sales import | 26.34 seconds |
| Demographic import | 135.02 seconds |
| Complete reconciliation after indexes | approximately 25–30 seconds |

The isolated Step 7 clean run measured 3.41 seconds for customers, 39.48 seconds
for campaign sales, and 202.12 seconds for demographics. First reconciliation
after index creation took 11.83 seconds; its idempotent repeat took 8.20 seconds.
Warm application endpoint checks measured approximately 0.55 seconds for health,
1.09 seconds for summary, 0.85 seconds for states, 1.57 seconds for 96 campaign
aggregates, and 0.67 seconds for 36 product aggregates. Machine load and OS file
cache affect these local timings.

## Known limitations

- This is a local POC, not a production multi-user or distributed deployment.
- Full `/api/data/status` reconciliation scans the large dataset and takes about
  25–30 seconds on the development machine; the UI caches the completed result
  for five minutes.
- SQLite supports this workload but permits only one writer at a time.
- Import batches commit incrementally rather than providing one 5-million-row
  transaction.
- Synthetic-data generators remain explicit operator commands and are not part
  of application startup.
- The test suite emits one external Starlette deprecation warning concerning its
  current HTTPX test-client compatibility layer; tests and runtime behavior pass.

## Phase 2 readiness

Phase 1 leaves versioned schema metadata, verified source domains, import audit
history, aggregate APIs, and an honest operational UI suitable as inputs to a
separately approved Phase 2 design. Before Phase 2, retain the frozen separation
between demographics and customers, define modeling governance and evaluation
criteria, and decide whether any new derived tables require explicit lifecycle
and refresh semantics. No Phase 2 implementation has been preemptively added.
