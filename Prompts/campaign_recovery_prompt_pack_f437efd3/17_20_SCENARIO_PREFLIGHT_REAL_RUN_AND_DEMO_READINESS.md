# Prompt 17 — Revalidate all 20 scenarios and run only genuinely qualified searches


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

Produce truthful demo readiness after runtime/model/selection-contract fixes.

## Inputs

Use the repository's canonical 20-scenario pack unchanged.

Do not alter:
- age;
- income;
- states;
- education;
- employment;
- family;
- resident-type filters;
- scenario IDs/names;
- 10,000 exact-customer qualification rule.

Use the approved selection contract resulting from Prompt 13/14.

## Step A — exact preflight

For each scenario record:
- scenario ID/name;
- normalized criteria hash;
- catalog version;
- generation ID;
- scoring run ID;
- calibration artifact ID if applicable;
- selection contract version;
- demographic count;
- selection/bucket population;
- exact intersection;
- demo_ready;
- safe currentness state.

Qualification requires:
- current/verified lineage;
- exact count >= 10,000;
- no widened filters.

## Step B — controlled real runs

Submit only qualifying scenarios.

For each real run capture:
- run ID;
- attempt;
- creation acknowledgement time;
- queue time;
- processing time;
- result source;
- progress stage sequence;
- ETA behavior if available;
- exact selected count;
- snapshot ID/checksum;
- preflight count vs materialized count;
- reuse/build explanation.

Any mismatch between exact preflight and actual ALL_MATCHING result is a blocker.

## Step C — TOP_N demonstration

Only after showing the full exact qualifying count, optionally rerun the same scenario under approved `TOP_N=250` semantics to demonstrate activation capacity. Keep this a separate run/contract.

## Step D — demo order

Recommend a live demo order only from scenarios that actually qualified. Do not preserve an old preferred order if some are not qualified.

## Evidence

`docs/evidence/recovery_hardening/17_20_SCENARIO_READINESS.json`
`docs/evidence/recovery_hardening/17_20_SCENARIO_READINESS.md`

## Acceptance gate

GO for demo only if at least the desired set of scenarios qualify and their actual materialized counts match exact preflight.
