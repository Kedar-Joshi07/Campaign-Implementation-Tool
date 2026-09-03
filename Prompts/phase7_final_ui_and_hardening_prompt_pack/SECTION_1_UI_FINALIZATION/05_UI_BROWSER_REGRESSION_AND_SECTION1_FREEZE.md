# UI Step 5 — Browser Regression & UI Freeze

Run real browser acceptance at:
1920x1080, 1366x768, 1024x768, 390x844.

Verify:
- exact IDs
- exact target/reconciliation/export counts
- compact KPI cards still readable
- age/family constraints correct
- CURRENT/STALE states correct
- Campaign Builder wording reflects implemented backend
- an export STARTED state remains visible/trackable beyond 120 sec
- manual refresh works
- no Activate/Send action
- no PII preview
- keyboard/a11y behavior unchanged

Create:
`docs/evidence/phase7_final_ui_browser_acceptance.json`

Run:
```powershell
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
```

Commit, e.g.:
`ui: finalize phase7 exactness and long-running export status`

Record UI-finalization SHA. Section 2 starts from that SHA.
