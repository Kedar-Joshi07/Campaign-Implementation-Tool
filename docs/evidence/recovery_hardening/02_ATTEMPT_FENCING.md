# Prompt 02 — Durable Attempt Execution Fencing

## Starting point

- Starting SHA: `f437efd3be9e6d4945b0ee12bff91ccce2697088`.
- The working tree contained the completed, uncommitted Prompt 01 changes, its evidence, the Prompt 00 evidence, and the untracked recovery prompt pack. They were preserved and identified as prior-pack work.
- No commit or push was performed.

## Defect reproduced

Worker mutation methods accepted only `search_run_id`. In particular, progress and lineage code read `current_attempt_number` during the write transaction. After retry changed the visible run from Attempt N to Attempt N+1, a stale Attempt N worker could therefore update the shared runtime and record an event against N+1. A stale worker could also fail or complete the visible run after reacquiring a superficially valid run state.

## Root cause

`campaign_search_attempts` preserved immutable attempt history, but it was observational rather than an execution fence. The coordinator did not hand an immutable attempt identity to the worker, and mutable repository APIs did not require or predicate writes on that identity.

## Durable design

Schema version 22 adds these columns to `campaign_search_attempts`:

- `execution_lease_token`: opaque 256-bit lowercase hexadecimal token;
- `lease_owner`: bounded internal coordinator/worker owner label;
- `lease_claimed_at`: first durable claim time;
- `lease_heartbeat_at`: latest successful owner activity.

It also creates a partial unique index over non-null lease tokens. Existing v17–v21 upgrade paths create or retain attempts through their historical migrations, then v22 backfills exactly one valid token per attempt. The v22 migration temporarily removes the terminal-attempt update trigger only inside its transaction, performs the backfill and validation, and restores the trigger before commit. Re-running the migration function is idempotent.

New runs receive a token from SQLite's `randomblob(32)` in the v22 attempt-creation trigger. Retries receive a new token from `secrets.token_hex(32)`. Restart reconciliation reclaims the already durable token for the same attempt instead of creating another attempt or lease.

The token is internal-only: it is excluded from API schemas, response projections, OpenAPI, exception messages, and logging arguments. `AttemptExecutionFence.__repr__` also redacts it.

## Exact SQL-level fencing invariant

Every worker-owned mutable operation requires both `attempt_number` and `execution_lease_token`. Within a `BEGIN IMMEDIATE` transaction, visible-run and runtime writes include the equivalent of:

```sql
WHERE search_run_id = :search_run_id
  AND current_attempt_number = :attempt_number
  AND status IN (:allowed_active_statuses)
  AND EXISTS (
      SELECT 1
      FROM campaign_search_attempts a
      WHERE a.search_run_id = campaign_search_runs.search_run_id
        AND a.attempt_number = :attempt_number
        AND a.execution_lease_token = :execution_lease_token
        AND a.status IN (:allowed_active_statuses)
  )
```

The attempt-row write independently repeats the primary-key, token, and status predicates. Every guarded cursor must affect exactly one row or the transaction raises `Phase11RegistryStateError` and rolls back. Progress events use the caller's immutable `attempt_number`; they never re-read and adopt the currently visible attempt number.

The retry transaction applies the same exact fence to stale-attempt terminalization, verifies the visible run, runtime, and old attempt each changed exactly once, inserts N+1 with a new token, then makes N+1 visible.

## State-transition diagram

```text
Run.current_attempt = N
Attempt N: QUEUED + token(N)
        |
        | mark_processing(N, token(N))
        v
Attempt N: PROCESSING + token(N) -- heartbeat/progress --> PROCESSING
        |
        | stale retry transaction
        v
Attempt N: FAILED (immutable)
        |
        +--> create Attempt N+1: QUEUED + token(N+1)
             set Run.current_attempt = N+1
             reset visible runtime to QUEUED

Late worker N write(N, token(N))
        |
        +--> current_attempt=N+1 / token mismatch --> zero rows --> rollback

Worker N+1 write(N+1, token(N+1))
        |
        +--> exact fence matches --> permitted transition
```

## Files changed for Prompt 02

- `app/database/schema.py`
- `app/repositories/campaign_result_registry_repository.py`
- `app/jobs/phase11_search_coordinator.py`
- `app/services/phase11_search_orchestration_service.py`
- `app/services/potential_customer_search_submission_service.py`
- `tests/test_phase11_attempt_execution_fencing.py`
- Existing Phase 11 registry, lifecycle, coordinator, restart, submission, result, reuse, materialization, performance, dashboard, feedback-lineage, and API tests were updated to provide explicit fences.
- Schema-version assertions were advanced from 21 to 22.

## Contract changes

- `mark_processing`, `update_search_progress`, `bind_current_attempt_lineage`, `complete_search_run`, and `fail_search_run` now require keyword-only `attempt_number` and `execution_lease_token` parameters with no defaults.
- `claim_search_attempt` returns an internal `AttemptExecutionFence` for the current active attempt.
- The coordinator claims once before executor submission and passes the same immutable fence through every bounded orchestration pass.
- Safe-failure handling uses the worker's original fence and ignores a fence-rejection after a retry, leaving the newer attempt untouched.
- No business API path or schema changed in this prompt.

## Mandatory adversarial verification

The tests prove:

1. stale Attempt 1 progress is rejected and records no Attempt 2 event;
2. stale Attempt 1 failure is rejected;
3. stale Attempt 1 completion is rejected;
4. stale Attempt 1 lineage binding is rejected;
5. Attempt 2 remains QUEUED and then processes normally after all stale writes fail;
6. eight retries with the same idempotency key create exactly one Attempt 2;
7. eight retries with different keys create one active Attempt 2 and reject the other seven;
8. restart recovery reuses one token and does not create a duplicate attempt/lease;
9. terminal Attempt 1 fields and token remain immutable after retry;
10. the token is absent from public API JSON, OpenAPI, and safe fence representation.

Migration tests cover starting schema versions 17, 18, 19, 20, and 21, a preserved terminal run/attempt, transactional token backfill, index creation, schema version 22, repeat initialization, and repeat direct migration application.

## Commands and results

- Initial lifecycle/registry/coordinator/restart regression: **75 passed** in 264.92 seconds.
- New attempt-fencing test module after final migration changes: **15 passed** in 27.88 seconds.
- Focused mandatory concurrency/stale-worker selector: **6 passed** in 17.59 seconds.
- Affected Phase 11 non-browser regression set: **136 passed, 27 deselected** in 349.01 seconds.
- Phase 9/10 schema-version regression: **11 passed** in 11.96 seconds.
- Changed production-file Ruff checks: **passed**.
- Python compilation and `git diff --check`: **passed**.

## Known remaining risks

- The runtime is deliberately a bounded single-application coordinator over SQLite. The durable token survives process restart, while in-process tracking prevents duplicate scheduling. This prompt does not introduce a distributed multi-host lease-election protocol.
- Full repository-wide CI and remote exact-SHA certification are reserved for Prompt 19; they are not claimed here.
- Prompt 01 changes remain uncommitted in the same working tree and are intentionally preserved.

## Gate

**GO.** No production worker mutation in scope can act using only `search_run_id`; the current immutable attempt number and matching opaque token are mandatory and SQL-guarded.

**Recommended next prompt:** `03_TRUE_PHASE10_DEPENDENCY_RETRY_AND_REJOIN.md`.
