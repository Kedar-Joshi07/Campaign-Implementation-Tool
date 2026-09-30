# Prompt 14B — Conditional path: implement an explicitly approved versioned selection contract v3


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


## Run only if

The operator/business has explicitly approved one of the alternatives documented in Prompt 13.

Record the approval/selected semantics in:
`docs/evidence/recovery_hardening/13_SELECTION_POLICY_DECISION.md`

Do not run this prompt without that decision.

## Objective

Implement the approved new targeting semantics as a **new versioned contract** while preserving v1 and v2 behavior and historical artifacts.

## Required architecture

Add:
- selection contract version 3;
- explicit schema/API fields whose names match the approved semantics;
- deterministic bucket/range/percentile definitions;
- exact preflight implementation;
- materialization implementation using the same shared predicate/selection layer;
- result cache identity updates;
- snapshot/membership contract update if field semantics change;
- Results/Detail labels;
- API/OpenAPI docs;
- scenario preflight support.

## Compatibility

- v1 raw-score searches unchanged;
- v2 absolute calibrated-probability searches unchanged;
- v3 explicit new semantics only for new requests;
- no automatic migration of historical runs.

## Tests

Boundary tests, preflight/materialization parity, history reopening, result-cache separation, UI labels, export compatibility, and exact scenario qualification.

## Evidence

`docs/evidence/recovery_hardening/14B_SELECTION_V3.md`

## Acceptance gate

GO only if a business user cannot confuse v3 semantics with absolute purchase probability and all historical versions remain interpretable.
