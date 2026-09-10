# Step 13 — Accessibility, Responsive Design & Business Usability

## Objective
Ensure a non-technical user can complete the workflow without hidden interaction barriers.

## Accessibility
Verify:
- complete keyboard path
- visible focus
- labels for every input
- multi-select keyboard access
- selected chips removable by keyboard
- stepper semantics
- validation focus
- aria-live for loading/result state
- no status communicated by color alone
- accessible tables
- reduced motion where applicable
- tooltips/help available without mouse-only interaction

## Responsive viewports
Use system browser:
- 1920x1080
- 1366x768
- 1024x768
- 768x1024
- 390x844

Test the full new wizard shell at every viewport.
Do not rerun heavy backend work per viewport.

## Business usability review
A user should be able to answer:
1. What campaign am I creating?
2. What am I promoting?
3. Who do I want to reach?
4. How selective is my target group?
5. How many people match?
6. Why were they selected?
7. Is the targeting result up to date?
8. What happens when I save?

If the UI requires knowledge of `analysis_run_id`, `model_run_id`, `scoring_run_id`, PU, algorithms, or model artifacts in the normal path: FAIL.

## Copy quality
Use short labels and helper text.
Avoid walls of technical text.

Create:
`docs/evidence/phase9/13_ACCESSIBILITY_RESPONSIVE_USABILITY_REPORT.md`

STOP.
