# Step 2 — Schema v9, Audience Preparation Jobs, and Persistence

Use HEAD from successful Step 1. Do not implement search/profile/UI yet.

## Objective

Add minimum durable Phase 6 schema for percentile preparation and immutable saved audience definitions without a 5M rank/member table.

## Schema v9

Migrate additively from v8 to v9. Migration must be transactional, idempotent under normal initialization, and preserve every Phase 1–5 row/job/score.

## Extend jobs

Add job type:
`AUDIENCE_PREPARATION`

Allowed stages:
- QUEUED
- STARTING
- VALIDATING_SCORING_RUN
- PREPARING_RANK_BOUNDARIES
- VERIFYING_RANK_BOUNDARIES
- COMPLETED
- FAILED

Preserve MODEL_TRAINING and PROSPECT_SCORING constraints exactly.

Audience-preparation jobs use the existing shared lazy `ProcessPoolExecutor(max_workers=1)` and global heavy-compute exclusion. Startup reconciliation must fail stale active preparation jobs safely.

## audience_rank_boundaries

Create table with recommended columns:
```text
scoring_run_id INTEGER NOT NULL
percentile_bucket INTEGER NOT NULL CHECK 1..100
boundary_rank INTEGER NOT NULL CHECK >0
boundary_score REAL NOT NULL CHECK finite and 0..1
boundary_person_id TEXT NOT NULL
total_population INTEGER NOT NULL CHECK >0
rank_contract_version TEXT NOT NULL
created_at TEXT NOT NULL
PRIMARY KEY(scoring_run_id, percentile_bucket)
```

FK scoring_run_id -> scoring_runs.

Exactly 100 rows constitute a prepared run. Percentile 100 rank must equal total population. Persist no demographic features/PII.

## saved_audiences

Recommended fields:
```text
audience_id INTEGER PK AUTOINCREMENT
audience_name TEXT NOT NULL
description TEXT
created_at TEXT NOT NULL
scoring_run_id INTEGER NOT NULL
model_run_id INTEGER NOT NULL
analysis_run_id INTEGER NOT NULL
selection_mode TEXT NOT NULL
target_count INTEGER
resolved_count INTEGER NOT NULL
filter_contract_version TEXT NOT NULL
rank_contract_version TEXT NOT NULL
selection_contract_version TEXT NOT NULL
filters_json TEXT NOT NULL
selection_json TEXT NOT NULL
profile_summary_json TEXT
customer_import_id INTEGER NOT NULL
customer_source_checksum TEXT NOT NULL
campaign_sales_import_id INTEGER NOT NULL
campaign_sales_source_checksum TEXT NOT NULL
demographic_import_id INTEGER NOT NULL
demographic_source_checksum TEXT NOT NULL
feature_contract_version TEXT NOT NULL
feature_contract_sha256 TEXT NOT NULL
artifact_sha256 TEXT NOT NULL
```

Checks:
- name trimmed/bounded (~120 chars);
- description bounded (~500);
- mode ALL_MATCHING/TOP_N;
- TOP_N requires target_count >=1;
- ALL_MATCHING target may be NULL;
- resolved_count >=1;
- SHA fields valid length;
- filter/selection JSON non-null.

Use FKs where safe. Do not store mutable CURRENT status; calculate currentness dynamically.

## Repositories

Prefer dedicated repositories:
- `audience_rank_repository.py`
- `saved_audience_repository.py`

Support complete boundary publication/fetch and immutable audience create/list/detail.

No `audience_members` table.

## Tests

Cover v8->v9 preservation, job constraints, boundary checks, saved-audience checks, no audience_members table, idempotent initialization, and all prior regressions.

Run pytest, compileall, pip check, diff check, validation.

STOP.
