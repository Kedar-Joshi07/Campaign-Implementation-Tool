# Prompt 06 — Make exact preflight a trustworthy qualification gate


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

Guarantee that preflight and actual v2 result materialization use the same selection contract, current lineage, filters, bucket boundaries, deduplication, and selection semantics.

## Inspect at minimum

- `app/services/potential_customer_preflight_service.py`
- `app/services/phase11_search_orchestration_service.py`
- normalized criteria/filter-branch builders
- propensity bucket definitions
- calibrated score schema/indexes
- TOP_N/ALL_MATCHING behavior
- `scripts/validation/preflight_demo_readiness_scenarios.py`
- scenario pack JSON

## Required properties

### Same lineage
Preflight must bind:
- generation ID;
- scoring run ID;
- calibration artifact ID;
- catalog version/current source identity.

### Same filters
Preflight and actual search must use the same normalized branch representation. Avoid maintaining two subtly different filter implementations.

Prefer extracting a shared predicate/selection contract layer used by:
- exact preflight count;
- calibrated member iterator.

### Same bucket semantics
Prove inclusive/exclusive boundaries exactly:
- 0.90: [0.90, 1.00] according to contract;
- other buckets: [lower, upper) unless the frozen contract says otherwise.

Do not count all >= lower if the actual search selects only one discrete bucket.

### Same OR/dedup semantics
Overlapping branches must count each person once exactly as materialization emits them.

### Selection mode
- `ALL_MATCHING`: preflight intersection count equals eventual resolved count.
- `TOP_N`: report both qualifying population and eventual selected `min(qualifying, N)` clearly.

### Cache identity
Cache key must include every semantic/currentness component needed so a cache entry cannot survive:
- source change;
- generation change;
- calibration change;
- criteria change;
- bucket change;
- contract version change.

## Mandatory parity tests

For controlled fixtures and at least one larger fixture:
- preflight count == materialized snapshot row count;
- overlapping OR branches;
- empty bucket;
- exact lower/upper boundary values;
- ALL_MATCHING;
- TOP_N smaller than qualifying population;
- TOP_N larger than qualifying population;
- source/calibration change invalidates cache.

## Evidence

`docs/evidence/recovery_hardening/06_PREFLIGHT_PARITY.md`

## Acceptance gate

Do not use preflight as the 10,000-customer qualification gate until parity tests prove the count and actual search agree.
