# Phase 4 Freeze, Scope, Architecture, and Boundaries

## Baseline
Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Required starting SHA: `04e61caddedcf7963e824e2ccc425ac241d03842`

Before editing:
- verify `git rev-parse HEAD`;
- inspect `git status --short`;
- preserve unrelated changes;
- run full pytest;
- run `python -m pip check`;
- run compileall;
- run `python scripts/validate_data.py --json`;
- verify at least one role-policy-v2 Bagging artifact loads through the existing verified loader.

## Frozen Phase 3 model governance
New policy-v2 runs mean:

```text
PRIMARY
BAGGING_PU + Logistic Regression

CHALLENGER_1
ELKAN_NOTO_LOGISTIC + Logistic Regression

DIAGNOSTIC_CONTROL
NAIVE_PU_LABEL_BASELINE
```

Frozen metadata:
```text
model_role_policy_version = 2
evaluation_contract_version = 2
selection_policy = PRIMARY_ROLE_GOVERNED
```

Frozen feature contract remains version 1 with exactly 11 raw features:
```text
age
gender
state
individual_yearly_income
marital_status
education
employment_status
resident_status
resident_type
family_member_count
type_of_employment
```

Phase 4 must not change those semantics.

## Product goal

```text
Model Training UI
    ↓
Choose COMPLETED historical analysis
    ↓
Submit bounded training configuration
    ↓
Create persistent job
    ↓
Execute existing Phase 3 training service outside request path
    ↓
Poll job progress
    ↓
COMPLETED model_run_id
    ↓
Render governed model result
```

## Technology
Preserve FastAPI, Python, direct sqlite3, HTML/CSS/Vanilla JS, SQLite, local joblib artifacts, scikit-learn, pulearn, pytest.

Do not add Redis, Celery, RabbitMQ, Kafka, Airflow, MLflow server, PostgreSQL, React, Vue, Angular, cloud queues, or distributed services.

## Local execution architecture
Preferred worker:
```text
ProcessPoolExecutor(max_workers=1)
```
created lazily in a dedicated executor module.

Windows rules:
- top-level pickleable worker target;
- no executor creation during FastAPI module import;
- pass only serializable args;
- worker opens its own SQLite connections;
- never pass live DB connections to child process.

If ProcessPoolExecutor is demonstrably unstable in the tested platform, a bounded `ThreadPoolExecutor(max_workers=1)` is permitted only with recorded evidence and reasoning. Do not use FastAPI BackgroundTasks for the model-training pipeline.

## One-active-job rule
For this POC, allow at most one MODEL_TRAINING job in QUEUED/RUNNING state. A second request returns a conflict rather than growing an invisible queue.

## Schema
Expected schema version: 4.
Add only `jobs`; do not alter `model_runs` unless a proven compatibility defect requires it.

Required jobs fields:
```text
job_id
job_type
status
progress_percent
stage
message
analysis_run_id
model_run_id
created_at
started_at
finished_at
request_json
result_json
error_message
```

No `propensity_scores` table.

## Required APIs
```text
POST /api/models/train
GET  /api/jobs/{job_id}
GET  /api/models
GET  /api/models/{model_run_id}
GET  /api/models/training-options
```

Do NOT add `/api/models/{id}/score` in Phase 4.

## Training inputs
Allow only:
```text
analysis_run_id
model_name
random_seed
validation_fraction
run_elkan_challenger
```
Defaults:
```text
random_seed = 42
validation_fraction = 0.20
run_elkan_challenger = true
```

No algorithm dropdown and no Bagging disable option.

## Progress stages
Centralize stage codes. Recommended:
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

## Restart semantics
This is a local executor, not a durable distributed queue. On app startup, stale QUEUED/RUNNING jobs from a previous process become FAILED with a safe interruption message. Do not auto-resume.

## UI
Enable Model Training only. Keep Audience Explorer and Campaigns disabled.

Required UI sections:
- Source Analysis;
- Training Configuration;
- Active Job / Progress;
- Latest Model Result;
- Primary vs Challenger vs Diagnostic comparison;
- Recent Model Runs.

## Explicitly out of scope
- 5M demographic scoring;
- propensity-score table;
- score bands/percentiles;
- Audience Explorer;
- target selection;
- campaign creation;
- export;
- activation;
- auth/RBAC;
- distributed queue;
- automatic retraining;
- challenger auto-promotion.

## Definition of Done
Phase 4 is complete only when:
1. schema v4 works;
2. jobs persist safely;
3. one active training job is enforced;
4. POST training returns without waiting for completion;
5. job progress can be polled;
6. Phase 3 service remains authoritative;
7. successful job points to a verified model_run_id;
8. failure/restart behavior is terminal and safe;
9. model list/detail APIs work;
10. Model Training UI works end to end;
11. all Phase 1–3 regressions pass;
12. no Phase 5 scoring exists.
