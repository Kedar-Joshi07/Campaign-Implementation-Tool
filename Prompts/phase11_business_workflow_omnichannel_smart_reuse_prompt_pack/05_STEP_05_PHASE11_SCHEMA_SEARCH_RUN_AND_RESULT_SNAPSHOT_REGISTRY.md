# Step 5 — Phase 11 Schema: Search Runs & Result Snapshot Registry

## Objective
Persist every business submission separately from reusable immutable result membership.

Increment schema version additively.

### A. campaign_search_runs
Recommended fields:
- search_run_id
- search_run_contract_version
- campaign_name
- description
- planned_launch_date
- targeting_context_id
- modeling_context_sha256
- targeting_criteria_json / sha256
- filter_branches_json / sha256
- selection_mode
- target_count
- delivery_channel
- export_profile
- generation_id
- analysis_run_id
- model_run_id
- scoring_run_id
- result_snapshot_id
- result_source
- status
- selected_count
- started_at
- completed_at
- processing_seconds
- created_by_user_id nullable
- safe_error_message

Statuses:
QUEUED, PROCESSING, COMPLETED, BLOCKED, FAILED.

Result source:
EXACT_RESULT_REUSE
INTELLIGENCE_REUSE
NEW_INTELLIGENCE_BUILD

### B. campaign_result_snapshots
Recommended:
- result_snapshot_id
- result_membership_contract_version
- generation_id
- targeting_criteria_sha256
- filter_branches_sha256
- selection_mode
- target_count
- result_cache_key_sha256 UNIQUE
- resolved_count
- storage_format
- storage_uri
- snapshot_sha256
- created_at
- last_verified_at
- last_used_at
- currentness_state

Never store contact PII in snapshot metadata or membership.

### C. campaign_result_export_events
Either extend existing campaign_export_events carefully or create search-result-specific audit table.
Prefer a new table if existing campaign_id/finalization semantics would be weakened.

Store:
search_run_id, snapshot_id, profile/version, status, selected/deliverable/undeliverable,
row_count, checksum, timestamps, currentness, safe error.

Indexes:
created_at DESC, status, result_cache_key, generation_id, snapshot_id, targeting_context_id.

Repository/service boundaries only; no frontend SQL.

Migration from schema 15 must be idempotent and preserve Phase1–10 rows.

Evidence:
`docs/evidence/phase11/05_SEARCH_RUN_RESULT_SCHEMA.md`

STOP.
