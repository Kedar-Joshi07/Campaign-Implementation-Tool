# Step 7 — Phase 2 Hardening, Performance, and Documentation

## Objective

Audit Phase 2 end-to-end against the freeze, correct defects within scope, validate against the real datasets where practical, and leave a documented Phase 3-ready historical-analysis foundation.

Do not add Phase 3 functionality.

## 1. Full regression and contract audit

Verify:

- all Phase 1 tests and behavior remain healthy;
- all Phase 2 schema/API/UI contracts match the prompt pack;
- no duplicated or alternate analytics implementation exists;
- no API returns raw people, PII, SQL, paths, or diagnostic details;
- positive/unlabeled semantics are customer-grain and consistent across code, API, UI, tests, and docs;
- Model Training, Audience Explorer, and Campaigns remain disabled;
- Git LFS data and hashes are unchanged.

Run the full suite from a clean process/environment state.

## 2. Independent reconciliation

Using the full populated database when practical, independently verify selected headline values with direct parameterized/read-only SQL:

- overall observation/contact/engagement/response/purchase/attributed counts;
- distinct customers/campaigns/products;
- net sales and gross margin totals;
- monthly totals sum to overview totals where definitions align;
- selected cohort observation and distinct-customer counts;
- positive + unlabeled = selected;
- conversion-definition differences for at least one cohort;
- saved result matches recomputed source aggregates at creation time.

Record queries conceptually and results; do not expose or commit the populated SQLite database.

## 3. Query plans and performance

Measure cold and warm behavior separately where possible:

- `/api/historical/options`
- `/api/historical/overview`
- broad two-year default analysis
- narrow campaign/product analysis
- recent-run list and reopen

Use `EXPLAIN QUERY PLAN` for the expensive queries. Confirm useful indexes are selected for narrow filters.

Only add a composite index when evidence shows a material benefit without unacceptable database growth/write cost. If added:

- document the query it serves;
- test its presence idempotently;
- compare before/after timing and query plan;
- keep the total index set restrained.

Target warm response times from the freeze, but report actual hardware-dependent results honestly. Do not fake asynchronous processing to hide slow SQL.

## 4. Failure and edge-path testing

Exercise:

- empty database/history
- invalid/reversed/out-of-range dates
- every list at and above its limit
- duplicate/blank option values
- no matching records
- multiple observations per customer
- zero contacted denominator
- inconsistent `pu_label`/attribution rows in a fixture
- locked/unavailable database
- corrupt saved JSON
- failed run reopening
- unexpected service exception
- backend unavailable in browser then successful retry

Public responses must remain stable and sanitized. Internal logs/metadata must retain enough detail to diagnose failures.

## 5. Documentation

Update repository documentation with:

- Phase 2 objective and boundary
- schema version 2 and migration behavior
- historical analysis semantics
- conversion-definition table
- customer-grain positive/unlabeled explanation
- endpoint list and sample requests
- Historical Analysis UI workflow
- performance notes and measured values
- test commands/results
- known limitations
- explicit Phase 3 boundary/handoff

Update the implementation summary and progress tracker. Do not rewrite or delete the original Phase 1 prompt pack.

## 6. Known limitations to state honestly

At minimum:

- analytics are synchronous in the POC;
- results are snapshots and do not auto-refresh after underlying data changes;
- unlabeled is not negative;
- analysis quality depends on synthetic historical data;
- no causal inference is claimed;
- metrics are descriptive, not model performance metrics;
- no model is trained and no prospect is scored;
- SQLite/local single-user architecture is not production multi-user infrastructure.

## 7. Final validation commands

Run and record:

```text
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
git status --short
```

Also run the app and verify `/`, `/docs`, all Phase 1 endpoints, and all five Phase 2 endpoints.

## Final response format

Report:

1. Base and resulting HEAD.
2. Complete changed-file list grouped by schema/backend/API/frontend/tests/docs.
3. Implemented Phase 2 behavior.
4. Test and runtime results.
5. Full-data reconciliation evidence.
6. Query plans/timings and any index decision.
7. Browser validation.
8. Known limitations and residual findings with severity.
9. Confirmation that Phase 3+ functionality was not added.
10. Pass/fail against `10_PHASE_2_ACCEPTANCE_CHECKLIST.md`.
11. Go/no-go recommendation for Phase 3.

Do not commit or push unless explicitly authorized.
