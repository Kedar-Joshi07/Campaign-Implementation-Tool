# Phase 8 Step 2 CI Test Discovery and Dependency Separation Report

Generated at: 2026-09-06T15:06:10Z

## Scope
- Prompt executed: Prompts/phase8_release_assurance_system_browser_prompt_pack/02_STEP_02_CI_TEST_DISCOVERY_AND_DEPENDENCY_FIX.md
- Goal: prevent accidental pytest collection of executable browser validation scripts and validate CI-equivalent gates.

## Implemented Changes
- Renamed standalone validation runner:
  - from: scripts/validation/system_chrome_campaign_test.py
  - to: scripts/validation/run_system_chrome_campaign.py
- Restricted pytest discovery to intended suite:
  - updated pytest.ini with `testpaths = tests`

## Dependency Separation Status
- Runtime and CI normal test flows continue to install `requirements.lock` only.
- Browser-system validation remains script-driven and separate from standard pytest collection.
- Existing CI job separation already present and preserved in .github/workflows/ci.yml:
  - Repository Hygiene
  - Python Validation
  - Tests
  - Clean-Room Phase1-7
  - Frontend Contract

## Required Gates
- `pytest --collect-only`: PASS
  - collected: 458
  - rootdir/config confirms `testpaths: tests`
- `pytest -q`: PASS
  - 458 passed in 1085.12s
- `pytest -m "not cleanroom and not full5m and not performance and not browser" -q`: PASS
  - 429 passed, 29 deselected in 926.52s
- clean-room (`python scripts/validation/run_cleanroom_phase1_to_phase7.py`): PASS
  - report: docs/evidence/CLEANROOM_PHASE1_TO_PHASE7_REPORT.md
  - json: docs/evidence/cleanroom_phase1_to_phase7.json
- `python -m compileall -q app scripts tests`: PASS (`COMPILEALL_OK`)
- `python -m pip check`: PASS (`No broken requirements found.`)
- `git diff --check`: PASS for blocking issues
  - warnings only: existing line-ending conversion warnings in clean-room evidence files

## CI Trigger Attempt
- `gh` CLI unavailable in this environment (`CommandNotFoundException`).
- No direct authenticated CI trigger was performed from this session.

## Outcome
- Step 2 objective achieved: accidental collection path removed and CI Tests selector now passes locally.
- No application business logic changes were made.