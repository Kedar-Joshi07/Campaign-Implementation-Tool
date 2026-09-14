# Step 4 — Phase 10 Schema, Registry & Repositories

Increment SQLite schema version and add focused Phase 10 persistence without mutating
old immutable analytical assets.

Recommended tables:

## phase10_intelligence_generations
Store:
generation_id, generation/compatibility versions, modeling_context_json/SHA,
historical_filters_json/SHA, historical/multi-product/training policy versions,
customer/campaign/demographic import IDs+checksums, feature version/SHA,
model-role/evaluation/training policy versions, analysis_run_id, model_run_id,
scoring_run_id, artifact SHA, score semantics, rank/analytics versions,
lifecycle_state, created_at, last_verified_at, last_used_at.

A READY generation must have complete valid analytical IDs.

## phase10_orchestration_runs
Store:
orchestration_id/version, targeting_context_id, modeling_context_sha,
intelligence_key_sha, status, stage, progress 0..100, business_message,
technical_message, reuse_plan_json, analysis/model/scoring/generation IDs,
training/scoring child job IDs, created/started/updated/completed timestamps,
safe_error_message.

Statuses: QUEUED, RUNNING, READY, BLOCKED, FAILED.

## phase10_context_bindings
Map targeting_context_id to modeling_context_sha, orchestration_id, generation_id,
binding_status and timestamps. Multiple campaign contexts may share one generation.

Add indexes for context/intelligence hashes, lifecycle, analytical IDs, active orchestration,
and targeting context.

Constraints: valid JSON, 64-char SHA, allowed states, positive IDs, progress bounds.
Prevent duplicate exact active orchestration where safely enforceable.

Create a focused repository with atomic stage updates, active lookup, generation
lookup/insert/verify, binding, usage touch, lifecycle/reference queries.

Upgrade a Phase 9 database idempotently. No old row rewritten/deleted.

Evidence:
`docs/evidence/phase10/04_SCHEMA_AND_REGISTRY.md`

STOP.
