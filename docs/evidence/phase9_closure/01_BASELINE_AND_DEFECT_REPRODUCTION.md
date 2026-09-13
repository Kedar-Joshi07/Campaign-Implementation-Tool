# Phase 9 Closure Baseline and Defect Reproduction

Generated: 2026-09-12

Prompt: `01_STEP_01_RECONCILE_BASELINE_AND_REPRODUCE_DEFECT.md`

## Decision

`DEFECT_REPRODUCED`

The Phase 9 multi-branch Target Group is stored and consumed correctly by the
campaign/export path, but the legacy Audience Explorer reopen path receives and
applies only the first branch. Presenting that branch as the complete reopened
definition is therefore unsafe.

## Baseline reconciliation

- Branch: `main`
- HEAD: `6934c586780b5f8f5bd57d533b5597ea63dec8cc`
- `origin/main`: `6934c586780b5f8f5bd57d533b5597ea63dec8cc`
- Git status before reproduction: only the supplied
  `Prompts/phase9_closure_interoperability_fix_prompt_pack/` directory was
  untracked; tracked files were clean.
- Frozen Phase 1–8 baseline:
  `d6a9f9b963622a334bf3e5c3220e5d0a73e528fe`
- Schema version: `14`
- Phase 9 contract versions: targeting segment `1`, campaign-targeting context
  `1`, business match strength `1`, age bucket `1`, income group `1`, targeting
  intelligence resolution `1`, target-group preview `1`, saved target group
  `1`, and target-group campaign `1`.
- Preserved Phase 7 contracts: campaign `1`, export `1`, member resolution `1`.

## Latest exact-SHA CI

- Commit: `6934c586780b5f8f5bd57d533b5597ea63dec8cc`
- Workflow: CI run `#9`
- URL: https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool/actions/runs/34617435112
- Result: `SUCCESS`, 5/5 jobs successful, duration 3m06s.
- Jobs: Repository Hygiene, Python Validation, Tests, Clean-Room Phase1-7,
  and Frontend Contract.

## Current Phase 9 browser evidence

- Recorded browser candidate:
  `00e8588b08b15abb1ad7db200d2bc9b88871fd18`
- Controls discovered: `72`
- PASS: `68`
- JUSTIFIED_EXCLUSIVE: `4`
- FAIL: `0`
- NOT_RUN: `0`
- Browser evidence status: `PASS`

The browser candidate predates the two evidence-closure commits. Correcting
stale candidate/summary values is explicitly deferred to Step 5 of this pack.

## Isolated reproduction

The reproduction used the existing bounded Phase 9 fixture in a temporary
database. It did not modify `data/campaign_poc.db`, retrain a production model,
rescore the 5M universe, or rebuild production rank boundaries.

Business criteria:

- Match strength: Broad (`score >= 0.60`)
- Age: `25–34` OR `45–54`
- Income: `<25K` OR `50K–74,999` OR `75K–99,999`
- Marital status: Married OR Single
- Selection: all matching people

Normalization coalesced the two adjacent middle income buckets into
`50,000–99,999`, producing four Cartesian branches:

1. Age 25–34 AND income 0–24,999
2. Age 25–34 AND income 50,000–99,999
3. Age 45–54 AND income 0–24,999
4. Age 45–54 AND income 50,000–99,999

All four branches retained Broad match strength and the Married/Single OR
criterion.

## Reproduction assertions

| Assertion | Result | Evidence |
|---|---|---|
| `phase9_saved_target_groups.filter_branches_json` contains multiple branches | PASS | Isolated Target Group `1` stored 4 branches. |
| `saved_audiences.filters_json` contains only the base/first branch | PASS | The legacy JSON exactly equalled branch 1. |
| Saved Audience detail exposes only the first branch | PASS | `detail.definition.filters` exactly equalled branch 1. |
| Campaign/export resolution uses every branch | PASS | `_resolve_campaign_member_query_context` compiled 4 predicate branches. |
| Union member resolution remains exact | PASS | Campaign `1` resolved `PER_000002` and `PER_000005`, matching the immutable selected count of 2 with no duplicates. |
| Audience Explorer applies only `detail.definition.filters` | PASS | `reopenSavedAudience()` assigns `detail.definition?.filters` and calls `setFilterFormValues(filters, selection)`. |
| Legacy reopen can present an incomplete definition | **DEFECT** | For this group the applied UI definition represents only age 25–34 AND income <25K, silently omitting the other three authoritative branches. |

## Code-path evidence

- `app/services/target_group_campaign_service.py` stores the complete normalized
  branch set and its integrity hash in Phase 9 metadata.
- `app/services/campaign_service.py::_saved_filter_definition` reads and
  validates `filter_branches_json`; campaign member/export resolution builds a
  predicate branch for every authoritative branch.
- `app/services/saved_audience_service.py::get_saved_audience_detail` returns
  the legacy single `filters_json` object under `definition.filters` and does
  not identify the Phase 9 multi-branch limitation.
- `frontend/js/audience-explorer.js::reopenSavedAudience` reads only
  `detail.definition.filters`, populates the legacy form, and submits it as if
  it represented the complete definition.

## Required correction boundary

The complete Phase 9 branch set remains authoritative. Step 2 must either make
legacy reopen faithfully replay the complete set or block/redirect reopening
to the Phase 9 business workflow. It must not collapse the branches into a
broad min/max range and must not silently display branch 1.

## Step result

`STEP_01_COMPLETE_STOP`

Focused bounded revalidation on 2026-09-13:

- `pytest -q tests/test_phase9_save_target_group_campaign.py::test_reopen_restores_immutable_business_context_and_exact_union_members`
- Result: `1 passed in 24.17s`

No application code was modified in Step 1.
