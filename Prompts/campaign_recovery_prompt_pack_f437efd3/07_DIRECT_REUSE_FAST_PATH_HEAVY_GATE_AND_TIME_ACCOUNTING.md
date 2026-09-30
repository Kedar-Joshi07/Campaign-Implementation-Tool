# Prompt 07 — Separate cheap reuse from heavy work and correct queue/processing timing


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

Prevent cheap exact/direct reuse from waiting behind the global heavy-work slot and make runtime timing fields semantically truthful.

## Inspect at minimum

- `app/services/phase11_search_orchestration_service.py`
- `_PHASE10_HEAVY_GATE`
- `_phase10_state`
- coordinator worker limits/queues
- runtime schema
- ETA/projected status
- Results processing-duration rendering

## Heavy-gate redesign

Current conceptual issue to verify:
`with _PHASE10_HEAVY_GATE: _phase10_state(...)`
means even the cheap attested-generation lookup is serialized.

Refactor so:

1. perform bounded cheap current attested direct-reuse lookup outside the heavy gate;
2. if reusable intelligence exists, continue immediately;
3. only if fallback Phase 10 compatibility/build work is required, acquire the heavy-work gate;
4. after acquiring the gate, recheck whether another worker prepared the intelligence while this worker waited;
5. build only if still needed.

This must be race-safe and must not create duplicate heavy work.

## Timing semantics

Separate:
- queued_at / created_at;
- processing_started_at;
- completed_at;
- queue_seconds;
- processing_seconds;
- total_elapsed_seconds if useful.

Do not compute `processing_seconds` from a timestamp written while still QUEUED.

Retry attempts need the same semantics.

Preserve backward compatibility where possible; if an existing public field's meaning was wrong, document the correction and test it.

## Queue observability

Queue position should be calculated consistently and cheaply for queued runs. Processing duration should begin only after the worker actually claims/starts the attempt.

## Tests

- cheap direct reuse completes while an unrelated heavy build holds the heavy gate;
- two workers race: one builds, the waiter rechecks and reuses;
- no duplicate generation/scoring work;
- queue wait of N seconds does not inflate `processing_seconds`;
- total elapsed can include queue time if exposed;
- retry timing resets per attempt while historical attempt timestamps remain immutable.

## Evidence

`docs/evidence/recovery_hardening/07_FAST_PATH_AND_TIMING.md`

Include a sequence diagram.

## Acceptance gate

GO only if verified reuse does not block behind unrelated heavy compute and processing time excludes queue wait.
