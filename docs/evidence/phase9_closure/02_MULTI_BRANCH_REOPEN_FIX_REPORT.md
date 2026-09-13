# Phase 9 Multi-Branch Reopen Interoperability Fix

Generated: 2026-09-13

Prompt: 02_STEP_02_FIX_MULTI_BRANCH_REOPEN_INTEROPERABILITY.md

## Decision

PASS_OPTION_B_SAFE_BLOCK_REDIRECT

Legacy Audience Explorer cannot faithfully represent disjoint OR branches in
its single filter form. The implementation therefore uses the prompt's Option B:
safe block and redirect. It never flattens ranges and never populates the
legacy form from branch 1 for a multi-branch Phase 9 Target Group.

## Backend response metadata

get_saved_audience_detail now returns:

- is_phase9_target_group
- filter_branch_count
- can_reopen_in_legacy_audience_explorer
- reopen_guidance

The service detects Phase 9 metadata from
phase9_saved_target_groups.filter_branches_json. Non-Phase-9 audiences and
single-branch Phase 9 groups remain legacy-reopenable. Multi-branch groups are
not. If Phase 9 branch metadata is unreadable, the service fails closed for
legacy reopening.

The API exposes no branch JSON, database table details, or additional PII.

## Audience Explorer behavior

When a selected Saved Audience is a Phase 9 multi-branch Target Group:

- Reopen definition is disabled.
- A visible note displays:
  “This Target Group was created in Campaign Planner and contains multiple
  targeting branches. Reopen it from Saved Target Groups / Campaign Planner to
  preserve the exact definition.”
- Open Saved Target Groups and Open Campaign Planner navigation actions are
  offered.
- The reopen handler independently checks the capability flag before reading
  detail.definition.filters; direct/programmatic invocation therefore cannot
  populate the legacy form from branch 1.

The navigation actions use the application's existing governed view routing.

## Compatibility checks

| Case | Phase 9 | Branches | Legacy reopen |
|---|---:|---:|---|
| Existing legacy Saved Audience 1 | No | 1 | Enabled |
| Existing single-branch Phase 9 Target Group 2 | Yes | 1 | Enabled |
| Isolated multi-branch Phase 9 Target Group | Yes | 4 | Disabled with required guidance |

The isolated multi-branch response returned:

- is_phase9_target_group=true
- filter_branch_count=4
- can_reopen_in_legacy_audience_explorer=false
- the exact required plain-language guidance

## Focused verification

Command:

pytest -q tests/test_saved_audience_service.py tests/test_saved_audience_api.py tests/test_frontend.py tests/test_phase9_save_target_group_campaign.py::test_reopen_restores_immutable_business_context_and_exact_union_members

Result: 54 passed in 92.52s

Additional checks:

- Python compileall: PASS
- git diff --check: PASS, with only expected CRLF-to-LF notices
- Direct legacy/single-branch/multi-branch response inspection: PASS

## Preserved contracts

- Campaign/export member resolution is unchanged and still consumes the
  authoritative full Phase 9 branch set.
- Saved Audience and Saved Target Group records remain immutable.
- Phase 9 metadata and hashes are unchanged.
- Currentness behavior is unchanged.
- Planning/preview and export PII boundaries are unchanged.
- Phase 1–8 legacy single-branch behavior is unchanged.

## Files changed

- app/services/saved_audience_service.py
- frontend/index.html
- frontend/js/audience-explorer.js
- docs/evidence/phase9_closure/02_MULTI_BRANCH_REOPEN_FIX_REPORT.md

## Step result

STEP_02_COMPLETE_STOP

Step 3 regression-test implementation was not started.
