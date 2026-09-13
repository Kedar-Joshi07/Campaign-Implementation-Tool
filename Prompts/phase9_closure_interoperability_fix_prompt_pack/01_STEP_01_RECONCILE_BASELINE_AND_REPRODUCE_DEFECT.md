# Step 1 — Reconcile Baseline & Reproduce the Defect

Start from `6934c586780b5f8f5bd57d533b5597ea63dec8cc`.

## Objective
Prove the exact defect before modifying code.

Record:
- HEAD / branch / remote main
- git status
- schema version
- current Phase 9 contract versions
- latest exact-SHA CI
- current Phase 9 browser candidate/control totals

Create or reuse a Phase 9 Target Group whose business criteria produce multiple filter branches, e.g.:
- Age: 25–34 OR 45–54
- Income: <25K OR 50K–74,999 OR 75K–99,999

Verify:
1. `phase9_saved_target_groups.filter_branches_json` contains multiple branches.
2. `saved_audiences.filters_json` contains only the base/first branch.
3. Campaign/export resolution uses all branches.
4. Audience Explorer `Reopen definition` reads only `detail.definition.filters`.
5. Reopening therefore risks presenting an incomplete definition.

If the defect cannot be reproduced, STOP and document why.

Create:
`docs/evidence/phase9_closure/01_BASELINE_AND_DEFECT_REPRODUCTION.md`

STOP.
