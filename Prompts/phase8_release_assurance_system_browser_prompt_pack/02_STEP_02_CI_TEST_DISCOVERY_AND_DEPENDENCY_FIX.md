# Step 2 — CI Test Discovery & Browser Dependency Separation

Fix accidental pytest collection of executable validation scripts.

Preferred:
- rename standalone runners to `run_*.py`;
- configure pytest `testpaths = tests`;
- register markers;
- keep normal automated tests visible.

Separate runtime/test/browser-system dependencies. Browser validation jobs install Playwright; normal runtime users need not.

Update CI so Repository Hygiene, Python Validation, Tests, Clean-Room Phase1-7 and Frontend Contract are independent and deterministic.

Run:
- pytest --collect-only
- full pytest
- clean-room
- compileall
- pip check
- git diff --check

Trigger CI where possible.

Create `docs/evidence/phase8/02_CI_DISCOVERY_FIX_REPORT.md`.

Suggested commit:
`ci: fix test discovery and browser dependency separation`

STOP.
