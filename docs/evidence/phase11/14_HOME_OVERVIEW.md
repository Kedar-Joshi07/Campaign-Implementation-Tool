# Phase 11 Step 14 — Home / Overview Business Dashboard

Date: 2026-09-17

## Outcome

The Home route is now a business-only dashboard. The visible screen contains:

- Potential Customers Available;
- Search Runs;
- Completed Results;
- Latest Result Count;
- the five newest searches with status, result count, delivery profile and View Result action;
- a primary Find Potential Customers action; and
- a View All Results action.

The previous technical foundation, reconciliation, health, schema and historical-performance markup remains retained in the repository under the hidden `legacy-overview-content` boundary. It is not visible and its reconciliation or historical APIs are not loaded by the Home route.

## API and layering

Added additive business endpoints:

- `GET /api/business/overview`
- `GET /api/business/recent-results?limit=5`

The implementation uses schema, router, service and repository layers:

- `app/schemas/business_dashboard.py`
- `app/routers/business.py`
- `app/services/business_dashboard_service.py`
- `app/repositories/business_dashboard_repository.py`

The overview query reads the latest completed demographic import's recorded `rows_inserted` value and aggregate search-run metadata. The recent-results query reads at most 5–10 indexed search-run rows. Neither query reads demographic people, scored prospects, result membership files, model artifacts or rank-boundary data.

The canonical database read returned 5,000,000 potential customers, zero current search runs and zero recent results in approximately 195 ms. No imports, training, scoring, generation or population reconciliation ran.

## Business and failure states

- An empty history explains that no searches exist and offers Find Potential Customers.
- A backend failure replaces the metrics with Unavailable, clears partial result cards, shows a business-safe retry message, and sets the global backend state offline.
- Try again forces both dashboard requests to bypass their caches.
- A successful retry hides the error, restores metrics/results or the valid empty state, and restores the global backend online state.
- Visible Home content does not expose model IDs, analysis IDs, scoring IDs, PU terminology, artifact information, rank-boundary metrics, database/schema details or reconciliation controls.

## Verification

Focused service/API tests:

```text
python -m pytest tests/test_phase11_home_dashboard.py -m "not browser" -q
2 passed, 2 deselected
```

Focused real system-browser tests:

```text
python -m pytest tests/test_phase11_home_dashboard.py -m browser -q
2 passed, 2 deselected
```

The browser checks cover business KPI rendering, bounded recent-result cards, both primary navigation actions, prohibited technical vocabulary, absence of legacy Home API requests, backend-unavailable behavior, retry recovery, empty state and global connection status recovery.

Adjacent real system-browser navigation regression:

```text
python -m pytest tests/test_phase11_business_navigation.py -q
28 passed
```

Updated frontend contract checks:

```text
python -m pytest \
  tests/test_frontend.py::test_historical_overview_is_retained_but_home_uses_bounded_business_apis \
  tests/test_frontend.py::test_overview_retry_restores_global_backend_status_after_success -q
2 passed
```

Python compilation and OpenAPI registration also passed for both new endpoints.

## Guardrail confirmation

- No canonical import was run.
- No model training or prospect scoring was run.
- No 5M population scan or full reconciliation was run.
- No result membership or contact PII is returned by either Home endpoint.
- No files were staged, committed or pushed.
