# Step 1 — Schema v4 and Persistent Job Foundation

## Objective
Add durable SQLite job state. Do not add execution or HTTP APIs yet.

## Tasks
### A. Baseline evidence
Record HEAD, status, pytest, pip check, compileall, data validation, schema version, and one verified Phase 3 model artifact.

### B. Add v3→v4 migration
Create `jobs` with:
```text
job_id INTEGER PRIMARY KEY
job_type TEXT NOT NULL
status TEXT NOT NULL
progress_percent INTEGER NOT NULL DEFAULT 0
stage TEXT NOT NULL
message TEXT
analysis_run_id INTEGER
model_run_id INTEGER
created_at TEXT NOT NULL
started_at TEXT
finished_at TEXT
request_json TEXT NOT NULL
result_json TEXT
error_message TEXT
```

Constraints:
```text
job_type IN ('MODEL_TRAINING')
status IN ('QUEUED','RUNNING','COMPLETED','FAILED')
progress_percent BETWEEN 0 AND 100
```

FKs:
```text
analysis_run_id -> historical_analysis_runs.analysis_run_id
model_run_id -> model_runs.model_run_id
```

Indexes:
```text
idx_jobs_newest
idx_jobs_status
idx_jobs_analysis_run_id
idx_jobs_model_run_id
```

Migration must be additive, transactional, idempotent, and preserve populated Phase 1–3 data.

### C. Job repository
Create `app/repositories/job_repository.py` or equivalent with:
```text
create_training_job
fetch_job
find_active_training_job
mark_running
update_progress
mark_completed
mark_failed
fail_stale_active_jobs
```

State transitions must be guarded. Terminal jobs cannot restart.

### D. JSON rules
Canonical finite JSON. Persist only frozen training request fields. No PII, customer IDs, raw score arrays, training matrices, SQL, or absolute paths.

### E. Tests
Cover fresh v4, populated v3 migration, rollback, idempotence, constraints, FKs, indexes, guarded transitions, active detection, newest ordering, and absence of propensity table.

## Exit
Schema v4 and repository are complete; no execution/API/UI yet.
