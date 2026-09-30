# Prompt 16 — Canonical 5M performance and non-mutating certification


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

Certify performance on the canonical 5M database after correctness fixes, without contaminating business evidence.

## Measure separately

### Warm read paths
- targeting options;
- Results history 20;
- status/detail;
- exact preflight cached;
- exact result reuse lookup;
- snapshot validation.

### Write/compute paths
Where business qualification permits:
- search creation acknowledgement;
- coordinator scheduling latency;
- exact-result reuse completion;
- new materialization for a qualifying controlled scenario;
- feedback ingestion;
- calibration/preflight refresh.

If a path cannot be ethically executed because no scenario qualifies, state **NOT EXECUTED**. Do not substitute a different metric and call it certified.

## Budgets

Use existing repository budgets where already frozen. If no budget exists, record measurement without inventing a pass threshold.

## Query plans

Capture `EXPLAIN QUERY PLAN` for:
- calibrated bucket count;
- preflight intersection filters;
- queue positions;
- history;
- normalized product lookup;
- current catalog version;
- snapshot/cache lookup.

Check for N+1 regressions.

## Resource behavior

Record:
- elapsed time;
- peak memory if practical;
- DB size changes;
- lock errors/timeouts;
- number of queries for history/options where tests instrument them.

## Evidence

Update/create:
`docs/evidence/recovery_hardening/16_CANONICAL_PERFORMANCE.json`
`docs/evidence/recovery_hardening/16_CANONICAL_PERFORMANCE.md`

Do not overwrite older historical evidence without preserving its baseline.

## Acceptance gate

GO only for operations actually executed and within frozen budgets. Keep unexecuted operations explicitly uncertified.
