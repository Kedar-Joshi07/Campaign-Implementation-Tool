# Phase 8 Step 8 System Browser Campaign Export Report

Generated at: 2026-09-08T03:48:04Z

## Scope
- Prompt executed: Prompts/phase8_release_assurance_system_browser_prompt_pack/08_STEP_08_SYSTEM_BROWSER_CAMPAIGN_BUILDER_AND_EXPORTS.md
- Execution path: Campaign Builder full lifecycle for EMAIL and DIRECT_MAIL, including browser handoff and export contract verification.

## Browser
- sessions: 2
- name: system_chrome
- executable: C:\Program Files\Google\Chrome\Application\chrome.exe
- version: 152.0.7977.82
- mode: headless

## Navigation and Handoff
- Campaign view entered via normal navigation: yes
- Audience Explorer handoff hash: #campaigns
- Handoff selected audience name: Phase8 Step7 Current Audience 1788809854

## Validation Scenarios
- Missing audience: Select a current saved audience before continuing.
- Blank campaign name: Campaign name is required.
- Missing/invalid channel: Channel is required and must be EMAIL or DIRECT_MAIL.
- Back/forward preservation checks: {'review_summary_contains_name': True, 'review_summary_contains_channel': True, 'campaign_name_preserved': True, 'campaign_description_preserved': True, 'campaign_channel_preserved': True}
- Finalized immutability: {'blocked': True, 'message': 'FINALIZED campaigns are immutable.'}

## EMAIL
- Campaign id: 24
- Export profile: EMAIL_CONTACT_V1
- Download path: C:\Users\KEDAR~1.JOS\AppData\Local\Temp\phase8-browser-downloads-meoiozrk\phase8_step8\step8_email_export_1788839981072.csv
- Columns: ['person_id', 'propensity_score', 'percentile_bucket', 'decile', 'rank_band', 'first_name', 'last_name', 'email']
- Reconciliation: selected=50000, deliverable=50000, undeliverable=0, rows=50000
- CSV SHA256: 4a70d45b791c5f150c4d4c375c59cb1717d8745a3595b281ab47c1b19d7aed64
- Export audit SHA256: 4a70d45b791c5f150c4d4c375c59cb1717d8745a3595b281ab47c1b19d7aed64
- Long-running status trackability needed: False
- Long-running status trackability checked: False

## DIRECT_MAIL
- Campaign id: 25
- Export profile: DIRECT_MAIL_CONTACT_V1
- Download path: C:\Users\KEDAR~1.JOS\AppData\Local\Temp\phase8-browser-downloads-743uy9nt\phase8_step8\step8_direct_mail_export_1788840544103.csv
- Columns: ['person_id', 'propensity_score', 'percentile_bucket', 'decile', 'rank_band', 'first_name', 'last_name', 'address_line_1', 'address_line_2', 'city', 'state', 'postal_code']
- Reconciliation: selected=50000, deliverable=50000, undeliverable=0, rows=50000
- CSV SHA256: 911296a70e3633007dd523a6a9c7d388412644595c8966dd49f0032cdb9095be
- Export audit SHA256: 911296a70e3633007dd523a6a9c7d388412644595c8966dd49f0032cdb9095be
- Long-running status trackability needed: False
- Long-running status trackability checked: False

## UI Error Telemetry
- Console errors: 0
- Page errors: 0
- Request failures: 0

## Campaign Control Inventory
- Campaign controls PASS: 24
- Campaign controls FAIL: 0
- Campaign controls JUSTIFIED_EXCLUSIVE: 1
- Campaign controls NOT_RUN: 0
- Controls updated this step: 25

## Outcome
- Step 8 completed with full Campaign Builder lifecycle coverage, both export profiles, download capture, deterministic ordering checks, checksum reconciliation, and campaign control terminalization.