# Step 7 — Real App API Integration Tests

Add tests that start the actual FastAPI lifespan and do NOT monkeypatch the executor.

Mandatory assertions:

GET `/api/potential-customer-search/options`
→ `workflow_available == true`.

POST valid search:
→ 201
→ search run persisted
→ status is QUEUED/PROCESSING/COMPLETED
→ not BLOCKED due missing executor.

Poll status until terminal in bounded test fixture.

Test real runtime paths for:
- exact-result reuse
- intelligence reuse
- blocked insufficient history
- controlled failure
- export download
- result history/detail
- app shutdown.

Include a regression test that fails if `app.main` no longer configures Phase11 executor.

If full real Phase10 work is too heavy for ordinary integration tests, use bounded fixtures while keeping real application composition unchanged.

Create:
`docs/evidence/phase11_runtime_closure/07_REAL_APP_API_TESTS.md`

STOP.
