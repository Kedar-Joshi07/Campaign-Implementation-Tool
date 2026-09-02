# Step 2 — Schema v10 & Provenance-Bound Analytics Snapshot

## Objective

Introduce a **small additive analytics snapshot** so static 5M analytics are prepared once and reused.

Add `AUDIENCE_ANALYTICS_CONTRACT_VERSION = "1"`.

Advance schema `9 -> 10` with a purely additive migration.

## CRITICAL

Do not rebuild/copy `jobs`, `scoring_runs`, `propensity_scores`, `demographics`, `customers`, or `campaign_sales`. Do not alter job CHECK constraints solely to create analytics-specific stages. Reuse existing `AUDIENCE_PREPARATION` type/stages/messages.

## New table

Create `audience_analytics_snapshots` (or equally clear name) with aggregate-only columns:

- scoring_run_id + analytics_contract_version
- model_run_id, analysis_run_id
- customer/campaign/demographic import IDs + checksums
- feature contract version/SHA, artifact SHA
- filter/rank/selection contract versions
- population_count
- options_json
- universe_profile_json
- historical_positive_profile_json
- score_bucket_stats_json
- created_at

Recommended PK: `(scoring_run_id, analytics_contract_version)`.

Add safe FKs/checks. Never store person IDs, customer IDs, names, email, phone, addresses, postal codes, raw member arrays, PII, or 5M ranks.

## Currentness helper

Implement `validate_audience_analytics_snapshot_currentness()` (or equivalent). A snapshot is usable only if scoring/model/analysis IDs, all three source provenances, feature/artifact SHAs, filter/rank/selection/analytics contract versions, and population count match the current canonical scoring chain. Use lightweight currentness; do not deep-scan 5M per read.

## Payload safety

Set sensible JSON size limits and tests preventing accidental large member arrays.

## Migration tests

Prove v9->v10 preserves existing data/IDs/counts, no 5M table rebuild occurs, snapshot table exists, initialization is idempotent, fresh DB reaches v10, and old v9 fixture migrates cleanly.

STOP until schema v10 is clean and additive.
