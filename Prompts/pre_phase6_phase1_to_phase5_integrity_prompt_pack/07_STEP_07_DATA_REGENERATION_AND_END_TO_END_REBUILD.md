# Step 7 — Data Regeneration Decision and End-to-End Rebuild

Use the HEAD from successful Step 6.

Do not begin Phase 6.

## Decision rule

Use the measured Step 1 `underage_campaign_contact_count`.

### If count = 0

The current campaign source happens to satisfy the adult historical-contact invariant.

- Keep the current customer source.
- Keep the current demographic source.
- Full campaign regeneration is optional, not required.
- Still retain the corrected campaign generator for future deterministic generation.
- Create new provenance-aware Phase 2 analysis/model/scoring runs if Step 4 policy requires legacy runs to be replaced for the clean final baseline.

### If count > 0

Regenerate campaign sales with the corrected generator.

Do NOT regenerate the 5M demographic source.

Do NOT regenerate the customer master unless another measured customer-source defect was found.

## Campaign regeneration

Use the tracked current customer master as input.

Generate exactly:
- 570,000 campaign-sales rows;
- 96 campaigns;
- associated campaign master;
- product master;
- sample;
- summary.

Prove:
- exactly 570,000 rows;
- zero invalid customer FK;
- zero PU consistency violations;
- zero underage campaign contacts;
- date coverage remains within 2024-01-01..2025-12-31;
- deterministic rerun under the configured seed.

Update the Git LFS campaign source only after validation.

## Database strategy

Preferred cleanest validation approach:

Create a fresh validation database using the corrected code and import:

1. existing customer source;
2. corrected campaign source;
3. existing adult 5M demographic source.

This avoids confusing old derived rows with the new canonical chain.

The working POC database may then be rebuilt similarly, or safely migrated/reimported after evidence is complete.

## Rebuild derived Phase 2–5 chain

Because campaign history changed, do NOT continue treating the old analysis/model/scoring chain as current.

Create:

1. new Phase 2 completed analysis (`analysis_run_id`);
2. new Phase 3 governed model through Phase 4 job orchestration (`model_run_id`);
3. verify Bagging PRIMARY artifact and frozen feature contract;
4. new Phase 5 prospect scoring job (`scoring_run_id`);
5. exact 5M score reconciliation;
6. deterministic bounded re-score.

Old runs remain historical/audit evidence.

## Required full validation

Verify:

```text
customers = 125,000 target/tolerance policy
campaign_sales = 570,000
demographics = 5,000,000
underage campaign contacts = 0
demographic ages outside 18..100 = 0
demographic adult-count violations = 0
invalid customer FK = 0
PU consistency violations = 0
```

Phase 2:
- positive + unlabeled = selected
- saved historical source provenance current

Phase 3/4:
- analysis provenance current
- feature contract v1/hash unchanged
- role policy v2
- evaluation contract v2
- selected BAGGING_PU
- artifact verified

Phase 5:
- demographic provenance current
- historical/model provenance current
- scored count = 5,000,000
- score rows = 5,000,000
- scores finite and within [0,1]
- deterministic sample re-score passes

Do not impose old Phase 2/3 metric values if campaign data was regenerated; counts/metrics may legitimately change. Reconcile internally and document new evidence.

STOP and report.
