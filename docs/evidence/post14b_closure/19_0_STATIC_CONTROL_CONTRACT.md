# Phase 8 UI Control Coverage Contract

Generated at: 2026-10-12T19:14:10Z

## Contract Rules
- Allowed statuses: `NOT_RUN`, `PASS`, `FAIL`, `JUSTIFIED_EXCLUSIVE`.
- Terminal statuses allowed for certification: `PASS`, `FAIL`, `JUSTIFIED_EXCLUSIVE`.
- Generic `EXCEPTION` is forbidden.
- `JUSTIFIED_EXCLUSIVE` requires both `mutually_exclusive_group` and `justification`.
- Coverage gate fails if any control is `NOT_RUN`.
- Coverage gate fails if any control is `FAIL`.
- Coverage gate fails if any `JUSTIFIED_EXCLUSIVE` is unjustified.

## Discovery Summary
- Total controls: 197

By page:
- audience-explorer: 40
- campaign-planner: 64
- campaigns: 25
- data-status: 2
- global: 8
- historical-analysis: 25
- insights: 2
- model-training: 11
- overview: 6
- result-detail: 8
- results: 3
- saved-target-groups: 3

By type:
- a: 4
- button: 103
- dynamic:button: 4
- input:checkbox: 3
- input:date: 5
- input:file: 1
- input:number: 20
- input:radio: 5
- input:text: 9
- select: 40
- textarea: 3

## Checker
Run:
- `python scripts/validation/browser/check_ui_control_coverage.py --inventory docs/evidence/phase8/ui_control_inventory.json`

Expected current state after Step 4:
- Inventory is intentionally initialized with `NOT_RUN` status for all controls.
- Gate should fail until execution steps update statuses to terminal values.