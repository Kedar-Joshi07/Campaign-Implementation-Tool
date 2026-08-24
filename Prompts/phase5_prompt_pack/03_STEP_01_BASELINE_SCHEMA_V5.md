# Step 1 — Baseline Verification and Schema v5

## Objective

Add persistence foundations only. No scoring execution/API/UI.

## Baseline

Record HEAD, worktree, schema v4, full tests, pip, compile, data validation, verified Bagging artifact, feature contract.

## v4 → v5

Transactional migration preserving every old row.

### Rebuild jobs safely

SQLite CHECK must expand from only `MODEL_TRAINING` to:

```text
MODEL_TRAINING
PROSPECT_SCORING
```

Preserve all old job IDs/fields and old training stages.

Scoring stages:

```text
QUEUED
STARTING
VALIDATING_MODEL
PREPARING_SCORING_RUN
SCORING_PROSPECTS
FINALIZING_SCORES
VERIFYING_COMPLETENESS
COMPLETED
FAILED
```

Add type/stage compatibility. Training requires `analysis_run_id`; scoring requires `analysis_run_id IS NULL` and `model_run_id`.

### scoring_runs

Recommended fields:

```text
scoring_run_id INTEGER PK AUTOINCREMENT
job_id INTEGER NOT NULL UNIQUE
model_run_id INTEGER NOT NULL
created_at TEXT NOT NULL
completed_at TEXT
status CHECK IN RUNNING/COMPLETED/FAILED

demographic_snapshot_count INTEGER NOT NULL
demographic_min_person_id TEXT
demographic_max_person_id TEXT
scored_person_count INTEGER NOT NULL DEFAULT 0
chunk_size INTEGER NOT NULL
last_person_id TEXT

selected_candidate TEXT NOT NULL
model_role_policy_version TEXT NOT NULL
feature_contract_version TEXT NOT NULL
feature_contract_sha256 TEXT NOT NULL
artifact_sha256 TEXT NOT NULL

score_min REAL
score_max REAL
score_mean REAL
score_summary_json TEXT
error_message TEXT
```

FKs `job_id→jobs`, `model_run_id→model_runs`; counts nonnegative; chunk bounds; hash length 64; terminal timestamps; FAILED requires error; COMPLETED requires exact count equality and finite summary fields. Add `UNIQUE(scoring_run_id, model_run_id)`.

Indexes: newest, model/newest, status, plus a partial unique index allowing only one COMPLETED scoring run per model while permitting failed retries.

### propensity_scores

Exactly:

```text
scoring_run_id INTEGER NOT NULL
model_run_id INTEGER NOT NULL
person_id TEXT NOT NULL
propensity_score REAL NOT NULL CHECK BETWEEN 0 AND 1
PRIMARY KEY(scoring_run_id, person_id)
```

Composite FK `(scoring_run_id,model_run_id)→scoring_runs`, `person_id→demographics`.

Required rank index:

```text
(scoring_run_id, propensity_score DESC, person_id ASC)
```

No PII/features/rank/band.

### Repository

Create `scoring_repository.py` with create/fetch/list/update counters/complete/fail/find completed/find running primitives. No chunk reading yet if kept for Step 2.

## Tests

Fresh v5; populated v4 migration; all old jobs preserved; training/scoring type-stage checks; rollback; idempotence; scoring FKs/constraints; completed equality; failed rules; [0,1]; duplicate score rejection; one completed run per model; indexes.

STOP after Step 1.
