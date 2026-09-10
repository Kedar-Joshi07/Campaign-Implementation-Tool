# Step 2 — Business Terminology & Information Architecture

## Objective
Design the default experience for a non-technical business user while preserving existing technical capability.

## Navigation redesign
Recommended top-level business navigation:
- Home / Overview
- Create Campaign
- Saved Target Groups
- Campaigns
- Insights

Technical pages should remain available under:
- Advanced
  - Historical Analysis
  - Targeting Intelligence / Model Management
  - Scoring / Targeting Results
  - Audience Explorer

Do not delete technical pages.

## Default business path
Create Campaign
→ Campaign Details
→ Campaign Context
→ Targeting Preferences
→ Target Group Preview
→ Review
→ Save Target Group
→ Create Campaign Draft

## Terminology
Implement the Business Terminology Contract from the pack.

No default screen should require understanding:
PU, P/U, algorithm, model artifact, scoring run, feature contract, rank contract, SHA, calibration, candidate model.

## Tooltips / explainers
Add short plain-language help for:
- Targeting Match Score
- Targeting Strength
- Potential Customer
- Saved Target Group
- Up to date / Needs refresh
- Why these people?

## Technical detail
Every business result must be traceable through optional:
`View technical details`

but technical detail must not dominate the normal workflow.

## Acceptance
Create a page/flow map and terminology matrix.
Update existing UI strings only where safe and regression-tested.

Create:
`docs/evidence/phase9/02_BUSINESS_UX_AND_TERMINOLOGY_REPORT.md`

STOP.
