# Step 8 — Target Group Estimate, Search, Profile & Explanation

## Objective
Use the existing Phase 6 Audience Engine underneath a business-friendly Target Group Preview.

## Exact preview
For a valid READY targeting source and criteria, show:

KPI cards:
- Potential Customers Available
- Matching Your Preferences
- Selected for Target Group
- % of Available People
- Average Targeting Match Score
- Strongest Match
- Lowest Selected Match

Do not show IDs like scoring_run_id on the default screen.

## Distribution
Show non-overlapping Targeting Match Score bands:
- 0.90–1.00
- 0.80–<0.90
- 0.70–<0.80
- 0.60–<0.70
- lower bands if relevant

## Demographic mix
Business labels:
- Age Mix
- Gender Mix
- Where They Are Located
- Income Mix
- other advanced demographic profiles if selected

## Preview table
Allowed fields:
- person_id (or business-facing “Potential Customer ID”)
- Targeting Match Score
- Top Matching %
- Match Strength
- approved demographic attributes

No:
- name
- email
- phone
- street address
- customer_id
- prohibited demographic fields

## Search/pagination
Reuse deterministic keyset behavior.
No duplicate IDs across pages.

## Why these people?
Add plain-language explanation generated deterministically from:
- campaign context
- targeting-intelligence readiness/source category
- selected targeting criteria
- match threshold

Example:
“These potential customers match the targeting preferences you selected and have a high similarity score under the validated targeting intelligence currently linked to this campaign.”

Do not claim causality or purchase probability.

## Currentness
Show:
- Up to date
- Needs refresh
- unavailable

Technical provenance only under details.

## Reuse
Do not duplicate Phase 6 query/profile logic. Build adapters/view models around it.

Create:
`docs/evidence/phase9/08_TARGET_GROUP_PREVIEW_REPORT.md`

STOP.
