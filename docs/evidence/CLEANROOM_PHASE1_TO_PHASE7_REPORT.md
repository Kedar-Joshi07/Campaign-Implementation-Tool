# Clean-Room Phase 1 to Phase 7 Report

Status: PASS
Generated at: 2026-09-22T08:04:19Z
Runtime root: C:\POCs\Campaign Implementation Tool\artifacts\cleanroom-runtime\phase1-7-e_u7d_i9

## STEP1
- status: PASS
- duration_seconds: 21.512
- bounded_counts: customers=1200, campaign_sales=9000, demographics=12000

## STEP2
- status: PASS
- duration_seconds: 4.941

## STEP3
- status: PASS
- duration_seconds: 8.02
- model_job: id=1 statuses=['QUEUED', 'RUNNING', 'COMPLETED']
- scoring_job: id=2 statuses=['QUEUED', 'RUNNING', 'COMPLETED']

## STEP4
- status: PASS
- duration_seconds: 56.925
- saved_audience_id: 1

## STEP5
- status: PASS
- duration_seconds: 100.195
- email_campaign_id=1 selected=60 deliverable=58 undeliverable=2
- direct_mail_campaign_id=2 selected=60 deliverable=57 undeliverable=3

## CLEANUP
- status: PASS
- runtime_removed: True
