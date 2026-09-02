# Step 2 — Schema v11 Campaign Persistence

Advance 10 -> 11 using additive migration only.
Do not rebuild/copy 5M core tables.

## campaigns
Recommended:
campaign_id PK
campaign_contract_version
campaign_name
description
channel
planned_launch_date
saved_audience_id FK
scoring_run_id
model_run_id
analysis_run_id
saved_audience_filter_hash
saved_audience_selection_json
saved_audience_resolved_count
filter/rank/selection/analytics contract versions
member_resolution_contract_version
export_contract_version
status DRAFT|FINALIZED
created_at
updated_at
finalized_at

No contact PII.

## campaign_export_events
export_event_id PK
campaign_id FK
export_contract_version
export_profile
status STARTED|COMPLETED|FAILED|ABORTED
selected_count
deliverable_count
undeliverable_count
row_count
csv_sha256
started_at
completed_at
safe_error_message

No PII rows/file path/traceback.

Tests:
v10->v11 additive, no member table, no PII columns, FKs/checks, idempotence, fresh DB.
STOP.
