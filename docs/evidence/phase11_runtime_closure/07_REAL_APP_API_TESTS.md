# Phase 11 Real-App API Integration Tests

## Scope and baseline

- Prompt: `07_STEP_07_REAL_APP_API_INTEGRATION_TESTS.md`
- Baseline: `9009e23b750000d3f3d29e09204281f3d301e640`
- Date: 2026-09-21 (Asia/Calcutta)
- Result: **PASS**

Step 7 adds API integration coverage that enters and exits the actual FastAPI lifespan and exercises the production Phase 11 runtime coordinator. The test suite does not replace or monkeypatch `PHASE11_SEARCH_EXECUTOR`, `Phase11SearchCoordinator`, `execute_phase11_search_safely`, or `ResultSnapshotMaterializer`.

## Added integration module

New module:

```text
tests/test_phase11_real_app_api.py
```

The module contains two integration tests:

1. a focused composition regression that fails if `app.main` stops configuring the Phase 11 executor; and
2. a complete bounded API workflow covering successful reuse, terminal error paths, results, export, and shutdown.

Only the database path and project/artifact root are redirected to pytest temporary directories. This keeps the canonical database and repository artifacts untouched while preserving the real application composition and real HTTP router/service path.

## Bounded Phase 10 fixture

The comprehensive test prepares a small durable fixture before application startup:

- 40 historical customers/campaign observations;
- 60 demographic prospects;
- one real READY Phase 10 generation;
- one different product context that resolves to insufficient history; and
- two queued Phase 11 runs for startup recovery coverage.

The small READY generation lets the normal Phase 11 request path perform real Phase 10 compatibility checks and all-reuse finalization without invoking full-scale training/scoring work. Fixture preparation uses the production Phase 10 orchestration services. It does not change application composition.

## Mandatory API and lifecycle assertions

### Executor wiring and workflow availability

Inside `TestClient(app)` with the actual lifespan:

- `PHASE11_SEARCH_EXECUTOR` is non-null;
- `GET /api/potential-customer-search/options` returns HTTP 200;
- `workflow_available` is `true`;
- after lifespan exit, `PHASE11_SEARCH_EXECUTOR` is reset to null.

This is the explicit regression gate for the `app.main` executor wiring. Removing the call that configures `phase11_coordinator.submit` makes the test fail.

### Valid POST and bounded terminal polling

The test submits a valid request through:

```text
POST /api/potential-customer-search/runs
```

It verifies:

- HTTP 201;
- the durable search row exists independently in SQLite;
- the immediate state is `QUEUED`, `PROCESSING`, or `COMPLETED`;
- the response is not fail-closed as `BLOCKED` because of a missing executor; and
- status polling through the real status route reaches a terminal state within a 20-second bound.

No API call waits synchronously for the search to finish.

## Runtime-path results

The isolated database starts search IDs at 1, making the exercised paths easy to inspect:

| Search | Preparation | Terminal result | Assertion |
| --- | --- | --- | --- |
| 1 | Different product with insufficient history | `BLOCKED` | Real startup coordinator observes terminal Phase 10 insufficiency; message is not the missing-executor message |
| 2 | READY identity with a deliberately unsupported persisted Audience Engine filter | `FAILED` | Production safe wrapper persists only the fixed safe error and no collaborator detail |
| 3 | Valid HTTP POST over existing compatible intelligence | `COMPLETED`, `INTELLIGENCE_REUSE` | A new immutable snapshot is materialized and validated |
| 4 | Second intentional valid HTTP POST with the same exact targeting identity | `COMPLETED`, `EXACT_RESULT_REUSE` | The same snapshot ID is reused without another membership build |

Startup reported two scheduled durable searches, proving the BLOCKED and FAILED fixture cases were executed through startup reconciliation rather than called directly by the test.

## Results history and detail

The suite exercises the normal routes:

```text
GET /api/potential-customer-search/results
GET /api/potential-customer-search/runs/{search_run_id}/result
```

It verifies that history includes all four terminal outcomes with their correct result sources/statuses. The exact-reuse detail reports:

- `COMPLETED`;
- `EXACT_RESULT_REUSE`;
- `CURRENT` currentness;
- `download_eligible == true`; and
- snapshot provenance pointing to the same immutable snapshot used by the intelligence-reuse request.

## Governed export path

The exact-reuse result is downloaded through:

```text
GET /api/potential-customer-search/runs/{search_run_id}/download
```

The response is HTTP 200 with `X-Export-Profile: EMAIL_CONTACT_V1`. Its CSV header exactly matches the frozen profile `output_columns` contract.

The fixture deliberately contains no email contact values, so a governed header-only export is the truthful result. The terminal export audit is checked for:

- `COMPLETED` status;
- CSV row count equal to actual streamed data rows;
- row count equal to deliverable count;
- selected count equal to deliverable plus undeliverable;
- `CURRENT` currentness.

This validates that a zero-deliverable channel result still downloads and audits correctly rather than fabricating contact data.

## Controlled failure and privacy

The controlled-failure case keeps a valid persisted targeting contract and READY intelligence but supplies an unsupported Audience Engine filter. The real runner catches the collaborator validation failure and persists:

```text
The search could not be completed. Please try again.
```

The public status response uses the fixed business-safe FAILED message. Neither response includes the unsupported filter name or an exception/traceback.

## Shutdown

Exiting the real FastAPI lifespan verifies:

- executor disconnection;
- bounded coordinator-pool closure; and
- all four exercised searches remain durable terminal records.

No worker is left detached after `TestClient` closes.

## Test results

Step 7 integration module:

```text
python -m pytest tests\test_phase11_real_app_api.py -q
2 passed in 59.54s
```

Adjacent runtime, recovery, backward-compatibility, and export regression:

```text
python -m pytest \
  tests\test_phase11_runtime_coordinator.py \
  tests\test_phase11_restart_recovery.py \
  tests\test_phase11_api_backward_compatibility.py \
  tests\test_phase11_omnichannel_export_engine.py -q

49 passed in 97.23s
```

Combined verified result: **51 passed**.

## Repository impact and sequencing

- Added `tests/test_phase11_real_app_api.py`.
- Added this evidence document.
- No production code or executor behavior was changed by Step 7.
- Step 5 was subsequently completed and certified in `05_CONCURRENCY_IDEMPOTENCY.md`.
- Step 8 was not started.

## Decision

**PASS - Step 7 real-app API integration coverage is complete.**

The suite now fails if the application stops wiring the Phase 11 executor and proves that the actual lifespan can accept, persist, asynchronously execute, poll, project, export, audit, and safely terminate Phase 11 work across reuse, blocked, and controlled-failure paths.
