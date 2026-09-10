# Step 14 — System-Browser End-to-End Phase 9 Certification

## Objective
Prove the new Phase 9 business-user workflow works end to end in the real installed system browser.

Use:
1. Google Chrome preferred
2. Microsoft Edge fallback

Do not use VS Code Simple Browser or an IDE webview.

## Clean certification state
Start from:
- committed candidate SHA
- clean git status
- valid Phase 1–8 runtime/data
- at least one explicit READY/current targeting-intelligence source suitable for Phase 9 preview
- no fake “latest scoring run” fallback

Phase 9 certification does NOT need to retrain and rescore 5M if the frozen Phase 8 source remains current and explicitly linked. Phase 10 will own automatic model/scoring orchestration.

## Business-user scenario

A non-technical user must be able to:

1. Open Create Campaign.
2. Enter campaign name/description/launch date.
3. Select multiple products.
4. Select campaign type/category/offer.
5. Select delivery channel.
6. Continue without seeing required ML jargon.
7. Choose Targeting Strength.
8. Select multiple genders where supported.
9. Select multiple age buckets.
10. Select states/region.
11. Select income groups.
12. Open More Targeting Options.
13. Select at least one advanced demographic criterion.
14. Review exact target-group estimate.
15. Compare Very Strong / Strong / Good / Broad counts.
16. Apply a recommendation.
17. Review demographic mix.
18. Search/paginate the potential-customer preview.
19. Open “Why these people?”
20. Open “View technical details.”
21. Verify default UI remained business-friendly.
22. Save Target Group.
23. Create Campaign Draft.
24. Reopen the campaign draft.
25. Verify business context and target-group summary.
26. Verify PII is absent from planning/preview.
27. Navigate to Advanced tools and verify existing Phase 1–8 pages remain functional.

## Required alternate/error scenarios
- no targeting intelligence available
- stale targeting intelligence
- zero matching people
- invalid target-count
- invalid/mutually conflicting targeting preferences
- backend retryable error
- Back/Next state preservation
- refresh/reopen
- changing criteria after a Saved Target Group creates a new immutable target group rather than mutating the old one

## Control coverage
Create/refresh the Phase 9 actionable-control inventory.

Terminal statuses:
- PASS
- FAIL
- JUSTIFIED_EXCLUSIVE

Required:
- NOT_RUN = 0
- FAIL = 0
- unjustified exclusions = 0

## Browser telemetry
Require:
- zero unexplained console errors
- zero unexplained JS exceptions
- zero unexplained critical network failures

## Independent backend assertions
After browser actions verify:
- exact targeting-context normalization
- target criteria normalization
- targeting source explicitly linked/current
- exact estimate/selection counts
- saved audience immutable
- filter hash/provenance correct
- campaign draft linked to correct saved target group/context
- no PII in preview APIs
- existing Phase 7 export contracts unchanged

## Evidence
Create:
`docs/evidence/phase9/final_system_browser/PHASE9_SYSTEM_BROWSER_CERTIFICATION_REPORT.md`
`docs/evidence/phase9/final_system_browser/phase9_certification_manifest.json`
`docs/evidence/phase9/final_system_browser/ui_control_coverage.json`

Record:
- candidate SHA
- browser/version
- campaign context
- criteria
- targeting source
- exact counts
- saved target-group ID
- campaign draft ID
- console/network status
- control coverage
- currentness
- timings
- final local decision

STOP.
