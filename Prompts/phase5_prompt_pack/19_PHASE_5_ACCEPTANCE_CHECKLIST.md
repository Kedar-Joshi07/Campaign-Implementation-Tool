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
- [x] coherent adult source regenerated (no post-hoc age mutation path).
- [x] completed demographics provenance captured (import_id + source_checksum).

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
- canonical demographics import: `import_id=5`, checksum `7d57a02add836f448ed2d937e60bb6c0d38402c3c82e6f219b54e904e0e0c2db`.
- canonical scoring identifiers: `job_id=18`, `scoring_run_id=7`, `model_run_id=6`.
- exact reconciliation: demographics snapshot 5,000,000; scored 5,000,000; score rows 5,000,000; duplicates 0; invalid FK 0.
- score summary: min `0.006140909845521252`, mean `0.044244679521142034`, max `0.9943604573869449`.
- runtime + throughput: `1572.4510145999993s`, `3179.749291758956 rows/s`.
- chunk/memory: `chunk_size=25000`, `chunk_count=200`, `largest_chunk_rows=25000`, `largest_transformed_matrix_bytes=3396428`.
- deterministic re-score: `verify_scoring_run_sample(scoring_run_id=7, sample_size=256)` -> `verified=true`, `max_abs_diff=0.0`.
- provenance verification: canonical payload present and current demographics source match confirmed.
- residual risks: local SQLite single-user throughput characteristics; no functional blockers for Phase 5 acceptance.
- **Go / Conditional Go / No-Go Phase 6:** Go.
