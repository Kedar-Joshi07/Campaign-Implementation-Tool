# Step 13 — UI Coverage, Accessibility, Responsive & Screenshot Evidence

Compare actual executed tests with the full UI-control inventory.

Every reachable actionable control must be PASS/FAIL or have an explicit justified exception.

Create:
`docs/evidence/full_fresh_e2e/UI_CONTROL_COVERAGE.md`

Collect browser console errors, unhandled promise rejections and failed critical network requests. Any unexplained critical error = FAIL.

Accessibility smoke:
visible keyboard focus, labels, keyboard-operable buttons, aria-live/error behavior, stepper/focus behavior and table/control reachability.

Responsive checks:
- 1920x1080
- 1366x768
- ~768px width
- 390x844

Validate major pages at every viewport. Reuse completed backend state rather than rerunning 5M jobs per viewport.

Capture only curated screenshots for major lifecycle states. STOP.
