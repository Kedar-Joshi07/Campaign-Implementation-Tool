# Phase 9 Closure Acceptance Checklist

## Interoperability
- [x] Phase 9 multi-branch groups are detectable by Audience Explorer
- [x] Reopen never silently loads only branch #1
- [x] Full branch replay OR safe block/redirect is implemented
- [x] Legacy single-branch audiences still reopen normally
- [x] Exact resolved count remains unchanged
- [x] Campaign/export membership remains unchanged
- [x] No duplicate person IDs

## Regression tests
- [x] Legacy single-branch reopen
- [x] Phase 9 single-branch Target Group
- [x] Phase 9 multi-branch Target Group
- [x] Branch hash validation
- [x] Resolved-count validation
- [x] Campaign-member regression
- [x] Export-member regression
- [x] Immutability regression
- [x] No-PII regression
- [x] Currentness/stale regression

## Browser recertification
- [x] Very Strong Match explicitly selected
- [x] Marital Status explicitly changed
- [x] Employment Status explicitly changed
- [x] Resident Status explicitly changed
- [x] Resident Type explicitly changed
- [x] Type of Employment explicitly changed
- [x] Top Matching Percentage explicitly exercised
- [x] Clear All explicitly exercised
- [x] Review-step Back explicitly exercised
- [x] Any other contract-only PASS control upgraded to browser proof
- [x] FAIL = 0
- [x] NOT_RUN = 0
- [x] unjustified exclusions = 0

## Documentation
- [x] Phase 9 implementation summary uses final candidate/freeze values
- [x] Control totals match authoritative control ledger
- [x] Final SHA references are consistent
- [x] Historical evidence remains clearly historical
- [x] Phase 10 handoff unchanged

## Release
- [x] Full pytest green
- [x] Clean-room Phase1→7 green
- [x] Phase 8 harness tests green
- [x] Phase 9 focused tests green
- [x] compileall green
- [x] pip check green
- [x] git diff --check green
- [x] repo/LFS hygiene green
- [ ] exact-SHA CI green
- [ ] FINAL DECISION = GO
