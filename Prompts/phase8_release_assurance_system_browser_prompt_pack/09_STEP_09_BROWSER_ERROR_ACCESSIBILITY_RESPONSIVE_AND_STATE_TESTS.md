# Step 9 — Browser Errors, Accessibility, Responsive Layout & State Tests

Use the real system Chrome/Edge harness.

## Console/network
Collect console.error, uncaught exceptions, unhandled promise rejections and failed critical requests.

Resolve every unexplained 4xx/5xx/JS error. If a harmless optional asset such as favicon is responsible, fix it or explicitly classify it so the final unexplained-error count is zero.

Final targets:
- 0 unexplained console errors
- 0 unexplained critical network failures

## Accessibility smoke
Test:
- visible keyboard focus
- Tab/Shift+Tab traversal
- Enter/Space activation
- labels for controls
- validation focus/error summary
- aria-live states
- disabled-action explanations
- stepper semantics
- table/control reachability
- no color-only status
- reduced-motion behavior where applicable

## Responsive
Validate major pages at:
- 1920x1080
- 1366x768
- 1024x768
- ~768px width
- 390x844

Do not rerun 5M jobs per viewport; reuse completed backend state.

## State coverage
Exercise loading, empty, retryable error, stale/historical read-only, long-running job, long-running export, completed and failed/aborted states where safely reproducible.

Create `docs/evidence/phase8/09_BROWSER_QUALITY_REPORT.md`.

STOP.
