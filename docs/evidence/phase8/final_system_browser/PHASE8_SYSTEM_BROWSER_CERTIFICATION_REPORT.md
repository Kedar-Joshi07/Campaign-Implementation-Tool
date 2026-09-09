# Phase 8 System Browser Certification Report

Generated at: 2026-09-08T20:30:21Z
Prompt: Prompts/phase8_release_assurance_system_browser_prompt_pack/11_STEP_11_CLEAN_HEAD_TRUE_BROWSER_PHASE1_TO_PHASE7_CERTIFICATION.md
Candidate SHA: 969de70560fe086296c643ad47609678fc9e3e40
Branch: main
Execution mode: strict_fresh_single_run

## Clean-start gate
- Passed: True
- git status --short lines: []
- Browser resolved: chrome @ C:\Program Files\Google\Chrome\Application\chrome.exe

## Browser-driven stages
- step5_historical: PASS (195.158s)
- step6_training_scoring: PASS (2269.531s)
- step7_audience: PASS (2619.677s)
- step8_campaigns: PASS (272.982s)
- step9_browser_quality: PASS (85.867s)

## Coverage acceptance
- PASS: 104
- FAIL: 0
- NOT_RUN: 0
- JUSTIFIED_EXCLUSIVE (with individual docs): 7
- Generic EXCEPTION: 0
- Coverage gate status: True

## Integrity
- customers_125k: True
- campaign_sales_570k: True
- prospects_5m: True
- current_imports_completed: True
- completed_analysis_present: True
- governed_model_present: True
- scores_5m_completed: True
- deterministic_rescore_sample: True
- rank_boundaries_100: True
- analytics_current: True
- saved_audience_present: True
- finalized_email_campaign: True
- finalized_direct_mail_campaign: True
- completed_exports_present: True
- no_stale_active_jobs: True
- no_started_exports: True
- pragma_integrity_ok: True

## Browser quality
- 0 unexplained console errors: True
- 0 unexplained critical network failures: True

## Run IDs and checksums
- IDs: {'historical_analysis_run_ids': {'broad': 1, 'narrow': 2}, 'model_run_id': 1, 'scoring_run_id': 1, 'saved_audience_id': 1, 'campaign_ids': {'email': 1, 'direct_mail': 2}, 'export_event_ids': {'email': 1, 'direct_mail': 2}, 'export_checksums': {'email': '14dcdcb8734483310d20ba539409f141de20aedfd14e68890a97d4fd980157a0', 'direct_mail': '9aee8cb3d70e80fe8b9f18e7b372bb4da8b00b1591af58fd3820ff4301822bed'}}

## Artifact SHA-256
- docs/evidence/phase8/05_system_browser_historical_analysis.json: c4c2931b70a4f8b749e71424d294ecd732f1d7fc9ab76e7c622a0fce59fcb171
- docs/evidence/phase8/05_SYSTEM_BROWSER_HISTORICAL_ANALYSIS_REPORT.md: aa6c2b4ae8326a40b5f6ea57d6537475dcf011054d08324da2651c11ea1766f2
- docs/evidence/phase8/06_system_browser_training_and_5m_scoring.json: 64820fe1e0fc2a715100c5041dea2cab412530656beae9b98b00a7e1d50342bd
- docs/evidence/phase8/06_SYSTEM_BROWSER_TRAINING_AND_5M_SCORING_REPORT.md: f91e7aec4788ca86443f3adc5daf92ec6d6576c122a57caf0f261952e5c54bcb
- docs/evidence/phase8/07_system_browser_audience_explorer_all_controls.json: f8c4b713216ce329408924ee8dccb7342a121b066e78290e3e1533690370d656
- docs/evidence/phase8/07_SYSTEM_BROWSER_AUDIENCE_REPORT.md: e6b36797ab621db4dc1b026d4c79a3fa3ca7a24005ffd9befd7e866ed5e328c1
- docs/evidence/phase8/08_system_browser_campaign_builder_and_exports.json: 827ce951cc38e8f2d1c316337fddd9cca2903bbadd0d509fdb937b87d009a316
- docs/evidence/phase8/08_SYSTEM_BROWSER_CAMPAIGN_EXPORT_REPORT.md: b79b7e87bbaff577a152ccf7d41e5b52009e07154c9bd842e8be93532dc821c9
- docs/evidence/phase8/09_browser_quality_evidence.json: 6e2cb0caed158f0dfa91adbb7ca988358cabc3b8db1ce8e495854f11c43e82bb
- docs/evidence/phase8/09_BROWSER_QUALITY_REPORT.md: 2024e009191eb3f4b402915838b360a79a2274f07b64b054d5d4cc0236718053
- docs/evidence/phase8/ui_control_inventory.json: 3236b1dd110b4270d1b4a136547a926aebe03e1b43c66925c5a18c041549b9e4

## Decision
- Overall status: PASS
- Local decision: PASS_PENDING_STEP12_CI
- Final GO declaration is deferred until Step 12 CI is green.