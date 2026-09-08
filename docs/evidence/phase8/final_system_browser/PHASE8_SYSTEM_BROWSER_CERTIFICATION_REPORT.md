# Phase 8 System Browser Certification Report

Generated at: 2026-09-08T15:28:18Z
Prompt: Prompts/phase8_release_assurance_system_browser_prompt_pack/11_STEP_11_CLEAN_HEAD_TRUE_BROWSER_PHASE1_TO_PHASE7_CERTIFICATION.md
Candidate SHA: 7b712bcecd9a8de20dd851bef457135c327dc5bf
Branch: main
Execution mode: user_directed_resume_existing
Resume disclosure: user-directed reuse of existing completed scoring; no import, training, or scoring rerun was performed by this aggregation.

## Clean-start gate
- Passed: True
- git status --short lines: []
- Browser resolved: chrome @ C:\Program Files\Google\Chrome\Application\chrome.exe

## Browser-driven stages
- step5_historical: PASS (Nones)
- step6_training_scoring: PASS (Nones)
- step7_audience: PASS (Nones)
- step8_campaigns: PASS (Nones)
- step9_browser_quality: PASS (Nones)

## Coverage acceptance
- PASS: 103
- FAIL: 0
- NOT_RUN: 0
- JUSTIFIED_EXCLUSIVE (with individual docs): 8
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
- docs/evidence/phase8/05_system_browser_historical_analysis.json: 5946c5c994302e8a7524c49403f3d3d4cf0e872bd1292bd4cb38dbcd5ccb8821
- docs/evidence/phase8/05_SYSTEM_BROWSER_HISTORICAL_ANALYSIS_REPORT.md: 1157e5c5a0cf4bbd30f93ed2c0cc1ae6a1544dd7ffe447c5778080508ad11a37
- docs/evidence/phase8/06_system_browser_training_and_5m_scoring.json: f3591aab0016c3042d29f482417a4c560bbb1f68c428855acb85e292ed4cac33
- docs/evidence/phase8/06_SYSTEM_BROWSER_TRAINING_AND_5M_SCORING_REPORT.md: 4e9ad6cdcb8dc1c35fd423ca45a7c79ed15ec64fbccddc6ed770c6f3618387aa
- docs/evidence/phase8/07_system_browser_audience_explorer_all_controls.json: 1e321822688c993e091450ae27d7bbbfd0a271d3eb94a35b6d0fef081668a45c
- docs/evidence/phase8/07_SYSTEM_BROWSER_AUDIENCE_REPORT.md: da90a9e0ded52b9d6f0220050d29e1cb8b7d00ef91884bfdcaf329a439388913
- docs/evidence/phase8/08_system_browser_campaign_builder_and_exports.json: 302cc39649cc75a057edb961b85429442f4385422377314f8c26821a15fe8a66
- docs/evidence/phase8/08_SYSTEM_BROWSER_CAMPAIGN_EXPORT_REPORT.md: d083e8d687316fba95ffa1bb7881ed95b4294d9f094891483b0ae77802885351
- docs/evidence/phase8/09_browser_quality_evidence.json: 550998fa5b8f1fb842be70859e78c7f32ae05c0d5ab7c3891106098ba54f124f
- docs/evidence/phase8/09_BROWSER_QUALITY_REPORT.md: 22d3b8e17d8272915791fb5e4c1e0dd6b4f5ad7b3d8799f0ff3dc9d92aa71c90
- docs/evidence/phase8/ui_control_inventory.json: c2c7110d85bdef4c8e810beb8fb6322f83dc01bcefc8d7e914a7ef8faae7a9f1

## Decision
- Overall status: PASS
- Local decision: PASS_PENDING_STEP12_CI
- Final GO declaration is deferred until Step 12 CI is green.