# Phase 8 Step 5 System Browser Historical Analysis Report

Generated at: 2026-09-08T04:56:12Z

## Scope
- Prompt executed: Prompts/phase8_release_assurance_system_browser_prompt_pack/05_STEP_05_SYSTEM_BROWSER_OVERVIEW_DATA_STATUS_HISTORICAL_ANALYSIS.md
- Execution used system-browser harness only.

## Browser
- name: system_chrome
- executable: C:\Program Files\Google\Chrome\Application\chrome.exe
- version: 152.0.7977.82
- mode: headless

## Historical Analyses Submitted Through UI
- Broad run: id=1, selected=119748, positive=35416, unlabeled=84332
- Narrow run: id=2, selected=11662, positive=1297, unlabeled=10365
- UI reconciliation verified: positive + unlabeled == selected for both runs.

## Validation and Control Coverage
- Invalid input path triggered: True
- Validation message: Contact date from must be on or before contact date to.
- Reset cleared error: True
- Inventory statuses updated this step: 34 controls

## Backend Assertions (Post-UI Creation)
- Broad API run 1: status=COMPLETED, selected=119748, positive=35416, unlabeled=84332
- Narrow API run 2: status=COMPLETED, selected=11662, positive=1297, unlabeled=10365

## UI Error Telemetry
- Console errors: 0
- Page errors: 0
- Request failures: 0

## Outcome
- Step 5 completed with true browser-initiated historical analyses and inventory status updates.