# Phase 9 Closure Interoperability Regression Test Report

Generated: 2026-09-13

Prompt: 03_STEP_03_ADD_INTEROPERABILITY_REGRESSION_TESTS.md

## Result

PASS

Explicit regression coverage now protects legacy single-branch Audience
Explorer reopen behavior, Phase 9 single-branch compatibility, Phase 9
multi-branch fail-closed interoperability, and exact campaign/export member
resolution.

## Requirement-to-test mapping

| Requirement | Explicit test | Assertion |
|---|---|---|
| Legacy detail compatibility and exact filter/selection restore | test_legacy_audience_reopen_preserves_detail_filters_and_selection_exactly | Non-Phase-9 metadata remains compatible, legacy reopen remains enabled, and detail/replay filters and selection match exactly. |
| Phase 9 single-branch detection and reopen | test_saved_target_group_interoperability_phase9_single_branch_reopens_in_legacy_explorer | Phase 9 is detected with one branch, legacy reopen remains enabled, and the stored authoritative branch equals the replayed filters. |
| Phase 9 multi-branch count, SHA, PII boundary, and exact union | test_phase9_multi_branch_saved_target_group_interoperability_preserves_exact_union | Branch count is greater than one, canonical SHA-256 matches storage, detail is PII-free, reopen is blocked, and members are exactly PER_000002 and PER_000005 with no duplicates. |
| Multi-branch Audience Explorer fail-closed behavior | test_phase9_multi_branch_saved_target_group_interoperability_blocks_legacy_form_population | Required guidance and redirects exist; the capability guard returns before filters are read or setFilterFormValues can populate the form. |
| Previous Target Group immutability | test_saved_target_group_interoperability_keeps_previous_group_immutable_after_criteria_change | Saving revised criteria creates a new group and leaves the earlier metadata row byte-for-byte unchanged. |
| Stale source blocks a new save | test_saved_target_group_interoperability_stale_source_blocks_new_save | Reopen reports NEEDS_REFRESH and a subsequent API save returns HTTP 409 without extra records. |
| Idempotent replay and retry | test_saved_target_group_interoperability_idempotent_retry_reuses_group | Repeat save reuses the same group/campaign, and a retry after injected draft creation failure reuses the preserved group without duplicates. |

## Multi-branch exact-membership result

- Authoritative filter branches: 4
- Stored branch SHA: validated against canonical branch JSON
- Expected selected person IDs: PER_000002, PER_000005
- Actual selected person IDs: PER_000002, PER_000005
- Duplicate IDs: 0
- Actual member count: 2
- Stored resolved count: 2
- Legacy Audience Explorer reopen: blocked with the required guidance

The same campaign member resolver used by finalized target-list export consumes
the authoritative full Phase 9 branch set. The regression enumerates its
selected-member chunks with the email contact export profile and verifies the
exact union before any export serialization.

## Focused verification

Command:

pytest -q tests/test_saved_audience_service.py::test_legacy_audience_reopen_preserves_detail_filters_and_selection_exactly tests/test_phase9_save_target_group_campaign.py::test_phase9_multi_branch_saved_target_group_interoperability_preserves_exact_union tests/test_phase9_save_target_group_campaign.py::test_saved_target_group_interoperability_phase9_single_branch_reopens_in_legacy_explorer tests/test_phase9_save_target_group_campaign.py::test_saved_target_group_interoperability_keeps_previous_group_immutable_after_criteria_change tests/test_phase9_save_target_group_campaign.py::test_saved_target_group_interoperability_stale_source_blocks_new_save tests/test_phase9_save_target_group_campaign.py::test_saved_target_group_interoperability_idempotent_retry_reuses_group tests/test_frontend.py::test_phase9_multi_branch_saved_target_group_interoperability_blocks_legacy_form_population

Result: 7 passed in 83.68s

## Modified-module regression

Command:

pytest -q tests/test_saved_audience_service.py tests/test_phase9_save_target_group_campaign.py tests/test_frontend.py

Result: 57 passed in 180.81s

Additional checks:

- Python compileall: PASS
- git diff --check: PASS, with only expected CRLF-to-LF notices
- Required test-name tokens phase9_multi_branch, legacy_audience_reopen, and saved_target_group_interoperability: PRESENT

## Scope controls

- No production data was changed.
- No import was run.
- No training was run.
- No scoring was run.
- No 5M-data preparation or scan was run.
- No Step 4 browser recertification was started.

## Files changed by Step 3

- tests/test_saved_audience_service.py
- tests/test_phase9_save_target_group_campaign.py
- tests/test_frontend.py
- docs/evidence/phase9_closure/03_INTEROPERABILITY_TEST_REPORT.md

## Step result

STEP_03_COMPLETE_STOP

Step 4 was not started.

## Closure follow-up regression

The post-freeze evidence-integrity audit added
`test_saved_target_group_interoperability_unreadable_branch_metadata_fails_closed`.
It verifies that valid JSON with an invalid non-list branch shape fails closed
at both service and API boundaries, omits no required safety capability or
guidance, and exposes no contact PII. Malformed JSON is independently rejected
by the database `json_valid` constraint.

- Expanded focused interoperability matrix: 8 passed in 40.77s.
- Full regression after the addition: 558 passed in 436.84s.
