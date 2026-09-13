# Step 2 — Fix Multi-Branch Audience Explorer Reopen

## Objective
Prevent legacy Audience Explorer from misrepresenting Phase 9 multi-branch Target Groups.

## Preferred resolution order

### Option A — Full branch-aware replay
Use only if Audience Explorer can faithfully represent the entire OR-branch definition.

Requirements:
- detect Phase 9 metadata
- load/verify full branch JSON and SHA
- surface all branches
- preserve exact OR semantics
- never flatten disjoint ranges

### Option B — Safe block/redirect
Use this if full faithful replay is not cleanly representable in the legacy form.

Requirements:
- detect Phase 9 multi-branch Target Group
- intercept/disable `Reopen definition`
- show plain-language message:
  “This Target Group was created in Campaign Planner and contains multiple targeting branches. Reopen it from Saved Target Groups / Campaign Planner to preserve the exact definition.”
- offer navigation back to Saved Target Groups / Campaign Planner
- do not populate the legacy form from branch #1
- leave legacy single-branch audiences unchanged

## Suggested response metadata
Add fields such as:
- `is_phase9_target_group`
- `filter_branch_count`
- `can_reopen_in_legacy_audience_explorer`
- `reopen_guidance`

Do not expose unnecessary internal DB details.

## Preserve
- campaign/export exact membership
- Saved Audience immutability
- Phase 9 saved metadata
- currentness behavior
- privacy boundary

Create:
`docs/evidence/phase9_closure/02_MULTI_BRANCH_REOPEN_FIX_REPORT.md`

STOP.
