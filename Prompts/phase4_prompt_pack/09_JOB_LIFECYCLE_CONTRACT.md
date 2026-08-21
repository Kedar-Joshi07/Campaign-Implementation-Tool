# Phase 4 Job Lifecycle Contract

## Type
Phase 4 supports exactly `MODEL_TRAINING`.

## Statuses
```text
QUEUED
RUNNING
COMPLETED
FAILED
```
No cancellation in Phase 4.

## State machine
```text
submit → QUEUED → RUNNING → COMPLETED
              \         \→ FAILED
               \→ FAILED
```
Terminal states never transition again.

## Progress
- QUEUED = 0
- RUNNING = 1–99
- COMPLETED = 100
- FAILED = latest progress <=99
- monotonic only

## Stages
```text
QUEUED
STARTING
RECONSTRUCTING_COHORT
SPLITTING_DATA
PREPROCESSING
TRAINING_PRIMARY
TRAINING_CHALLENGER
TRAINING_DIAGNOSTIC
EVALUATING
PERSISTING_ARTIFACT
VERIFYING_ARTIFACT
COMPLETED
FAILED
```

## request_json
Only analysis_run_id, model_name, random_seed, validation_fraction, run_elkan_challenger.

## result_json
Keep bounded. Include model_run_id, selected candidate, selection policy, flags, artifact hash. Do not duplicate giant metrics payload already owned by model_runs.

## error_message
Internal bounded diagnostic only. API converts to safe text.

## One-active rule
At most one MODEL_TRAINING job may be QUEUED/RUNNING.

## Restart
Stale QUEUED/RUNNING → FAILED at startup because local executor jobs are not restart-durable.

## Relationship to model_runs
`jobs` owns orchestration. `model_runs` owns modeling. Keep separate. Completed job points to model_run_id; failed job may point to a FAILED model_run_id when one was created.
