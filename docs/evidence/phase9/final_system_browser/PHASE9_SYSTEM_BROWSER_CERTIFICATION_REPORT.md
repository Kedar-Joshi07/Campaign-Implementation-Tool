# Phase 9 System-Browser Certification Report

Generated at: 2026-09-11T04:15:00Z

Prompt: `Prompts/phase9_business_friendly_campaign_targeting_prompt_pack/14_STEP_14_SYSTEM_BROWSER_END_TO_END_PHASE9_CERTIFICATION.md`

Candidate SHA: `d78ad1fb8347060d033b8b7a49902610ca676a53`

Branch: `main`

## Decision

**PASS — Step 14 is complete locally.** The Phase 9 business workflow passed in the installed Google Chrome browser, all required alternate states were exercised, independent backend assertions passed, and the actionable-control gate has `NOT_RUN=0`, `FAIL=0`, and no unjustified exclusions. This report does not execute or claim Step 15.

## Clean-start gate

- The candidate was committed and `git status --short` was empty before certification.
- Installed system browser: Google Chrome `152.0.7977.83` at `C:\Program Files\Google\Chrome\Application\chrome.exe`.
- Runtime database: `data/campaign_poc.db`, schema version 14.
- Verified source: analysis run `#1`, model run `#2`, scoring run `#2`, selected candidate `BAGGING_PU`.
- A new general source was required because the frozen Phase 8 source carried campaign/product scope and could not honestly be used as general Phase 9 targeting intelligence.

## Source preparation

- Model run `#2`, `Phase9 Certification General Source`: completed in 78 seconds.
- Scoring run `#2`: 5,000,000/5,000,000 people, 200 chunks of 25,000, completed in 835.410 seconds at 5,985.086 rows/second.
- Audience-rank preparation job `#7`: completed in 490 seconds with 100 rank boundaries and one current analytics snapshot.
- Artifact SHA-256: `cd50dc7a39bf1288478072f01d98216a4fb64187a8085c2752ad637fa82f01f6`.
- Feature-contract SHA-256: `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`.
- Current import checksums were restored and independently verified after the stale-source simulation.

## Main business-user scenario

The 27 required actions passed in Chrome:

1. Opened Create Campaign and entered name, description, and launch date.
2. Selected products `PRD001` and `PRD002`.
3. Selected Cross-sell and Retention types, Cross-sell Promotion and Retention Offer categories, Bundle Offer and Percent Discount offers, Email delivery, and Email/Paid Social historical context.
4. Continued through the default business UI without required ML identifiers or model terminology.
5. Used targeting strength and multi-select Gender, Age Groups, States, and Income Groups controls.
6. Opened More targeting options and selected Education as an advanced demographic criterion.
7. Reviewed exact target-group KPIs, all four strength comparisons, demographic mix, privacy-safe people, and the business explanation under Why these people?.
8. Applied the displayed guidance by explicitly changing the strength radio to Broad. The UI correctly did not silently broaden the criteria.
9. Paginated the privacy-safe preview from 25 to 50 unique people.
10. Opened View technical details and verified the explicitly linked analysis/model/scoring identifiers and hashes.
11. Saved immutable Target Group `#2`, created Campaign Draft `#3`, reopened it from Campaigns, and refreshed the page successfully.
12. Navigated to Overview, Data Status, Historical Analysis, Model Training & Prospect Scoring, Audience Explorer, and Campaigns; each existing Phase 1–8 page rendered its functional ready/loading workspace without an application error.

### Certified campaign context

- Campaign: `Phase 9 Business Certification 2026-09-11`
- Description: `Multi-product retention and growth campaign for priority markets.`
- Planned launch: `2026-10-15`
- Delivery channel: `EMAIL`
- Campaign-context ID: `1`
- Campaign-context SHA-256: `ce7a3c7e36af62099d6af723444ada72b0eedc0fda1712631fbde5e91001446a`

### Certified Broad criteria and results

- Strength: Broad (`score >= 0.60`)
- Genders: Female, Male, Non-binary/Other
- Age groups: all seven Phase 9 buckets
- States: all 27 available states
- Income groups: all seven Phase 9 buckets
- Advanced criterion: all eight available education categories
- Selection: all matching people
- Targeting-criteria SHA-256: `a687aea89b5b1df9705bbbc2c4a0037d3b76cccabf30deaa0f6b4d842bef46fe`
- Filter-branches SHA-256: `3afb1b093844366ad07b8db39b62410269dcdf27a231fc5e300fd5e43956c9bd`
- Available: 5,000,000
- Matching/selected: 2,248
- Average/maximum/lowest selected score: 0.662 / 0.987 / 0.600
- Exact comparison: Very Strong 30, Strong 130, Good 457, Broad 2,248
- Saved Target Group: `Phase 9 Priority Market Target Group (#2)`
- Campaign Draft: `Phase 9 Business Certification 2026-09-11 (#3)`, status `DRAFT`

## Alternate and error scenarios

| Scenario | Result | Evidence |
|---|---|---|
| No targeting intelligence | PASS | Before explicit source linkage the preview showed Not available, no count was fabricated, and Review & Save was blocked. |
| Stale targeting intelligence | PASS | A controlled demographic checksum mismatch changed the source state to Needs refresh, hid exact results, and disabled Review & Save. The original checksum was immediately restored; Check again returned Up to date and exact results. |
| Zero matching people | PASS | Restrictive Strong criteria produced an exact zero state with business guidance to broaden preferences. |
| Invalid target count | PASS | TOP_N without a positive integer showed “Enter a whole number greater than zero” and focused Number of People. |
| Conflicting preferences | PASS | Family minimum 5 / maximum 2 showed “Maximum family size must be at least the minimum family size” and focused the maximum field. |
| Retryable backend error | PASS | The initial process-pool training job `#4` failed with a local permission condition; inputs were retained, the runtime was restarted with the required authority, and job `#5` completed. A later retained-input targeting-save retry also returned HTTP 200 and recovered. |
| Back/Next preservation | PASS | Campaign context and targeting selections remained intact after Back/Next navigation. |
| Refresh/reopen | PASS | Campaign `#3` reopened with Target Group `#2`, 2,248 people, Email, DRAFT, and CURRENT; the same values remained after browser refresh. |
| Changed criteria creates a new immutable group | PASS | Good criteria produced Target Group `#3` (457 people) and Campaign `#4`; Target Group `#2` remained 2,248. The focused same-context immutability regression also passed. |

The stale simulation modified only the current import checksum long enough to observe the UI gate. It was restored to `e12fa5f54606aee0e6704db418f2054df29f4e1b8827d82ed2ce7897b7693e75` before certification assertions.

## Privacy and progressive disclosure

- Planning and preview displayed opaque Potential Customer IDs and approved score/demographic fields only.
- Preview columns were Potential Customer ID, Targeting Match Score, Top Matching %, Match Strength, Age, Gender, State, and Individual Yearly Income.
- Name, email, phone, street, city, postal code, and customer-master identifiers were absent from planning and preview.
- Model/scoring IDs, feature/artifact hashes, checksums, and contract versions remained behind explicit View technical details disclosures.
- The score explanation explicitly stated that similarity scores do not establish causation or guarantee purchase/response.

## Independent backend assertions

`python scripts/validation/phase9_step14_backend_assertions.py` passed in 8.602 seconds on the final run.

- Context JSON and criteria JSON independently canonicalized to their recorded SHA-256 values.
- Both sources resolved `READY`, explicitly linked, previewable, and pinned to scoring run `#2`.
- Independent score-table counts reconciled to 2,248 Broad and 457 Good selections from a 5,000,000-person universe.
- Target Groups `#2` and `#3` retained distinct criteria/filter hashes and immutable snapshot metadata.
- Campaigns `#3` and `#4` linked to the correct saved Target Group, targeting context, resolved count, scoring/model/analysis lineage, and DRAFT status.
- Two independent 25-row samples contained no contact-PII keys and no duplicate Potential Customer IDs.
- The frozen Phase 7 campaign/export/member-resolution contract versions remain `1`; Email and Direct Mail profile mappings and column contracts are unchanged.
- `pytest -q tests/test_phase9_save_target_group_campaign.py::test_changed_criteria_creates_new_group_without_mutating_previous_group`: `1 passed in 84.96s`.
- Pre-candidate Phase 9 regression: `58 passed, 488 deselected in 288.46s`.

## Actionable-control gate

- PASS: 61
- JUSTIFIED_EXCLUSIVE: 3
- FAIL: 0
- NOT_RUN: 0
- UNJUSTIFIED_EXCLUSIVE: 0
- INVALID_STATUS: 0

The three justified exclusions are controls that exist only in mutually exclusive campaign-context-load, targeting-options-load, or preview-error states. Every exclusion has an individual reason in `ui_control_coverage.json`; there is no generic exception bucket.

## Browser telemetry

- Unexplained console errors: 0
- Unexplained JavaScript exceptions: 0
- Unexplained critical network failures: 0
- Explained infrastructure messages: 6 Chrome automation-extension message-channel closure messages during tab reconnection/navigation. They originated from the browser extension, not application JavaScript; the associated application API requests completed successfully and the visible states were verified after each action.
- Expected negative-path responses: one deliberately malformed audience-preparation request returned HTTP 422 before the corrected request; failed training job `#4` represented the certified retryable backend path. Neither was an unexplained production failure.

## Timings

- Governed model training: 78 seconds
- Full 5M scoring: 835.410 seconds
- Audience-rank preparation: 490 seconds
- Main/alternate browser workflow window: approximately 2,320 seconds from first captured planner action to final advanced-page navigation
- Independent focused backend assertions: 8.602 seconds
- Same-context immutability regression: 84.96 seconds

## Evidence files

- `docs/evidence/phase9/final_system_browser/PHASE9_SYSTEM_BROWSER_CERTIFICATION_REPORT.md`
- `docs/evidence/phase9/final_system_browser/phase9_certification_manifest.json`
- `docs/evidence/phase9/final_system_browser/ui_control_coverage.json`
- `scripts/validation/phase9_step14_backend_assertions.py`

## Final local decision

`PASS_STEP14_COMPLETE`

Stop after Step 14. Step 15 has not been started.
