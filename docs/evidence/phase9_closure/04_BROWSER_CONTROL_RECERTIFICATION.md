# Phase 9 Closure Real System-Browser Control Recertification

Generated: 2026-09-13

Prompt: 04_STEP_04_REAL_SYSTEM_BROWSER_CONTROL_RECERTIFICATION.md

## Decision

PASS

The required reachable Phase 9 controls and the Step 2 multi-branch safe-block
path were exercised sequentially in installed Google Chrome against the real
application. The authoritative Phase 9 control ledger has no failed, not-run,
unjustified-exclusive, or invalid entries.

## Browser and source

- Browser: installed Google Chrome through the system browser-control session
- Application: http://127.0.0.1:8000/
- Main control scenario database: data/campaign_poc.db
- Reused source: existing READY scoring run 2
- Source behavior: initially Not available for a new context, then Up to date
  only after explicit linkage to scoring run 2
- Import run: not performed
- Model training: not performed
- Prospect scoring: not performed
- 5M rank preparation: not performed

The new browser context was explicitly linked to the existing READY source.
The application did not silently select a latest source. The only 5M work was
read-only exact preview querying over existing scores and demographics.

## Required real-browser control proof

| Selector | Browser action | Visible UI/state change | Normalized criteria effect | Exact preview/result effect | Result |
|---|---|---|---|---|---|
| input[name='match_strength'][value='VERY_STRONG'] | Selected the radio in Chrome | Radio checked; chip changed to Very Strong Match - 0.90+ | match_strength=VERY_STRONG | 4 selected; average 0.941; score range 0.900-0.985; Very Strong comparison count 4 | PASS |
| #planner-targeting-marital-statuses | Selected Married | Count became 1 selected; Married chip appeared | marital_statuses=[Married] | Explanation listed Married; Marital Status Mix was Married 4 (100%) | PASS |
| #planner-targeting-employment-statuses | Selected Employed full-time | Count became 1 selected; matching chip appeared | employment_statuses=[Employed full-time] | Employment Status Mix was Employed full-time 4 (100%) | PASS |
| #planner-targeting-resident-statuses | Selected Citizen by birth | Count became 1 selected; matching chip appeared | resident_statuses=[Citizen by birth] | Resident Status Mix was Citizen by birth 4 (100%) | PASS |
| #planner-targeting-resident-types | Selected Urban core | Count became 1 selected; matching chip appeared | resident_types=[Urban core] | Resident Type Mix was Urban core 4 (100%) | PASS |
| #planner-targeting-employment-types | Selected Private sector | Count became 1 selected; matching chip appeared | employment_types=[Private sector] | Employment Type Mix was Private sector 4 (100%) | PASS |
| #planner-targeting-top-percent | Entered 10 | Top matching percentage: 10% chip appeared | top_matching_percent=10 | Explanation explicitly listed top matching 10%; selected count remained the exact 4-person intersection | PASS |
| #planner-targeting-clear-all | Clicked Clear all | All five advanced counters became 0 selected; top percentage became empty; announcement confirmed clearing | Advanced arrays empty; top_matching_percent=null; default match_strength=GOOD and selection_mode=ALL_MATCHING retained | No stale optional choice remained visible | PASS |
| #planner-back-5 | Clicked Back from Review & Save | Returned to Target Group Preview; retained-entry announcement shown | Saved criteria unchanged | Exact selected count 4 remained visible | PASS |

## Exact preview proof

The exercised advanced-criteria scenario displayed:

- Potential Customers Available: 5,000,000
- Matching Your Preferences: 4
- Selected for Target Group: 4
- Average Targeting Match Score: 0.941
- Strongest Match: 0.985
- Lowest Selected Match: 0.900
- Very Strong / Strong / Good / Broad comparison counts: 4 / 18 / 72 / 425
- No contact PII in the preview

The browser explanation named all selected criteria and stated the non-causal
score semantics.

## Multi-branch interoperability browser proof

The safe-block path was exercised in Chrome using a deterministic six-person
fixture created from the established Phase 9 test data. Its Saved Target Group
had four authoritative branches, selected exactly two members, and used the
same application routes and frontend/backend implementation as the main
scenario.

### Detail and blocked reopen

- Saved Target Group: Closure Multi Branch Browser Group
- Authoritative branches: 4
- Stored resolved count: 2
- Browser detail: CURRENT, 2 selected, All matching
- #saved-audience-reopen: disabled
- Required guidance: visible verbatim
- Browser click attempt on Reopen definition: accepted no legacy form change

Before and after the click attempt, the following legacy form state was
identical:

- age minimum: empty
- age maximum: empty
- income minimum: empty
- income maximum: empty
- marital selections: empty

Therefore branch 1 was not loaded or presented as the full definition.

### Redirect controls

| Selector | Browser action | Result | Status |
|---|---|---|---|
| #saved-audience-phase9-reopen-guidance [data-view-target='saved-target-groups'] | Clicked Open Saved Target Groups | URL changed to #saved-target-groups and the Saved Target Groups view was visible | PASS |
| #saved-audience-phase9-reopen-guidance [data-view-target='campaign-planner'] | Clicked Open Campaign Planner | URL changed to #campaign-planner and the Create Campaign view was visible | PASS |

## Live defect found and corrected

The first Chrome detail request exposed HTTP 500. The service returned the new
interoperability metadata, but SavedAudienceDetailResponse had not declared
those fields, so response validation rejected the live API payload.

Correction:

- Added is_phase9_target_group to SavedAudienceDetailResponse.
- Added filter_branch_count with a positive-integer-or-null contract.
- Added can_reopen_in_legacy_audience_explorer.
- Added reopen_guidance.
- Extended the multi-branch regression to assert the real API response, safe
  capability, exact guidance, and absence of contact PII.

Focused regression after correction:

pytest -q tests/test_phase9_save_target_group_campaign.py::test_phase9_multi_branch_saved_target_group_interoperability_preserves_exact_union tests/test_saved_audience_service.py::test_legacy_audience_reopen_preserves_detail_filters_and_selection_exactly tests/test_frontend.py::test_phase9_multi_branch_saved_target_group_interoperability_blocks_legacy_form_population

Result: 3 passed in 12.85s

The identical Chrome detail action then returned successfully and displayed
the safe-block UI.

## Authoritative control ledger

Ledger:
docs/evidence/phase9/final_system_browser/ui_control_coverage.json

Validation command:

python scripts/validation/browser/check_ui_control_coverage.py --inventory docs/evidence/phase9/final_system_browser/ui_control_coverage.json

Validated counts:

- Controls: 75
- PASS: 71
- JUSTIFIED_EXCLUSIVE: 4
- FAIL: 0
- NOT_RUN: 0
- UNJUSTIFIED_EXCLUSIVE: 0
- INVALID_STATUS: 0
- Errors: 0
- Gate: PASS

The four exclusions remain the previously documented mutually exclusive error
or retry states. Each retains an individual group and justification; no generic
exception category was introduced.

## Files changed by Step 4

- app/schemas/audience.py
- tests/test_phase9_save_target_group_campaign.py
- docs/evidence/phase9/final_system_browser/ui_control_coverage.json
- docs/evidence/phase9_closure/04_BROWSER_CONTROL_RECERTIFICATION.md

## Step result

STEP_04_COMPLETE_STOP

Step 5 was not started.
