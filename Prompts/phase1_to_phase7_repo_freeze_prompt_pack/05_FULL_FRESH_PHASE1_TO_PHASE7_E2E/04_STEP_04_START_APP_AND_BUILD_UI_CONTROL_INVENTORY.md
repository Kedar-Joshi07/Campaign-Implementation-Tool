# Step 4 — Start App & Inventory Every UI Control

Start FastAPI/Uvicorn normally. Open a clean Chromium/Playwright profile with cache/storage cleared.

Discover all pages and interactive controls from rendered DOM plus frontend source.

Inventory every reachable actionable element: navigation, buttons, text/number/date inputs, selects, checkboxes/radios, tabs, pagination, refresh/reset/retry/save/next/back/finalize/export controls.

Create `docs/evidence/full_fresh_e2e/ui_control_inventory.json` with page, selector/test-id, label, type, expected behavior and planned test.

Final E2E fails if a reachable actionable control has no tested outcome or justified exception.

Do not use page.evaluate/internal JS functions to create workflow state. STOP.
