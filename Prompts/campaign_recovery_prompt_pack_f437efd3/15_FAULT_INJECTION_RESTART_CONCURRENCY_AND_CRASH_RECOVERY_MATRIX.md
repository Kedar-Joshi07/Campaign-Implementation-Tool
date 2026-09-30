# Prompt 15 — Fault injection and crash/restart certification


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

Prove the recovered runtime survives the failures that originally caused stuck 3%, stale retries, duplicate work, and unsafe terminal transitions.

## Build a deterministic fault matrix

Inject failures at least at:

1. after search row creation but before scheduling;
2. after attempt lease claim;
3. during direct-reuse validation;
4. while waiting for heavy slot;
5. during Phase 10 analysis/model/scoring/rank stages;
6. after Phase 10 becomes READY but before Phase 11 observes it;
7. during cache lookup;
8. during member selection;
9. during snapshot file write;
10. after file fsync but before DB publication;
11. after snapshot registration but before completion;
12. during export;
13. during feedback ingestion;
14. during recalibration publication;
15. process restart while attempts are QUEUED/PROCESSING;
16. stale worker resumes after retry creates a new attempt.

## Required guarantees

- no orphan active run without recoverable durable state;
- no two active attempts for one run;
- no stale worker writes;
- no duplicate immutable snapshot for one exact cache identity except safely reconciled race;
- no partial published file treated as current;
- no retry loop;
- no loss of idempotency;
- restart reconciliation is bounded;
- safe business error messages;
- logs contain technical context without PII/secrets.

## Tests

Prefer deterministic synchronization barriers/events over sleeps.

Run concurrency tests repeatedly enough to expose races.

Include SQLite lock/contention behavior appropriate for the POC.

## Evidence

`docs/evidence/recovery_hardening/15_FAULT_MATRIX.md`

Include a matrix:
fault point -> durable state -> startup/retry action -> expected terminal state -> test.

## Acceptance gate

NO-GO if any injected crash can cause an old attempt to mutate a newer attempt or produce an unowned permanent PROCESSING state.
