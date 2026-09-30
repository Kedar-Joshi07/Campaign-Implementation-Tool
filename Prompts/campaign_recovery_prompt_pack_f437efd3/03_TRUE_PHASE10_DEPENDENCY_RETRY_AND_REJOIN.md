# Prompt 03 — Make Retry restart or rejoin the failing Phase 10 dependency


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

A retryable Phase 11 failure caused by Phase 10 must not simply create a new Phase 11 attempt and immediately rediscover the same terminal Phase 10 orchestration.

## Inspect at minimum

- `app/services/phase11_search_orchestration_service.py`
- `app/services/phase10_api_service.py`
- `app/services/phase10_orchestration_service.py`
- `app/repositories/phase10_intelligence_repository.py`
- `app/jobs/phase11_search_coordinator.py`
- structured failure code mapping
- retry API/service
- Phase 10 restart reconciliation tests
- Phase 11 retry tests

## Required behavior

Build a failure-ownership map. At minimum distinguish:

- Phase 11-local transient failure;
- Phase 10 transient FAILED;
- Phase 10 BLOCKED due to business/data insufficiency;
- calibration not ready;
- stale/unresponsive worker;
- permanent validation failure.

For retryable Phase 10 transient failures:

1. Phase 11 retry creates a new immutable/fenced attempt.
2. It inspects the exact Phase 10 orchestration/targeting context.
3. If an appropriate Phase 10 orchestration is already QUEUED/RUNNING, **rejoin it**. Do not create a duplicate.
4. If the exact previous Phase 10 orchestration is FAILED and the failure is retryable, invoke the existing governed Phase 10 retry path or create a new exact orchestration according to Phase 10 contracts.
5. Persist the dependency lineage for observability.
6. Keep Phase 11 PROCESSING/WAITING until Phase 10 becomes READY/BLOCKED/FAILED.
7. Continue to result materialization when READY.
8. If BLOCKED for a non-transient business reason, do not auto-retry endlessly.

Do not make Phase 11 call internal worker functions that bypass Phase 10's repository/API state machine.

## Idempotency/concurrency

Two Phase 11 searches sharing the same modeling context must not create two identical heavy Phase 10 builds merely because they retry simultaneously.

Use durable Phase 10 uniqueness/reuse contracts, not a process-local assumption.

## Failure messages

Surface:
- what dependency failed in business-safe language;
- whether retry is eligible;
- whether the retry is waiting on an already-running dependency;
- a technical reference ID safe for support.

Do not expose raw exceptions.

## Mandatory tests

Include:
- exact reproduction of the previously observed "Retry -> immediate same Phase10 FAILED" bug;
- retry creates/rejoins Phase 10 and later completes when the dependency succeeds;
- concurrent retries share one Phase 10 orchestration;
- Phase 10 BLOCKED remains blocked and does not loop;
- permanent Phase 10 validation failure is not marked retryable;
- restart during Phase 10 retry resumes safely;
- stale worker from prior Phase 11 attempt cannot mutate the retry attempt (uses Prompt 02 fencing).

## Evidence

`docs/evidence/recovery_hardening/03_PHASE10_RETRY_REJOIN.md`

Document the dependency-owned retry state machine.

## Acceptance gate

GO only when a controlled transient Phase 10 failure can be retried from the Phase 11 UI/API and reach completion without manually resetting database state.
