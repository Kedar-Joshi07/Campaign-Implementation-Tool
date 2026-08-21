# Phase 4 Security and Test Matrix

## Public API must never expose
- traceback;
- SQL;
- absolute DB/artifact path;
- customer/person ID lists;
- PII;
- raw validation scores;
- training matrices.

## Safe failure examples
- A model training job is already active.
- The selected historical analysis is not available for training.
- Model training could not be completed.
- The model artifact could not be verified.
- The requested job was not found.

## Test groups
### Schema
fresh v4, populated migration, rollback, idempotence, constraints, no propensity table.

### Job repository
create, active detection, guarded transitions, monotonic progress, complete/fail, stale fail, ordering.

### Orchestration
immediate submit, bounded worker, success, primary failure, challenger skip, executor failure, one-active rule, startup reconciliation.

### Phase 3 compatibility
CLI still runs, callback optional, Bagging artifact unchanged structurally, legacy artifact loads.

### API
OpenAPI, 202, 409, job, model list/detail/options, 404/422, sanitized errors, pagination.

### Frontend
navigation, options, form, submit, polling, terminal stop, result, comparison, advisory, diagnostic label, no scoring.

### Hardening
race, restart, shutdown, safe paths, no PII/raw IDs/scores, bounded output.

### Full regression
Phase 1, Phase 2, Phase 3, full pytest, pip check, compileall, diff, data validation.
