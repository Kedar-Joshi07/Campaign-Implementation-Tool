# Phase 11 Submission, Idempotency, and Concurrency Safety

## Scope and baseline

- Prompt: `05_STEP_05_SUBMISSION_IDEMPOTENCY_AND_CONCURRENCY_SAFETY.md`
- Baseline: `9009e23b750000d3f3d29e09204281f3d301e640`
- Date: 2026-09-21 (Asia/Calcutta)
- Result: **PASS**

Step 5 preserves two deliberately different semantics:

1. every intentional user submission creates a separate immutable `campaign_search_runs` history row; and
2. one durable `search_run_id` can have at most one active coordinator loop in a process.

The implementation uses bounded per-process coordination plus durable database uniqueness at the shared-work boundaries. It does not add a broad database lock and does not serialize unrelated reads.

## Concurrency strategy

### Submission boundary

`submit_potential_customer_search` always persists a new immutable Campaign Context and search run for each accepted POST. It does not collapse two intentional requests merely because their payloads are identical.

The runtime executor receives the newly committed `search_run_id`; therefore execution identity is the durable ID, not a mutable form payload or request-local object.

### Coordinator active registry

`Phase11SearchCoordinator` owns:

- a fixed two-worker `ThreadPoolExecutor` in production;
- a lock-protected `active_search_ids` set;
- a bounded 100-run tracked-work limit;
- an `_accepting` shutdown gate;
- a bounded durable refill guard; and
- terminal-state checks before reservation.

The ID is reserved under the coordinator lock before executor submission. Startup reconciliation and request submission both call the same `submit` boundary, so a race between them can reserve a run only once. A second submission for an active ID returns `False`; it does not create another future or loop.

The lock protects only short in-memory registry operations. Orchestration, SQLite reads/writes, Phase 10 work, and snapshot streaming occur outside it.

### Durable Phase 10 sharing

Phase 10 retains ownership of heavy-work identity and active orchestration deduplication. Searches sharing the same Modeling Context attach to/reuse the compatible generation and scoring lineage. Phase 11 does not independently submit model training or 5M scoring work.

### Snapshot publication

The result registry has a unique `result_cache_key_sha256`. Production snapshot publication:

1. streams candidate membership into a private pending directory;
2. validates the artifact;
3. enters a bounded SQLite `BEGIN IMMEDIATE` publication transaction;
4. rechecks the exact cache key inside that transaction;
5. reuses a valid concurrently published snapshot when present; and
6. otherwise atomically publishes and registers exactly one snapshot.

This narrow transaction protects publication identity without locking ordinary search/status/history reads.

## Added race tests

New module:

```text
tests/test_phase11_submission_concurrency.py
```

### Startup resume racing request submission

Two threads are released through the same barrier:

- one calls the request-side `coordinator.submit`;
- one calls startup `resume_durable_searches`.

Exactly one returns a successful schedule count. While the worker is deliberately held active, additional submit and resume calls both report no new scheduling. The runner call list contains the search ID exactly once.

### Simultaneous identical intentional searches

Two separate history rows with identical exact targeting identity are submitted to both production coordinator workers. Their membership producers meet at a barrier so both attempt production snapshot materialization concurrently.

Verified outcome:

- the two `search_run_id` values remain distinct;
- each coordinator loop runs exactly once;
- both searches complete;
- both reference the same generation;
- both reference the same snapshot;
- the database contains one snapshot row for the cache key; and
- historical-analysis, model, scoring, and propensity-score counts remain unchanged.

A third later intentional identical submission creates another history row and completes through explicit `EXACT_RESULT_REUSE`, still with one snapshot row.

### Different searches sharing one Modeling Context

Ohio and Texas targeting criteria are submitted concurrently under the same Modeling Context.

Verified outcome:

- the runs and result-cache identities remain distinct;
- two appropriate membership snapshots are created;
- both searches share the same generation and scoring run;
- each runner executes once; and
- historical-analysis, model, scoring, and propensity-score counts remain unchanged.

## Browser behavior

The existing business form provides a request-local `submitting` guard before any asynchronous POST begins. During acknowledgment:

- the submit button is disabled;
- top-level fieldsets and multiselect controls are disabled;
- a second click or programmatic submit event is ignored; and
- navigation does not cancel the persisted request.

The browser tests verify:

- retrying failed option loading performs GET-only recovery and creates no work;
- rapid click plus a programmatic second submit produces one POST and one run;
- the form remains locked until acknowledgment finishes; and
- a later corrected/intentional submit creates a second context and run.

If acknowledgment fails, the UI explicitly tells the user to check Results before intentionally trying again. A later retry is treated as a new intentional submission rather than silently mutating or deduplicating the first durable row.

## Status polling

Status polling uses read-only GET projections and never invokes the executor. The real-app integration test repeatedly polls both submitted searches through:

```text
GET /api/potential-customer-search/runs/{search_run_id}/status
```

The searches still produce one coordinator execution per run, one shared exact snapshot, and unchanged heavy-work counts. Polling frequency therefore has no execution side effect.

## Test results

New focused race module:

```text
python -m pytest tests\test_phase11_submission_concurrency.py -q
3 passed in 19.40s
```

Real system-browser double-click/retry/intentional-submit cases, using the repository virtual environment and configured system browser:

```text
.venv\Scripts\python.exe -m pytest \
  tests\test_phase11_business_search_form.py::test_failed_options_can_retry_without_creating_work \
  tests\test_phase11_business_search_form.py::test_navigation_during_acknowledgement_and_duplicate_submit_lock \
  tests\test_phase11_business_search_form.py::test_corrected_custom_errors_and_intentional_new_submission -q

3 passed in 42.36s
```

Consolidated backend coordinator, restart, submission, and reuse regression:

```text
python -m pytest \
  tests\test_phase11_submission_concurrency.py \
  tests\test_phase11_runtime_coordinator.py \
  tests\test_phase11_restart_recovery.py \
  tests\test_phase11_api_backward_compatibility.py::test_repeated_intentional_identical_posts_are_distinct_but_synchronous \
  tests\test_phase11_smart_reuse_engine.py::test_identical_request_reuses_snapshot_but_creates_second_history_and_profile_does_not_rescore \
  tests\test_phase11_smart_reuse_engine.py::test_changed_demographic_filters_reuse_intelligence_without_training_or_scoring -q

27 passed in 54.51s
```

Repeated-polling real-app API integration:

```text
python -m pytest tests\test_phase11_real_app_api.py::test_real_app_api_reuse_failure_results_export_and_shutdown -q
1 passed in 60.81s
```

The final non-overlapping Step 5 matrices comprise **31 passing tests**: 27 backend/reuse tests, 3 browser tests, and 1 real-app polling test.

## Environment note

The default shell Python does not include Playwright. The repository `.venv` does. Its first browser launch was blocked by the filesystem/process sandbox with Windows access denied; rerunning the same command with approved browser subprocess access produced the passing result above. No application assertion failed in the blocked attempts.

## Repository impact and sequencing

- Added `tests/test_phase11_submission_concurrency.py`.
- Added this evidence document.
- No additional production change was required because the bounded active registry and snapshot publication transaction were already present from the runtime composition/materialization work.
- Step 8 was not started.

## Decision

**PASS - Step 5 submission idempotency and concurrency safety are complete.**

Intentional submissions remain distinct, while a single durable run cannot execute twice concurrently. Compatible searches share Phase 10 lineage, identical result identities share one immutable snapshot, unrelated reads remain unblocked, and browser/status retries do not create accidental heavy work.
