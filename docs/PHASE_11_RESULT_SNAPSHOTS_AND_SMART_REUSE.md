# Phase 11 Result Snapshots and Smart Reuse

## Search history is not snapshot storage

Every valid intentional submission creates a new immutable `campaign_search_runs` row. A `campaign_result_snapshots` row represents reusable analytical membership. Therefore repeated identical searches have distinct history IDs while sharing one validated snapshot; delivery-profile or campaign-description changes also retain their own history without rebuilding membership.

Snapshots contain only ordered analytical membership: `person_id`, propensity score, percentile bucket, decile, and rank band. Contact PII is never persisted. The companion manifest binds the snapshot, generation, Modeling Context, source imports/checksums, analysis/model/scoring IDs, criteria/branch/cache hashes, selection, schema, count, timestamp, and artifact SHA.

## Decision order

1. Compute the versioned exact cache key.
2. If a current registry row, member file, manifest, generation, source identity, schema, count, ordering, and checksum all validate, reuse it as `EXACT_RESULT_REUSE` without reading the score population or invoking the membership source.
3. Otherwise ask Phase 10 for exact compatibility. If compatible intelligence is READY, stream the requested filters and publish a snapshot as `INTELLIGENCE_REUSE`.
4. Otherwise let Phase 10 build only the missing incompatible layers, then filter and publish as `NEW_INTELLIGENCE_BUILD`.

The cache key includes membership-affecting generation, normalized criteria/branches, selection, and contract identities. It excludes name, description, launch date, delivery channel, and export profile. There is no latest-run fallback and no all-permutation precompute.

## Publication and recovery

Membership is streamed to a controlled temporary gzip file, closed and synced, fully validated, atomically renamed, revalidated, and registered in one short SQLite transaction. Concurrent exact publishers reuse a valid committed winner. A corrupt or missing artifact is reusable only after deterministic regeneration reproduces the immutable registered count and SHA.

Orphan recovery is bounded and age-gated, ignores registered snapshots, rejects symlinks/nesting/unknown files, and touches only known pending/final result directories. Search processing and Phase 10 preparation are durable and resumable after restart.

The optional atomic-segment index was benchmarked and not adopted. Existing exact-snapshot reuse plus Phase 10 intelligence reuse avoids speculative storage/build cost and remains the frozen Phase 11 design.
