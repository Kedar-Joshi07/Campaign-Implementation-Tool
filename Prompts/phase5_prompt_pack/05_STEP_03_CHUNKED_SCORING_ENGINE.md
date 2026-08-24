# Step 3 — Chunked Scoring Engine and Persistence

## Objective

Implement direct domain scoring service; no ProcessPool/API/UI yet.

Recommended `prospect_scoring_service.py` accepting DB, model_run_id, job_id and optional progress callback.

## Flow

1. validate scoreability;
2. load verified artifact;
3. capture demographic snapshot;
4. create RUNNING scoring_run;
5. iterate keyset chunks;
6. exact raw feature frame;
7. validate/normalize;
8. `artifact["preprocessor"].transform(...)`;
9. `positive_class_scores(..., require_unit_interval=True)`;
10. validate length/finite/[0,1];
11. insert current chunk with `executemany` in one bounded transaction;
12. update counters/last_person_id/progress;
13. discard chunk objects;
14. reconcile and complete.

Never call fit/fit_transform or create new imputer/encoder/scaler/model.

Recommended scoring progress range: model validation 5, prepare run 10, dynamic scoring 10–90, finalize 94, verify 98, complete 100. Emit only chunk/percentage changes.

## Completion

Recheck demographic count/min/max; score count and distinct person count equal snapshot; last_person_id equals snapshot max. Aggregate COUNT/MIN/MAX/AVG. Require finite `0<=min<=mean<=max<=1`.

`score_summary_json` contains count, min/max/mean, total_seconds, rows_per_second, chunk_size, feature/artifact/model provenance, and age-semantics note. No per-person values.

## Failure

Mark scoring_run FAILED. Partial rows may remain isolated under FAILED status; never usable. Avoid massive cleanup on failure/startup.

## Direct verification helper

Use a deterministic bounded sample (not `ORDER BY RANDOM()` on 5M), refetch 11 features, re-score with verified artifact, compare persisted scores strictly.

## Tests

Zero/one/multiple/final partial chunks; keyset continuity; score count/range; transform/estimator/write failures; snapshot drift; completed reconciliation; failed isolation; determinism; no refit; bounded objects; finite JSON.

STOP after Step 3.
