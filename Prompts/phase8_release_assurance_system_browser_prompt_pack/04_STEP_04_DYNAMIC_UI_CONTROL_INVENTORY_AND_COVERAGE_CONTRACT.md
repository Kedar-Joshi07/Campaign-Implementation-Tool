# Step 4 — Dynamic UI Control Inventory & Coverage Contract

Dynamically discover all application views and all reachable actionable elements from rendered DOM plus frontend source.

Inventory buttons, links, inputs, selects, multi-selects, checkboxes, radios, tabs, pagination, refresh/reset/retry, save/reopen, train/score/prepare, next/back, draft/finalize/export and dynamic controls.

Create `docs/evidence/phase8/ui_control_inventory.json`.

Each item:
page, selector/test-id, label, type, enable conditions, mutually-exclusive group, expected behavior, required scenario, status=NOT_RUN.

Allowed terminal statuses:
- PASS
- FAIL
- JUSTIFIED_EXCLUSIVE

Generic EXCEPTION is forbidden.

"Reachable but not explicitly exercised" is NOT justified.

Create a checker that fails if NOT_RUN>0, FAIL>0 or unjustified exclusions exist.

Create `docs/evidence/phase8/UI_CONTROL_COVERAGE_CONTRACT.md`.

STOP.
