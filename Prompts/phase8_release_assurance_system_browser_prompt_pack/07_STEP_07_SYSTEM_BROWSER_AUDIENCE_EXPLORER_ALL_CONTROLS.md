# Step 7 — System Browser: Audience Explorer Every Control

Use the scoring run created in Step 6.

## Preparation
Exercise scoring-run selector, preparation/refresh controls, preparation status/retry. If unprepared, trigger preparation through UI and observe completion.

Independently verify 100 percentile boundaries and current analytics snapshot.

## Exercise every filter/control

Numeric:
- propensity score min/max
- age min/max
- income min/max
- family member min/max

Ranking:
- top percentile
- decile
- rank bands

Categorical:
- gender
- state
- marital status
- education
- employment status
- resident status
- resident type
- type of employment

Selection:
- ALL_MATCHING
- TOP_N
- target count

Actions:
- Apply
- Reset/Clear
- Search
- Load More/Next
- profile dimension controls
- Save Audience
- saved-audience list/reopen
- Use in Campaign Builder
- refresh/retry

## Required scenarios
1. no filters ALL_MATCHING
2. top 1%
3. top decile
4. demographic filter
5. rank + demographic
6. TOP_N 50K if valid
7. invalid score range
8. invalid age range
9. invalid income range
10. invalid family range
11. invalid TOP_N
12. reset after error

Verify search returns only approved non-PII fields, deterministic order and no duplicate IDs across pages.

Verify profile populations and disclaimers: score is not purchase probability; no identity linking.

Save and reopen a current export-ready audience.

Update every Audience control to PASS/FAIL/JUSTIFIED_EXCLUSIVE.

Create `docs/evidence/phase8/07_SYSTEM_BROWSER_AUDIENCE_REPORT.md`.

STOP.
