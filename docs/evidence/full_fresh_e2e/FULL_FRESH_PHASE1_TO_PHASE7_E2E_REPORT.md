# Full Fresh Phase 1 to Phase 7 E2E Report

Status: PASS
Generated at: 2026-09-04T13:20:06Z
Completed at: 2026-09-04T14:55:56Z

## STEP1
- status: PASS
- duration_seconds: 17.486

## STEP2
- status: PASS
- duration_seconds: 320.985
- generated_rows: customers=125000, campaign_sales=570000, demographics=5000000

## STEP3
- status: PASS
- duration_seconds: 354.719

## STEP4
- status: PASS
- duration_seconds: 1620.174
- scoring_rows=5000000 distinct=5000000 min=0.06774103945805435 mean=0.20595671379862576 max=0.9782832402557606

## STEP5
- status: PASS
- duration_seconds: 1665.976
- email: campaign_id=1 selected=50000 deliverable=50000 rows=50000
- direct_mail: campaign_id=2 selected=500000 deliverable=500000 rows=500000

## STEP6
- status: PASS
- duration_seconds: 998.157

## STEP13
- status: PASS
- duration_seconds: 0.065
- ui_controls_total: 107

## STEP14
- status: PASS

## Decision
- status: GO
- reason: All full-fresh generation/import/scoring/audience/campaign/export and regression gates passed.
