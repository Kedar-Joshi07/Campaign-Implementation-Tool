# Step 7 — Audience Explorer UI

Use HEAD from successful Step 6. Do not implement Campaign Builder/export.

## Objective

Enable currently disabled Audience Explorer navigation and build a complete Phase 6 UI using existing HTML/CSS/Vanilla JS. Campaigns remains disabled.

Prefer new `frontend/js/audience-explorer.js`; extend shared API helpers only where appropriate. No React/Vue/build tooling.

## Required UI states

1. loading eligible score runs;
2. no current canonical run;
3. rank preparation missing;
4. preparation queued/running;
5. preparation failed/retry;
6. explorer ready;
7. search loading;
8. empty filtered result;
9. backend error/retry;
10. audience save success/error.

## Header/context

Show model/scoring IDs, BAGGING_PU, prospect universe count, score semantics, and verified current-source indicator. Keep technical checksums/path details out of normal business UI.

## Preparation UX

When boundaries are absent show `Prepare Audience Explorer`. POST preparation, poll status, display stage/progress, disable duplicates, surface 409 global-compute conflicts. Do not start a hidden long job automatically.

## Filters

Ranking:
- score min/max
- Top percentile
- decile multi-select
- rank band multi-select

Numeric:
- age min/max
- income min/max
- family member count min/max

Categorical:
- gender
- state
- marital status
- education
- employment status
- resident status
- resident type
- type of employment

Populate from `/api/audience/options`. Provide Apply, Reset, clear chips, active-filter summary. No PII filters.

## Selection

Allow `All matching prospects` and `Top N matching prospects` only. Show matching count, selected count, current average score from estimate. No individual checkbox member selection.

## Ranked prospect table

Columns:
Score, Rank band, Percentile, Decile, Person ID, Age, Gender, State, Income, Marital status, Education, Employment, Resident status, Resident type, Family size, Employment type.

No names/email/phone/address/city/postal/ethnicity/religion.

Use cursor-based Load more/Next.

## Profile

Show selected audience KPIs and distributions, selected vs universe, and selected vs historical known positives.

Mandatory text:
`Aggregate demographic comparison only. No prospect is matched to a historical customer.`

Use accessible HTML/CSS bars/cards; no new chart library required.

## Rank/score semantics

Clearly state:
- Percentile 1 = top 1%.
- Decile 1 = top 10%.
- Propensity score is relative model affinity, not purchase probability.

Never show `86% chance to buy`.

## Save audience

Name required, description optional, show selection summary/count/filters, save via API, then refresh Saved Audiences.

## Saved Audiences

List name, created, count, mode, current/stale. Reopen definition into explorer and show saved profile snapshot. Stale definitions are read-only historical context until current inputs are explicitly resolved.

No campaign creation/export control. A disabled `Use in Campaign — Phase 7` hint is acceptable.

## Accessibility/tests

Maintain semantic labels, focus management, aria-live, keyboard controls, visible errors, no color-only status.

Frontend contract tests must prove Audience Explorer enabled, Campaigns disabled, allowed fields only, forbidden PII absent, preparation/filter/profile/save states, disclaimers, and no export/activation.

Run full regression.

STOP.
