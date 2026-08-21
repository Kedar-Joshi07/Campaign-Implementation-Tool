# Phase 4 Model and Job API Contract

## POST /api/models/train
HTTP 202 request fields:
```text
analysis_run_id
model_name
random_seed
validation_fraction
run_elkan_challenger
```
Return job summary immediately.

## GET /api/jobs/{job_id}
Return job identity, status, progress, stage, safe message, analysis/model run IDs, timestamps, bounded result, safe error.

## GET /api/models
Paginated newest-first summaries. Limit 1–100. Optional status filter.

## GET /api/models/{model_run_id}
Recommended safe structure:
```text
identity
cohort
governance
candidates
challenger_comparison
quality_flags
artifact
feature_contract
runtime
```
Artifact verification should be explicit. Never expose absolute path, PII, IDs lists, raw scores, or traceback.

## GET /api/models/training-options
Return completed historical analyses, defaults, role-policy-v2 governance, and active job if present.

## Errors
```text
200 list/detail/options
202 accepted
404 missing resource
409 active job/unusable source state
422 validation
500 sanitized failure
```

## Legacy models
Role-policy-v1 historical runs remain immutable and must be labeled legacy when role metadata is absent. Do not reinterpret them as v2.
