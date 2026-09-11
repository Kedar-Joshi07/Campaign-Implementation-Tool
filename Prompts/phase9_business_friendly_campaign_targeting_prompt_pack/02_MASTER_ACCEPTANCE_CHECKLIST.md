# Phase 9 Master Acceptance Checklist

## Business experience
- [x] Normal user can start from Create Campaign
- [x] No ML/PU jargon required in default path
- [x] Plain-language terminology is consistent
- [x] Technical detail is progressively disclosed
- [x] Existing technical pages remain available under Advanced/Insights

## Campaign context
- [x] Campaign name
- [x] Description
- [x] Planned launch date
- [x] Product multi-select
- [x] Campaign Type multi-select
- [x] Campaign Category multi-select
- [x] Offer Type multi-select
- [x] Campaign Channel
- [x] Context normalized and persisted
- [x] Context does not falsely alter prospect filters

## Targeting criteria
- [x] Match Strength / minimum score
- [x] True 0.10 score-band distribution
- [x] Gender multi-select
- [x] Age bucket multi-select
- [x] State multi-select
- [x] Optional coarse Region
- [x] Income-group multi-select
- [x] Advanced demographic criteria
- [x] Optional TOP_N / target count
- [x] Criteria versioned and backend-owned

## Output
- [x] Exact matching count
- [x] Exact selected count
- [x] % of universe
- [x] avg/min/max match score
- [x] score distribution
- [x] age/gender/state/income mix
- [x] non-PII preview table
- [x] deterministic ordering
- [x] business-friendly “Why these people?” explanation
- [x] source/currentness status

## Recommendations
- [x] Very Strong / Strong / Good / Broad match choices
- [x] exact counts per choice
- [x] recommended option is explainable
- [x] no claim of purchase probability

## Saved Target Group / Campaign
- [x] business-facing saved target group
- [x] immutable underlying Saved Audience
- [x] exact filter hash/provenance retained
- [x] campaign draft created from saved target group
- [x] business context stored with campaign/draft
- [x] PII remains export-only

## UX quality
- [x] validation messages use plain language
- [x] empty/loading/error/currentness states
- [x] keyboard accessibility
- [x] responsive layouts
- [x] zero unexplained console errors
- [x] zero unexplained critical network failures
- [x] all Phase 9 controls accounted

## Regression
- [x] Phase 1–8 tests still pass
- [x] clean-room still passes
- [x] existing Audience Explorer still works
- [x] existing Campaign Builder still works
- [x] CI green
- [x] Phase 9 docs/evidence complete
- [x] Phase 10 handoff contract documented
