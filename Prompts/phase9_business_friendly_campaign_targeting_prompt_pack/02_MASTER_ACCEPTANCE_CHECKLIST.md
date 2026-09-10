# Phase 9 Master Acceptance Checklist

## Business experience
- [ ] Normal user can start from Create Campaign
- [ ] No ML/PU jargon required in default path
- [ ] Plain-language terminology is consistent
- [ ] Technical detail is progressively disclosed
- [ ] Existing technical pages remain available under Advanced/Insights

## Campaign context
- [ ] Campaign name
- [ ] Description
- [ ] Planned launch date
- [ ] Product multi-select
- [ ] Campaign Type multi-select
- [ ] Campaign Category multi-select
- [ ] Offer Type multi-select
- [ ] Campaign Channel
- [ ] Context normalized and persisted
- [ ] Context does not falsely alter prospect filters

## Targeting criteria
- [ ] Match Strength / minimum score
- [ ] True 0.10 score-band distribution
- [ ] Gender multi-select
- [ ] Age bucket multi-select
- [ ] State multi-select
- [ ] Optional coarse Region
- [ ] Income-group multi-select
- [ ] Advanced demographic criteria
- [ ] Optional TOP_N / target count
- [ ] Criteria versioned and backend-owned

## Output
- [ ] Exact matching count
- [ ] Exact selected count
- [ ] % of universe
- [ ] avg/min/max match score
- [ ] score distribution
- [ ] age/gender/state/income mix
- [ ] non-PII preview table
- [ ] deterministic ordering
- [ ] business-friendly “Why these people?” explanation
- [ ] source/currentness status

## Recommendations
- [ ] Very Strong / Strong / Good / Broad match choices
- [ ] exact counts per choice
- [ ] recommended option is explainable
- [ ] no claim of purchase probability

## Saved Target Group / Campaign
- [ ] business-facing saved target group
- [ ] immutable underlying Saved Audience
- [ ] exact filter hash/provenance retained
- [ ] campaign draft created from saved target group
- [ ] business context stored with campaign/draft
- [ ] PII remains export-only

## UX quality
- [ ] validation messages use plain language
- [ ] empty/loading/error/currentness states
- [ ] keyboard accessibility
- [ ] responsive layouts
- [ ] zero unexplained console errors
- [ ] zero unexplained critical network failures
- [ ] all Phase 9 controls accounted

## Regression
- [ ] Phase 1–8 tests still pass
- [ ] clean-room still passes
- [ ] existing Audience Explorer still works
- [ ] existing Campaign Builder still works
- [ ] CI green
- [ ] Phase 9 docs/evidence complete
- [ ] Phase 10 handoff contract documented
