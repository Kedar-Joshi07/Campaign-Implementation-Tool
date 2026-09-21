# Phase 11 Runtime Coordinator and Application Composition

## Scope and baseline

- Prompt: `03_STEP_03_IMPLEMENT_RUNTIME_COORDINATOR_AND_APP_COMPOSITION.md`
- Baseline: `9009e23b750000d3f3d29e09204281f3d301e640`
- Date: 2026-09-20 (Asia/Calcutta)
- Result: **PASS**
- Step 4 startup resumption: not started

Step 3 implements the bounded Phase 11 runtime coordinator, composes it into the real FastAPI lifespan, connects the production submission seam, proves normal-runtime availability, and adds focused regression coverage.

## Implementation

### Bounded coordinator

Created `app/jobs/phase11_search_coordinator.py` with:

- `ThreadPoolExecutor(max_workers=2)`;
- five-second interruptible Phase 10 polling;
- a maximum of 100 tracked active/queued futures;
- active search IDs and futures keyed by `search_run_id`;
- active-ID reservation before future creation;
- same-ID concurrent submission suppression;
- terminal-run rejection before scheduling;
- real `execute_phase11_search_safely` delegation;
- real materializer/project-root injection;
- safe outer exception handling;
- active/future cleanup in `finally`;
- shutdown-event wake-up and queued-future cancellation;
- idempotent shutdown and submit-after-shutdown rejection;
- durable `PROCESSING`/`QUEUED` discovery API reserved for Step 4 wiring.

No model, scoring, ranking, smart-reuse, snapshot, or export business logic was moved into the coordinator.

### Explicit submission-service configuration

Added:

```python
configure_phase11_search_executor(executor)
reset_phase11_search_executor()
```

The existing `PHASE11_SEARCH_EXECUTOR` compatibility seam remains, but production startup and shutdown no longer mutate it ad hoc. Invalid non-callable configuration fails explicitly.

Existing tests that intentionally exercise the disconnected service boundary now call the reset function explicitly. The normal application lifecycle is tested separately as available.

### Real FastAPI lifespan composition

`app.main` now performs this Phase 11 composition before the existing reconciliation sequence:

1. initialize/verify `DATABASE_PATH`;
2. create `ResultSnapshotMaterializer(PROJECT_ROOT)`;
3. create `Phase11SearchCoordinator`;
4. configure the submission executor with `coordinator.submit`;
5. log the bounded worker and polling configuration.

If composition fails, the executor is reset, any partially created coordinator is shut down, and the application logs explicit workflow unavailability. It does not falsely advertise readiness.

On shutdown:

1. the submission seam is reset;
2. the coordinator stops accepting work and shuts down cleanly;
3. the existing Phase 10/model-training executor retains its existing shutdown path.

Step 3 intentionally does not call `resume_durable_searches`; startup recovery belongs to Step 4.

## Submission behavior

The HTTP submission path still:

1. validates the request;
2. persists an immutable search run;
3. calls the configured executor seam;
4. returns the latest durable projection.

`coordinator.submit` performs only a keyed registry check, one indexed durable-run read, and `ThreadPoolExecutor.submit`. It does not wait for the coordinator future, a Phase 10 future, model training, scoring, ranking, or 5M snapshot materialization.

Depending on the worker race, the initial HTTP response may truthfully be `QUEUED`, `PROCESSING`, or an already reached terminal state. API compatibility tests now verify monotonic asynchronous status instead of incorrectly requiring every immediate projection to equal the initial `QUEUED` representation.

## Process ownership and boundedness

Static inspection of `app/jobs/phase11_search_coordinator.py` confirms it contains none of:

- `ProcessPoolExecutor`;
- Phase 10 heavy submitters;
- `Future.result()`;
- `threading.Thread` or per-click thread construction.

Phase 10 remains the sole owner of the existing one-worker ProcessPool and all model/scoring work. Phase 11 owns only two bounded coordination threads, durable polling, and existing result materialization.

## Focused test coverage

New test module: `tests/test_phase11_runtime_coordinator.py`

Covered:

- frozen production defaults;
- invalid/unbounded configuration rejection;
- one accepted search;
- same-ID concurrent deduplication;
- active registry cleanup;
- terminal search ignore;
- Phase 10 wait and bounded repoll;
- unexpected runner exception to safe durable failure;
- no private exception text persisted;
- shutdown waking a long poll;
- durable `PROCESSING` state preserved on shutdown;
- submit-after-shutdown rejection;
- database-path isolation;
- real FastAPI lifespan executor configuration;
- `/options` reports `workflow_available=true`;
- executor reset after lifespan shutdown.

Test results:

```text
python -m pytest tests\test_phase11_runtime_coordinator.py -q
13 passed in 36.55s

python -m pytest \
  tests\test_phase11_runtime_coordinator.py \
  tests\test_health.py \
  tests\test_phase11_api_backward_compatibility.py -q
35 passed in 64.67s
```

The three pre-existing backend tests that intentionally cover an absent executor were made explicitly disconnected and rerun:

```text
3 passed in 27.80s
```

The updated asynchronous API contract regression was rerun independently:

```text
1 passed in 13.91s
```

An attempted complete `test_phase11_business_search_form.py` run reached all backend cases but browser cases could not start because the current Python environment does not contain the `playwright` package. Browser certification is not a Step 3 acceptance condition and is assigned to Step 8. No browser result is claimed here.

## Real normal-runtime proof

Launched exactly:

```text
python -m uvicorn app.main:app
```

Observed startup:

```text
Application starting | name=Campaign Implementation Intelligence version=0.1.0 environment=development
SQLite schema initialized or verified | path=data\campaign_poc.db version=18
Phase 11 runtime composition completed | workers=2 poll_seconds=5.0
Compute startup reconciliation completed | failed_stale_jobs=0
Phase 10 startup reconciliation completed | resumed_orchestrations=0
Campaign export startup reconciliation completed | reconciled_stale_exports=0
Result export startup reconciliation completed | reconciled_stale_exports=0
Application startup complete.
```

Real request:

```http
GET /api/potential-customer-search/options
```

Observed projection:

```json
{"workflow_available":true,"profiles":10,"available_profiles":10}
```

- HTTP status: `200`
- `workflow_available`: `true`
- normal `app.main`: used
- executor injection/monkeypatch: none
- custom Step 19/20 server: not used

The uvicorn application then shut down cleanly and reset the executor seam.

## Additional verification

```text
python -m compileall -q app
PASS

git diff --check
PASS
```

## Decision

**PASS - Step 3 runtime coordinator and real application composition are complete.**

The normal runtime now advertises the Phase 11 workflow as available and schedules persisted searches into a bounded production coordinator without waiting for heavy Phase 10 work. Startup reconciliation and restart recovery have deliberately not been wired yet; that remains Step 4.
