# Step 6 — Audience Profile Redesign for 5M Performance

## Objective
Stop recomputing static universe and historical-positive analytics on every profile request.

## Architecture
STATIC: universe profile + historical-positive profile from analytics snapshot.
DYNAMIC: matching + selected only.

## Remove static live work
Do not materialize 5M `universe_members` in normal profile requests. Do not reconstruct historical positives live. Read both from snapshot after currentness validation.

## Fast paths

### No filters + ALL_MATCHING
universe=matching=selected=snapshot universe; historical positives=snapshot. Target `<2 sec`.

### No filters + TOP_N
matching=universe snapshot; compute only selected TOP_N dynamic profile.

### Filtered ALL_MATCHING
Compute matching dynamic profile once and reuse as selected.

### Filtered TOP_N where N >= matching_count
Compute matching once and reuse as selected while preserving TOP_N definition.

### Filtered TOP_N where N < matching_count
Compute matching profile plus selected TOP_N profile only.

## Dynamic profiler
Create one reusable exact SQL population-profiler returning summary + distributions for ONE dynamic population. Do not fetch all matching IDs into Python. No permanent member table. Do not unpivot the entire 5M universe during normal requests.

A connection-local TEMP table is allowed only if measured to improve dynamic filtered profiling; TEMP only, no PII, no persistence/cross-request sharing.

## Exactness
No sampling, approximate counts, approximate distributions, or probabilistic estimates.

## Preserve response contract
Keep scoring_run_id, contract versions, filter_hash, selection, source_verified, historical_reference_date, summary, distributions, comparisons, top_overindexed_traits.

## Performance
- no-filter ALL_MATCHING `<2 sec`
- top 1% `<=60 sec` threshold
- filtered TOP_N 50K `<=60 sec` threshold
- heavy bounded profile flows in `120-180 sec` are acceptable only when authenticity, quality, and usefulness of data remain unchanged

If still multi-minute: NO-GO.

## Regression
Compare optimized output to reference semantics for all selection/filter modes including Unknown/Other. Business results must not change.

## Quality-first guardrail
Any timing win that weakens exactness, provenance currentness, or interpretability/usefulness is a regression and must be rejected even if runtime improves.
