# Step 10 — Section 1 Acceptance & Handoff

Verify all existing UI wording/currentness/privacy fixes and all new Campaign Builder UI
regions/states.

Backend-dependent campaign actions must still be gated.

Run:
```powershell
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
```

Commit separately, e.g.:
`ui: align product language and prepare phase7 campaign builder`

Record Section 1 final SHA. That SHA becomes Section 2 baseline. STOP.
