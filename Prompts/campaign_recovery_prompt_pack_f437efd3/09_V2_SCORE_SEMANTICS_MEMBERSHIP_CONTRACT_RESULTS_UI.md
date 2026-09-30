# Prompt 09 — Correct v2 calibrated-probability semantics end to end


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

Stop conflating legacy raw model scores with calibrated purchase probabilities.

## Inspect at minimum

- `app/services/phase11_result_snapshot_service.py`
- result membership constants/contracts
- `app/services/phase11_search_orchestration_service.py`
- calibrated member iterator
- `app/services/phase11_results_service.py`
- response schemas
- export templates/profile fields
- frontend Results/Detail rendering
- tests/evidence for v1 snapshots

## Required contract decision

Preserve v1 immutable semantics:
`propensity_score` = legacy/raw score.

For selection contract v2, introduce an explicit versioned membership/result contract rather than storing calibrated probability under a v1 raw-score semantic name.

Preferred v2 analytical membership fields:
- person_id;
- calibrated_purchase_probability;
- probability_bucket;
- percentile/rank fields as actually defined;
- optional raw_propensity_score only if justified and clearly named.

Do not mutate old v1 snapshot files.

Result cache keys and manifests must include the membership/selection contract version.

## Result detail

For v2:
- display "Purchase Propensity" / calibrated probability bucket;
- do not display legacy "Match Strength" as the primary selection description;
- show calibrated probability summary sourced from the promoted calibration/scores;
- if raw score is shown, label it separately.

For v1:
- preserve current legacy labels and raw-score semantics.

## Export

Decide whether downstream export needs calibrated probability. If exposed, use an explicit field name. Do not silently rename existing frozen export columns.

## Migration/backward compatibility

No rewrite of historical snapshots.
Readers must understand both membership versions.

## Tests

- v1 snapshot remains readable and unchanged;
- v2 snapshot uses explicit calibrated field;
- cache cannot confuse v1/v2;
- Results card distinguishes 0.50 and 0.60 buckets even if both historically map to BROAD;
- score summary for v2 reflects calibrated probability, not raw scoring_run min/max/mean;
- old downloads remain byte/schema compatible where frozen.

## Evidence

`docs/evidence/recovery_hardening/09_V2_SCORE_SEMANTICS.md`

## Acceptance gate

NO-GO if a single field named `propensity_score` still means raw score in v1 and calibrated probability in v2 without a versioned schema boundary.
