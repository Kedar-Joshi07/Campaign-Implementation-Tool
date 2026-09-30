# Prompt 02 — Durable execution lease/fencing for immutable search attempts


# Common execution contract

**Canonical starting SHA:** `f437efd3be9e6d4945b0ee12bff91ccce2697088`

You are working on the repository **Campaign Implementation Tool**. Treat the current codebase, database schema, tests, migrations, and committed evidence as authoritative only after you verify them yourself. Do not assume prior summaries are correct merely because they exist in `docs/evidence`.

Before changing anything:

1. Run `git rev-parse HEAD` and confirm the starting commit is `f437efd3be9e6d4945b0ee12bff91ccce2697088` or a documented descendant created by an earlier prompt in this pack.
2. Run `git status --short`. Do not overwrite unrelated local changes. If prior pack steps created changes, preserve them and identify the exact prior step/commit.
3. Read the files named in this prompt plus adjacent callers, tests, migrations, API schemas, and frontend consumers. Search the whole repository for every symbol you modify.
4. Reproduce the current behavior with focused tests before changing it when practical.
5. Keep changes additive and narrowly scoped. Do not rewrite frozen Phase 1-10 behavior unless a defect proven by this pack requires it.
6. Preserve synthetic-data truthfulness. Do **not** fabricate customers, widen targeting filters, lower approved probability thresholds, duplicate people, change scenario definitions, or invent evidence to make a demo pass.
7. Preserve existing immutable lineage. Never rewrite historical attempts, snapshots, calibration artifacts, feedback batches, or audit events in place.
8. Never persist tracebacks, raw exception text, filesystem paths, secrets, contact PII, or unbounded payloads into business-safe runtime fields.
9. Every mutable worker write must be concurrency-safe and transactionally guarded.
10. Do not mark a requirement complete just because code exists. Prove the behavior through tests and, where requested, canonical/runtime evidence.
11. If a required business-policy decision is not encoded in the repository, stop that policy change and produce a decision document instead of silently choosing.
12. Do not commit or push unless explicitly instructed by the operator. At the end, report changed files, tests run, results, remaining risks, and the next prompt to run.

## Required completion format

End the run with:

- **Starting SHA**
- **Working tree state before**
- **Defects reproduced**
- **Root cause**
- **Files changed**
- **Schema/API/contract changes**
- **Tests added or changed**
- **Commands run**
- **Pass/fail results**
- **Evidence artifacts produced**
- **Known remaining risks**
- **GO / NO-GO for this prompt**
- **Recommended next prompt**


## Objective

Eliminate the most serious concurrency defect: a stale worker from Attempt N must never be able to mutate visible state belonging to Attempt N+1.

## Inspect at minimum

- `app/database/search_recovery_schema.py`
- `app/database/phase11_schema.py`
- `app/database/schema.py`
- `app/repositories/campaign_result_registry_repository.py`
- `app/jobs/phase11_search_coordinator.py`
- `app/services/phase11_search_orchestration_service.py`
- `app/services/potential_customer_search_submission_service.py`
- retry/status API
- tests for lifecycle, retry, restart, concurrency

Search repository-wide for all calls to:
- `mark_processing`
- `update_search_progress`
- `bind_current_attempt_lineage`
- `complete_search_run`
- `fail_search_run`
- `retry_search_run`

## Required design

Introduce a durable **attempt execution fence**. Choose a minimal safe design such as:

- immutable `attempt_number`;
- random/opaque `execution_lease_token` generated when an attempt is scheduled/claimed;
- lease owner / claimed-at / heartbeat-at if needed;
- optional monotonic lease generation.

The exact design can differ, but every worker mutation must require the attempt/fence it was given when execution began.

A worker for Attempt 1 must fail closed if:
- `current_attempt_number` became 2;
- lease token changed;
- attempt is no longer PROCESSING;
- visible run is terminal for another attempt.

## Repository contract changes

Change mutation APIs so callers cannot omit the fence accidentally. Prefer explicit parameters such as:
`attempt_number` and `execution_lease_token`.

Guard SQL with predicates that include the fence, e.g. conceptually:

`WHERE search_run_id=? AND current_attempt_number=? AND ...`

and verify the attempt row matches the token/status.

Do not read `current_attempt_number` at write time and then attribute a stale worker's event to the newly current attempt.

## Retry behavior

When a stale PROCESSING attempt is declared failed:
- terminalize that exact old attempt;
- create the next immutable attempt;
- issue a new lease;
- reset visible runtime for the new attempt;
- do not allow the old worker to complete/fail/update progress afterward.

## Event history

Every progress/failure/completion event must record the worker's actual immutable attempt number, never "whatever is current now."

## Migration

Schema change must be:
- additive;
- idempotent;
- backfilled safely for existing attempts/runs;
- transactionally validated;
- covered by upgrade tests from v17/v18/v19/v20/v21 as applicable.

Do not expose lease tokens through business APIs.

## Mandatory adversarial tests

Create deterministic tests for:

1. Attempt 1 starts; becomes stale; retry creates Attempt 2; Attempt 1 calls `update_search_progress` -> rejected.
2. Same scenario; Attempt 1 calls `fail_search_run` -> rejected.
3. Same scenario; Attempt 1 calls `complete_search_run` -> rejected.
4. Same scenario; Attempt 1 tries lineage binding -> rejected.
5. Attempt 2 remains healthy after all stale Attempt 1 writes fail.
6. eight concurrent retries with same idempotency key -> one next attempt.
7. retries with different idempotency keys cannot create multiple simultaneously active attempts.
8. restart recovery does not mint duplicate leases for one active attempt.
9. terminal attempt history remains immutable.
10. lease token is not present in public API/business-safe logs.

## Evidence

Write:
`docs/evidence/recovery_hardening/02_ATTEMPT_FENCING.md`

Include a state-transition diagram and the exact SQL-level fencing invariant.

## Acceptance gate

NO-GO if any mutation path can still act on a run using only `search_run_id` without proving the caller owns the current attempt.
