# Step 3 — System Chrome/Edge Browser Harness

System-browser rule:
All Phase 8 certification must use a real operating-system browser: Google Chrome preferred, Microsoft Edge fallback. Playwright may control the installed browser. Do not use VS Code Simple Browser, IDE webviews, mock DOMs, or Playwright-bundled Chromium as the primary certification browser when system Chrome/Edge exists. Evidence must record browser product/version and execution mode. If neither Chrome nor Edge is installed, browser certification is NO-GO.

Create reusable detection:
1. explicit override
2. installed Chrome
3. installed Edge
4. fail clearly

Support env vars such as:
`SYSTEM_BROWSER=auto|chrome|edge`
`SYSTEM_BROWSER_PATH=<optional>`

Do not hardcode developer usernames.

Use Playwright to launch the installed executable with:
- clean temporary browser profile;
- controlled downloads;
- explicit viewport;
- normal application URL;
- headed debug option;
- headless certification option if supported.

Create reusable module, e.g.:
`scripts/validation/browser/system_browser.py`

Provide browser metadata, clean-context creation, console/network collection, screenshot helpers and cleanup.

Add unit tests for browser resolution without requiring a real browser in normal CI.

Create `docs/evidence/phase8/03_SYSTEM_BROWSER_HARNESS_REPORT.md`.

Suggested commit:
`test: add system chrome edge certification harness`

STOP.
