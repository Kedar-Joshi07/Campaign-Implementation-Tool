# Clean-Room Phase 1 to Phase 7 Report

Status: PASS
Generated at: 2026-10-04T19:27:59Z
Runtime root: C:\POCs\Campaign Implementation Tool\artifacts\cleanroom-runtime\phase1-7-mca9f0ur

## STEP1
- status: PASS
- duration_seconds: 22.648
- bounded_counts: customers=1200, campaign_sales=9000, demographics=12000

## STEP2
- status: PASS
- duration_seconds: 5.466

## STEP3
- status: PASS
- duration_seconds: 5.913
- model_job: id=1 statuses=['QUEUED', 'RUNNING', 'COMPLETED']
- scoring_job: id=2 statuses=['QUEUED', 'RUNNING', 'COMPLETED']

## STEP4
- status: PASS
- duration_seconds: 50.621
- saved_audience_id: 1

## STEP5
- status: PASS
- duration_seconds: 92.408
- email_campaign_id=1 selected=60 deliverable=58 undeliverable=2
- direct_mail_campaign_id=2 selected=60 deliverable=57 undeliverable=3

## CLEANUP
- status: PASS
- runtime_removed: True
