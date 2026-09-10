# Phase 9 — Campaign Planning & Business-Friendly Targeting Experience

Repository:
`https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Frozen Phase 1–8 baseline:
`d6a9f9b963622a334bf3e5c3220e5d0a73e528fe`

## Purpose

Phase 9 transforms the current technically correct but analyst-oriented workflow into a business-friendly campaign planning and target-group experience.

Normal business users must NOT need to understand:
- Historical Analysis
- Positive/Unlabeled populations
- PU learning
- algorithm names
- model training
- model artifacts
- scoring runs
- feature contracts
- rank contracts
- SHA/provenance IDs

The technical machinery remains available in Advanced / Technical Details views for analysts, developers, audit, and troubleshooting.

The normal business flow should become:

Create Campaign
→ What are you promoting?
→ Who would you like to reach?
→ How selective should targeting be?
→ Review recommended target group
→ Save Target Group
→ Create Campaign Draft

Phase 10 will later make campaign-context intelligence fully automatic.

## Frozen quality rule

Correctness, data integrity, business meaning, reproducibility, provenance, privacy, and validated output take priority over convenience or speed. Do not introduce sampling, approximation, hidden semantic shortcuts, weak compatibility assumptions, or misleading labels merely to make the workflow faster or simpler. Simplify the user experience, not the analytical truth.

## Phase 9 / Phase 10 boundary

Phase 9 is the business-user experience and targeting-criteria layer. Phase 10 will add automatic campaign-context model resolution, compatible-model/scoring reuse, and automatic build orchestration. Phase 9 MUST NOT silently pretend that Product, Campaign Type, Campaign Category, Offer Type, or Channel have already changed the model/scoring source unless an explicit compatible targeting-intelligence source is genuinely linked and verified.

## Step order

1. `01_STEP_01_BASELINE_AND_PHASE9_GAP_ANALYSIS.md`
2. `02_STEP_02_BUSINESS_TERMINOLOGY_AND_INFORMATION_ARCHITECTURE.md`
3. `03_STEP_03_PHASE9_TARGETING_CONTRACTS_AND_SCHEMA.md`
4. `04_STEP_04_BUSINESS_CAMPAIGN_WIZARD_SHELL.md`
5. `05_STEP_05_CAMPAIGN_CONTEXT_CAPTURE.md`
6. `06_STEP_06_BUSINESS_TARGETING_CRITERIA_CONTROLS.md`
7. `07_STEP_07_TARGETING_INTELLIGENCE_SOURCE_BOUNDARY.md`
8. `08_STEP_08_TARGET_GROUP_ESTIMATE_SEARCH_PROFILE_AND_EXPLANATION.md`
9. `09_STEP_09_RECOMMENDATIONS_AND_MATCH_STRENGTH_COMPARISON.md`
10. `10_STEP_10_SAVE_TARGET_GROUP_AND_CREATE_CAMPAIGN_DRAFT.md`
11. `11_STEP_11_ADVANCED_TECHNICAL_DETAILS_AND_PROGRESSIVE_DISCLOSURE.md`
12. `12_STEP_12_VALIDATION_ERROR_EMPTY_LOADING_AND_CURRENTNESS_STATES.md`
13. `13_STEP_13_ACCESSIBILITY_RESPONSIVE_AND_BUSINESS_USABILITY.md`
14. `14_STEP_14_SYSTEM_BROWSER_END_TO_END_PHASE9_CERTIFICATION.md`
15. `15_STEP_15_REGRESSION_CI_DOCUMENTATION_AND_PHASE9_FREEZE.md`

Run all steps in order and obey every STOP/NO-GO condition.
