# Phase 8 Step 7 System Browser Audience Explorer Report

Generated at: 2026-09-08T14:31:15Z

## Scope
- Prompt executed: Prompts/phase8_release_assurance_system_browser_prompt_pack/07_STEP_07_SYSTEM_BROWSER_AUDIENCE_EXPLORER_ALL_CONTROLS.md
- Execution path: system-browser UI controls for preparation, filtering, profile, saved audience, and campaign handoff.

## Browser
- name: system_chrome
- executable: C:\Program Files\Google\Chrome\Application\chrome.exe
- version: 152.0.7977.82
- mode: headless

## Preparation
- Active scoring run: 1
- Source badge: Current source verified
- Prep submit clicked: False
- Prep retry clicked: False
- Prep running messages observed: 0

## Required Scenarios
- 1_no_filters_all_matching: matching=5000000, selected=5000000, rows_rendered=50
- 2_top_1_percent: matching=50000, selected=50000, rows_rendered=50
- 3_top_decile: matching=500000, selected=500000, rows_rendered=50
- 4_demographic_filter: matching=67943, selected=67943, rows_rendered=50
- 5_rank_plus_demographic: matching=1658, selected=1658, rows_rendered=50
- 6_top_n_50k: matching=5000000, selected=50000, rows_rendered=50
- 7_invalid_score_range: Score min cannot exceed score max.
- 8_invalid_age_range: Age min cannot exceed age max.
- 9_invalid_income_range: Income min cannot exceed income max.
- 10_invalid_family_range: Family member count min cannot exceed max.
- 11_invalid_top_n: Top N target count must be a positive whole number.
- 12_reset_after_error: form_error_cleared=True

## Backend Assertions
- Search determinism/no-duplicates: checked_pages=5, unique_person_ids=200
- Boundaries: count=100, p1_rank=50000, p10_rank=500000, p100_rank=5000000, population=5000000
- Analytics snapshot: prepared=True, is_canonical=True, source_verified=True, created_at=2026-09-08T12:57:24Z

## Saved Audience and Handoff
- Saved audience id: 1
- Saved audience name: Phase8 Step7 Current Audience 1788879374
- Currentness badge: CURRENT - usable in Campaign Builder
- Campaign handoff hash after click: #campaigns
- Stale saved definition exercised: False

## Profile and Disclaimer Checks
- Context disclaimer entries: 4
- Profile no-identity-linking disclaimer: Aggregate demographic comparison only. No prospect is matched to a historical customer.

## UI Error Telemetry
- Console errors: 0
- Page errors: 0
- Request failures: 0

## Audience Control Inventory
- Audience controls PASS: 35
- Audience controls FAIL: 0
- Audience controls JUSTIFIED_EXCLUSIVE: 3
- Audience controls NOT_RUN: 0
- Controls updated this step: 38

## Outcome
- Step 7 completed with preparation handling, all required audience scenarios, deterministic pagination and allowlist assertions, profile/disclaimer validation, saved-audience reopen, and Campaign Builder handoff checks.