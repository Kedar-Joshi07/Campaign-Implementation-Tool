# Phase 5 Scoring API Contract

Required:

```text
POST /api/models/{model_run_id}/score
GET /api/models/{model_run_id}/scoring-status
GET /api/scoring-runs
GET /api/scoring-runs/{scoring_run_id}
```

Existing GET `/api/jobs/{job_id}` supports scoring.

POST returns 202 queued job only, no score rows.

Scoring status returns scoreability, demographic count, selected candidate, artifact/feature compatibility, active job and completed run summary.

Scoring run detail returns identity/population/model provenance/aggregate score summary only.

HTTP: 200 reads, 202 accepted, 404 missing, 409 unscoreable/already-scored/active, 422 malformed, 500 sanitized failure.

Public scoring APIs must never contain person_id, customer_id, PII, individual score rows, raw features, validation scores, SQL, traceback or absolute paths.
