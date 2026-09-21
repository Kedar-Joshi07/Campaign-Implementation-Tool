# Phase 11 Startup Reconciliation and Restart Recovery

## Scope and baseline

- Prompt: `04_STEP_04_STARTUP_RECONCILIATION_AND_RESTART_RECOVERY.md`
- Baseline: `9009e23b750000d3f3d29e09204281f3d301e640`
- Date: 2026-09-20 (Asia/Calcutta)
- Result: **PASS**

Step 4 wires durable Phase 11 recovery into the real FastAPI lifespan and verifies restart behavior without processing searches synchronously during application startup.

## Runtime startup order

The real `app.main` lifespan now performs:

1. initialize/verify the database;
2. create `ResultSnapshotMaterializer(PROJECT_ROOT)`;
3. create the bounded `Phase11SearchCoordinator`;
4. connect the submission executor seam;
5. reconcile stale model jobs;
6. reconcile Phase 10 orchestrations;
7. call `phase11_coordinator.resume_durable_searches()`;
8. reconcile stale campaign exports;
9. reconcile stale result exports;
10. serve requests.

This ordering ensures that Phase 10 durable parents are resubmitted before Phase 11 begins polling the associated intelligence state. Export reconciliation occurs only after search resumption has been scheduled.

If Phase 11 composition is unavailable, the startup reconciliation records zero scheduled searches and the submission API continues to report workflow unavailability. If the bounded scheduling call itself fails, startup logs an explicit Phase 11 reconciliation failure without fabricating durable state.

## Bounded asynchronous recovery

`resume_durable_searches()` performs only bounded repository discovery and executor submission:

- scans `PROCESSING` first;
- then scans `QUEUED`;
- reads at most 100 records per repository page;
- respects the coordinator's 100-run tracked-work limit;
- suppresses IDs already active in the process;
- submits work to the fixed two-worker coordinator;
- returns without executing the orchestration loop in the startup thread.

The completion of one worker triggers a bounded durable refill, so additional queued work remains authoritative in SQLite rather than requiring an unbounded in-memory queue.

## State recovery behavior

### A. `QUEUED` before shutdown

Verified that startup discovers and schedules the run. The test deliberately blocks the worker and proves `resume_durable_searches()` has already returned, demonstrating that startup does not execute the search synchronously.

### B. `PROCESSING` while waiting on Phase 10

Verified with an A/B coordinator lifecycle:

1. application A advances the run to `PROCESSING` and reports `PHASE10_INTELLIGENCE` waiting;
2. application A shuts down cleanly;
3. the durable run remains `PROCESSING`;
4. application B discovers and submits the same run;
5. a second simultaneous resume call schedules zero duplicates;
6. exactly one application-B runner invocation reaches the expected terminal state.

No run is failed merely because the process stops between polling passes.

### C. `PROCESSING` before snapshot publication

Verified using the real `execute_phase11_search_safely` path with a ready compatible generation and the existing deterministic snapshot materializer contract:

- the restarted coordinator discovers the `PROCESSING` run;
- existing Phase 10 generation lineage is reused;
- membership is materialized;
- the snapshot validates;
- the search reaches `COMPLETED`;
- exactly one snapshot row exists;
- exactly one materializer call occurred;
- a second reconciliation schedules zero work and creates no second snapshot.

### D. `COMPLETED`

Verified that a completed run is not selected, submitted, or reprocessed. Its snapshot link and terminal status remain unchanged.

### E. `BLOCKED` and `FAILED`

Verified that both states remain terminal and are excluded from automatic startup resumption. Step 4 introduces no implicit retry or terminal-state reset.

## Duplicate heavy-work protection

The restart path does not directly start historical analysis, model training, scoring, or ranking. It calls the existing Phase 11 orchestration service, which re-reads durable Phase 10 state.

Protection exists at two levels:

1. Phase 11 active-ID deduplication prevents two coordinator loops for the same `search_run_id` in one process, including startup/request races.
2. Existing Phase 10 orchestration identity and active-orchestration lookup retain ownership of heavy work, so resuming Phase 11 observes or attaches to durable Phase 10 work rather than creating a second heavy executor.

No ProcessPool submission or wait was added to startup recovery.

## Tests

New test module: `tests/test_phase11_restart_recovery.py`

Focused result:

```text
python -m pytest tests\test_phase11_restart_recovery.py -q
5 passed in 17.69s
```

Consolidated affected regression:

```text
python -m pytest \
  tests\test_phase11_runtime_coordinator.py \
  tests\test_phase11_restart_recovery.py \
  tests\test_health.py \
  tests\test_phase11_api_backward_compatibility.py -q
40 passed in 67.13s
```

The test matrix covers all required A-E states, duplicate resume suppression, one-snapshot publication, asynchronous startup submission, lifespan ordering, coordinator shutdown, and API compatibility.

## Real normal-runtime proof

Launched exactly:

```text
python -m uvicorn app.main:app
```

Observed startup sequence:

```text
Application starting | name=Campaign Implementation Intelligence version=0.1.0 environment=development
SQLite schema initialized or verified | path=data\campaign_poc.db version=18
Phase 11 runtime composition completed | workers=2 poll_seconds=5.0
Compute startup reconciliation completed | failed_stale_jobs=0
Phase 10 startup reconciliation completed | resumed_orchestrations=0
Phase 11 startup reconciliation completed | scheduled_searches=0
Campaign export startup reconciliation completed | reconciled_stale_exports=0
Result export startup reconciliation completed | reconciled_stale_exports=0
Application startup complete.
```

The canonical runtime contained no `QUEUED` or `PROCESSING` Phase 11 searches at this startup, so `scheduled_searches=0` was correct. Terminal searches, including the Step 1 reproduction run, were not reprocessed.

The application then shut down cleanly.

## Additional verification

```text
python -m compileall -q app
PASS

python -m py_compile tests\test_phase11_restart_recovery.py
PASS

git diff --check
PASS
```

## Decision

**PASS - Step 4 startup reconciliation and restart recovery are complete.**

Phase 11 durable searches now resume after Phase 10 reconciliation through bounded scheduling, without synchronous startup processing, duplicate coordinator loops, duplicate snapshots, or terminal-state reprocessing. Step 5 submission/idempotency/concurrency work has not been started.
