# Step 9 — Accessibility, Responsive & Browser E2E

Accessibility:
keyboard-only builder, labels, associated errors, aria-live status, focus to error
summary, stepper semantics, disabled-action explanations, no color-only status,
reduced motion.

Responsive:
1920x1080, 1366x768, tablet, narrow mobile.
Tables may scroll; controls must not clip.

Perform real browser acceptance.
Add small Playwright smoke suite if proportionate; otherwise create explicit manual
browser evidence and do not claim automated browser coverage.

Test existing screens plus Campaign Builder shell, error/loading states, keyboard and
mobile.

Create `docs/evidence/phase7_section1_browser_acceptance.json`. STOP.
