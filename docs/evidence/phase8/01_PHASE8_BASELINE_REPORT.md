# Phase 8 Step 1 Baseline and Failure Reconciliation

Generated at: 2026-09-06T14:14:03Z

## Baseline
- Required starting SHA: 47a93d0a44c4df8ab12ff58157fbc204ec43a51d
- Local HEAD: 47a93d0a44c4df8ab12ff58157fbc204ec43a51d
- Remote main HEAD: 47a93d0a44c4df8ab12ff58157fbc204ec43a51d
- Branch: main
- Python: 3.12.0
- App version: 0.1.0
- Schema version: 12
- requirements.lock SHA256: 350439D9ACB3AFC8ED9E1ADC48DFAA8455ED81C53D3DEAA5248E36CEEB2401F1
- Pytest collection summary: 458 tests collected in 10.79s
- Workflow files: ci.yml, full-validation.yml

## Git Status Snapshot
- M docs/evidence/CLEANROOM_PHASE1_TO_PHASE7_REPORT.md
- M docs/evidence/cleanroom_phase1_to_phase7.json
- ?? Prompts/phase8_release_assurance_system_browser_prompt_pack/

## System Browser Availability
- Chrome preferred candidate found: True (C:/Program Files/Google/Chrome/Application/chrome.exe)
- Edge fallback candidate found: True (C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe)

## Latest CI Conclusions
- Latest run: CI (id=33886841019)
- Status/conclusion: completed / failure
- Head SHA: 47a93d0a44c4df8ab12ff58157fbc204ec43a51d
- Tests job annotation: Process completed with exit code 2
- Detailed Tests job logs were not directly downloadable in this environment (HTTP 403 without auth token).

Job outcomes:
- Repository Hygiene: completed/success
- Python Validation: completed/success
- Tests: completed/failure
- Clean-Room Phase1-7: completed/success
- Frontend Contract: completed/success

## Tests-Job Failure Reproduction
Reproduced in a temporary clean venv created from requirements.lock.

Command:
- python -m pytest -m "not cleanroom and not full5m and not performance and not browser" -q

Observed deterministic error:
- ERROR collecting scripts/validation/system_chrome_campaign_test.py
- ModuleNotFoundError: No module named playwright
- CI-style reproduction exit code: 2

Root cause:
- scripts/validation/system_chrome_campaign_test.py matches pytest default test discovery pattern (*_test.py).
- pytest.ini currently does not restrict test discovery to tests/.
- requirements.lock environment intentionally does not include Playwright, so importing playwright.sync_api fails during collection.

## Browser Evidence Reclassification
Sources reviewed:
- docs/evidence/full_fresh_e2e/UI_CONTROL_COVERAGE.md
- docs/evidence/full_fresh_e2e/system_chrome_full_fresh_e2e.json
- docs/evidence/full_fresh_e2e/system_chrome_campaign_test.json

Prior coverage summary:
- PASS=20
- FAIL=0
- EXCEPTION=87

Reclassification of previous EXCEPTION controls:
- Category A (genuine mutually-exclusive or inventory-artifact only): 10
- Category B (reachable but not explicitly tested): 77
- Every Category B control is mandatory in Phase 8.

## Open Issues Confirmed
- CI red: open
- Browser control gap: open
- Historical Analysis not truly browser-initiated: open
- Training not truly browser-initiated: open
- Full 5M scoring not truly browser-initiated: open
- Unexplained browser 404/error: open
- Stale source-hash docs: open
- Absolute machine paths in canonical summaries/evidence: open
- Raw GZIP hash drift with stable content: open
- dirty_override used previously: true
- Branch protection state: unresolved in this environment (HTTP 401 without GitHub auth token)

## Evidence Pointers
- docs/evidence/full_fresh_e2e/full_fresh_run_manifest.json
- docs/evidence/full_fresh_e2e/FULL_FRESH_PHASE1_TO_PHASE7_E2E_REPORT.md
- docs/evidence/full_fresh_e2e/UI_CONTROL_COVERAGE.md
- docs/evidence/full_fresh_e2e/system_chrome_campaign_test.json
- docs/evidence/phase8/01_phase8_gap_register.json

## STOP Gate
Step 1 deliverables created. No functional code changes were made.
