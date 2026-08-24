# Step 5 — Scoring APIs

## Required endpoints

```text
POST /api/models/{model_run_id}/score
GET  /api/models/{model_run_id}/scoring-status
GET  /api/scoring-runs
GET  /api/scoring-runs/{scoring_run_id}
```

Existing `GET /api/jobs/{job_id}` must support scoring jobs.

### POST score

Validate scoreability/completed-score/active job, persist job, submit worker, return HTTP 202 immediately. No request body needed unless framework convention requires `{}`.

### scoring-status

Aggregate only: model_run_id, eligible/reason, demographic_count, selected candidate, artifact/feature compatibility, active job, completed scoring run.

### scoring-run list/detail

Paginated newest first; optional status/model filters. Detail includes identity/population/model contract/score summary. Never return person_id or individual scores.

## Errors

200 status/list/detail; 202 accepted; 404 missing; 409 unscoreable/already-scored/active compute; 422 malformed; 500 sanitized internal.

## Tests

OpenAPI; 202; conflicts; missing/legacy; status/list/detail/pagination; scoring job detail; no person/customer/PII/score rows/raw features/SQL/path/traceback; finite response serialization. Existing training APIs unchanged.

STOP after Step 5.
