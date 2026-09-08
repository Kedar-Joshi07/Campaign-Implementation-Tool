# Phase 8 UI Control Coverage Contract

Generated at: 2026-09-08T10:14:43Z

## Contract Rules
- Allowed statuses: `NOT_RUN`, `PASS`, `FAIL`, `JUSTIFIED_EXCLUSIVE`.
- Terminal statuses allowed for certification: `PASS`, `FAIL`, `JUSTIFIED_EXCLUSIVE`.
- Generic `EXCEPTION` is forbidden.
- `JUSTIFIED_EXCLUSIVE` requires both `mutually_exclusive_group` and `justification`.
- Coverage gate fails if any control is `NOT_RUN`.
- Coverage gate fails if any control is `FAIL`.
- Coverage gate fails if any `JUSTIFIED_EXCLUSIVE` is unjustified.

## Discovery Summary
- Total controls: 111

By page:
- audience-explorer: 38
- campaigns: 25
- data-status: 2
- global: 7
- historical-analysis: 25
- model-training: 11
- overview: 3

By type:
- button: 60
- dynamic:button: 4
- input:checkbox: 3
- input:date: 3
- input:number: 12
- input:radio: 3
- input:text: 6
- select: 20

## Checker
Run:
- `python scripts/validation/browser/check_ui_control_coverage.py --inventory docs/evidence/phase8/ui_control_inventory.json`

Expected current state after Step 4:
- Inventory is intentionally initialized with `NOT_RUN` status for all controls.
- Gate should fail until execution steps update statuses to terminal values.