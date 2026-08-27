# Step 3 — Adult Historical Campaign Eligibility

Use the HEAD from successful Step 2.

Do not begin Phase 6.

## Problem

Customer master generation is adult as of 2025-12-31, while campaign history begins 2024-01-01.

The campaign generator calculates customer age on campaign start but currently allows all customers into weighted sampling.

Therefore customers aged 18/19 at the 2025 reference can be selected in 2024 while they were still under 18.

Phase 3 derives age at the saved analysis end date and the frozen feature contract requires age 18..100.

## Required generator correction

In:

`data_generation_scripts/generate_campaign_sales.py`

For each campaign:

1. calculate age at campaign start;
2. build:
   `eligible_indices = customers with age >= 18`;
3. require campaign target size <= eligible count;
4. calculate target/affinity weights as currently defined;
5. restrict weights to eligible indices;
6. normalize only eligible weights;
7. sample only from eligible indices;
8. contact dates remain within campaign window, so everyone contacted remains >=18.

Do not weaken the frozen feature contract.

Do not change `customer_id`/`person_id` separation.

Do not simply set disallowed weights to zero before the existing `normalize_weights()` if that helper forces a positive floor.

## Generator validation

At the end of generation, prove:

```text
underage_contact_count = 0
minimum_age_at_contact >= 18
```

Use calendar-aware completed age for final validation.

Add these fields to `campaign_sales_summary.json`.

## Reconciliation

Extend `run_reconciliation()` with a cross-dataset structural check:

```text
underage_campaign_contact_count
```

calculated by joining campaign sales to customer DOB and using calendar-aware age on `contact_date`.

Any count > 0 must make campaign_sales reconciliation `ERROR`.

Do not expose IDs.

## Tests

Add:
- generator small-run test proving zero underage contacts;
- exact birthday boundary tests;
- age 17 contact rejected by reconciliation;
- age 18-on-contact accepted;
- current PU/FK/count reconciliation unchanged;
- Phase 2 analysis behavior unchanged for compliant data;
- Phase 3 early-date cohort no longer violates age contract when generated from corrected data.

Do not regenerate the full campaign file in this step.

STOP and report.
