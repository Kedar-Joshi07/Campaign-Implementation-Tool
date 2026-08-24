# Phase 5 Acceptance Checklist

Any failed **Critical** item = **No-Go for Phase 6**.

## Baseline
- [x] **Critical** exact Phase 4 baseline verified.
- [x] pre-change full tests/pip/compile/data recorded.
- [x] real v2 Bagging artifact and feature contract verified.

## Schema v5
- [x] **Critical** v4->v5 preserves all old rows/jobs.
- [x] jobs supports both types with correct stages.
- [x] scoring_runs/propensity_scores constraints/FKs correct.
- [x] [0,1] DB score constraint.
- [x] ranking index.
- [x] one COMPLETED score set per model.
- [x] rollback/idempotence.

## Scoreability
- [x] **Critical** only completed v2 PRIMARY Bagging.
- [x] verified artifact/candidate agreement.
- [x] exact feature version/SHA.
- [x] legacy/bad artifacts rejected before scan.

## Prospect boundary
- [x] **Critical** no customer_id.
- [x] exact 11 features + person_id only.
- [x] no PII/ethnicity/religion scoring reads.
- [x] frozen contract enforced; age assumption documented.

## Chunking/inference
- [x] **Critical** no whole-5M load.
- [x] keyset/no OFFSET scoring loop.
- [x] deterministic coverage and bounded chunk.
- [x] persisted preprocessor/estimator only; no refit.
- [x] finite [0,1] scores; no pre-persist rounding.

## Persistence
- [x] per-chunk executemany transaction.
- [x] failed partial run ineligible.
- [x] completed count exactly snapshot.
- [x] finite summary JSON.

## Jobs
- [x] **Critical** one active heavy job globally.
- [x] training/scoring mutual exclusion.
- [x] same bounded ProcessPool reused.
- [x] no synchronous HTTP scoring.
- [x] stale job/run failure handling.

## APIs
- [x] POST score 202.
- [x] scoring status/list/detail work.
- [x] job detail supports scoring.
- [x] training APIs unchanged.
- [x] active/already-scored/unscoreable conflicts.
- [x] bounded pagination.

## API privacy
- [x] **Critical** no person_id/customer_id/PII/individual scores/raw features/SQL/traceback/absolute path.

## UI
- [x] scoring panel/CTA/progress/aggregate complete.
- [x] active compute cross-disable.
- [x] probability disclaimer.
- [x] **Critical** Audience Explorer disabled.
- [x] no person table/bands/percentiles/campaign/export.

## Full 5M
- [x] **Critical** real job completes.
- [x] snapshot/scored/score rows = 5,000,000.
- [x] duplicate IDs = 0; invalid FK = 0.
- [x] nonfinite/below0/above1 = 0.
- [x] min/mean/max valid.
- [x] runtime/throughput/chunk/memory/DB-growth evidence.
- [x] artifact and feature SHA recorded.

## Direct verification
- [x] deterministic sample re-score within tolerance.

## Regression
- [x] full pytest/pip/compile/diff/data pass.
- [x] Phase 1-4 regressions pass.

## Scope
- [x] individual score API absent.
- [x] Audience Explorer/bands/percentiles/audience/campaign/export/activation/linkage absent.

## Final
- Critical failures: none.
- full scoring job_id: 16.
- scoring_run_id/model_run_id: 5 / 7.
- scored rows/runtime/rows-sec/DB growth: 5,000,000 rows / 2,591.537831999998s / 1,929.3563606367618 rows/s / 3,342,602,240 -> 3,812,544,512 bytes (delta +469,942,272 bytes).
- residual risks: local SQLite single-user throughput characteristics; no new functional blockers for Phase 5 acceptance.
- final SHA: fdae4a7a40c846e4038a8ebe656257eb4164cd5d (working tree contains uncommitted Phase 5 changes).
- **Go / Conditional Go / No-Go Phase 6:** Go.
