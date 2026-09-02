# Step 3 — Analytics Preparation, Backfill & Snapshot Publication

## Objective

Extend existing Audience Preparation so readiness requires both 100 rank boundaries and analytics snapshot v1. Continue using the existing shared `ProcessPoolExecutor(max_workers=1)` and heavy-compute exclusion.

## Decision matrix

- Missing boundaries + missing snapshot: deep validate -> rank scan -> boundaries -> analytics -> verify.
- Boundaries current + snapshot missing: allow **analytics-only backfill**; do not reject or rewrite valid boundaries.
- Both current: deterministic already-prepared response.
- Snapshot stale: historical only; rebuild only for current canonical run.

## Static universe analytics

For a canonical run whose provenance proves exact score/demographic alignment, derive static demographic analytics directly from `demographics`; use scoring-run metadata for score min/mean/max/population. Do not join scores just to derive static options/profile.

## Historical-positive analytics

During preparation, reconstruct positives from the exact saved Phase 2 analysis, use saved `contact_date_to` as age reference, persist aggregate summary/distributions only, and verify count equals `historical_analysis_runs.positive_customer_count`. Never persist customer IDs.

## Score bucket stats

Persist exact percentile bucket 1..100 stats: bucket, count, score_min, score_max, score_sum, score_mean. Current 5M should be 50,000 per bucket. Calculate during rank scan when possible; for analytics-only backfill use one bounded keyset score scan and ~100 accumulators. No 5M Python list.

## Transactional publication

Compute outside final write transaction -> revalidate current provenance -> validate snapshot -> short atomic upsert -> verify persisted payload. If provenance changes mid-build, FAIL without publication.

Validate population totals, option/profile totals, positive count, finite shares/scores, 100 buckets, bucket total, and no forbidden identifiers.

## Status API

Expose `analytics_prepared` and `analytics_contract_version` (optional created_at). Define `ready_for_current_audience_actions = boundaries_prepared AND analytics_prepared AND is_canonical AND source_verified`.

## Real DB backfill

On current canonical DB, existing boundaries should remain unchanged while analytics snapshot is backfilled. No data/model/scoring rerun.

STOP until preparation/backfill tests pass.
