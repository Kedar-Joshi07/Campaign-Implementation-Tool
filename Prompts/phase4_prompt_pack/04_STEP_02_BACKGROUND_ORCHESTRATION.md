# Step 2 — Bounded Background Model-Training Orchestration

## Objective
Execute the existing Phase 3 model-training service outside the HTTP request path and persist job progress.

## Recommended modules
```text
app/jobs/executor.py
app/jobs/model_training_worker.py
app/services/model_job_service.py
```

## Responsibilities
### model_job_service
- validate completed analysis;
- enforce one-active-job rule;
- canonicalize request;
- create QUEUED job;
- submit worker;
- return job immediately.

### worker
- mark RUNNING;
- call existing `train_and_persist_model`;
- persist progress;
- attach model_run_id when known;
- COMPLETED or FAILED.

### executor
- lazy bounded executor;
- max_workers=1;
- clean shutdown;
- no ML logic.

## Backward-compatible Phase 3 progress hook
Extend `train_and_persist_model(..., progress_callback=None)` only if necessary.
Suggested callback:
```python
progress_callback(stage, progress_percent, message, model_run_id=None)
```
CLI must behave identically when callback omitted.

## Suggested progress mapping
```text
QUEUED 0
STARTING 5
RECONSTRUCTING_COHORT 15
SPLITTING_DATA 25
PREPROCESSING 35
TRAINING_PRIMARY 50
TRAINING_CHALLENGER 62
TRAINING_DIAGNOSTIC 70
EVALUATING 80
PERSISTING_ARTIFACT 90
VERIFYING_ARTIFACT 95
COMPLETED 100
```
Centralize mapping and keep it monotonic.

## One-active-job race protection
Do not rely on a naive SELECT-then-INSERT race. Use a transaction/application lock plus DB recheck suitable for the single-process POC.

## Failure handling
- executor submit failure: QUEUED→FAILED;
- Phase 3 failure: job→FAILED, attach failed model_run_id when available;
- unexpected worker exception: job→FAILED with bounded internal diagnostic;
- never fall back to naive or create fake completion.

## Startup reconciliation
At application startup, stale QUEUED/RUNNING jobs become FAILED with a safe interruption message. Do not resume them.

## Tests
Prove immediate submission with a controllable fixture, one-active rule, success/failure transitions, monotonic progress, primary failure, challenger skip, startup stale reconciliation, executor bound, and no FastAPI BackgroundTasks for training.

## Exit
A training job can execute asynchronously through persisted state, without HTTP/UI yet.
