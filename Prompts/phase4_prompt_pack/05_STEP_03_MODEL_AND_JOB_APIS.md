# Step 3 — Model Training, Job Status, and Model Run APIs

## Objective
Expose Phase 4 orchestration through FastAPI.

## Endpoints
```text
POST /api/models/train
GET /api/jobs/{job_id}
GET /api/models
GET /api/models/{model_run_id}
GET /api/models/training-options
```

## POST /api/models/train
Request:
```json
{
  "analysis_run_id": 10,
  "model_name": "Holiday Electronics Lookalike",
  "random_seed": 42,
  "validation_fraction": 0.2,
  "run_elkan_challenger": true
}
```

Behavior:
- validate request;
- source analysis must be COMPLETED;
- reject active training conflict;
- create job;
- submit worker;
- return HTTP 202 immediately.

Response includes job_id, type, status, progress, stage, analysis_run_id, created_at.

## GET /api/jobs/{job_id}
Return presentation-safe job state:
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
result
safe error
```
Never expose internal traceback.

## GET /api/models
Bounded pagination: default 20, limit 1–100, offset>=0. Newest first. Optional status filter.
Return model summary only.

## GET /api/models/{model_run_id}
Return safe decoded sections:
```text
identity
cohort
governance
candidate metrics
challenger comparison
quality flags
artifact verification
feature contract identity
runtime
```
No raw training rows, customer IDs, PII, validation-score arrays, raw SQL, or absolute filesystem paths.

## GET /api/models/training-options
Return:
- completed historical analyses;
- defaults;
- frozen model governance;
- current active training job.
No customer list.

## HTTP mapping
```text
200 list/detail/options
202 accepted training
404 unknown resource
409 active training or unusable source state
422 input validation
500 sanitized unexpected failure
```

## Legacy model support
Historical role-policy-v1 runs must remain understandable and immutable. Do not label them as v2 if metadata is absent.

## Tests
OpenAPI, 202, 409, missing/non-completed analysis, polling, completed/failed job, model pagination, role-v2 detail, challenger skipped, legacy detail, and no leakage.

## Exit
API works independently of browser.
