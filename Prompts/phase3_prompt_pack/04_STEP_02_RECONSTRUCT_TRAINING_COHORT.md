# Step 2 — Reconstruct and Reconcile the Customer-Grain Training Cohort

## Objective

Given one completed `analysis_run_id`, reconstruct exactly the customer-grain population that Phase 2 defined.

Do not fit a model yet.

## Required implementation

Create a Phase 3 modeling repository/service layer. Reuse authoritative Phase 2 filter semantics rather than duplicating them carelessly.

Recommended responsibilities:

```text
ModelTrainingRepository
  - load completed analysis metadata
  - reconstruct matching observations/customer labels
  - fetch one row per selected historical customer
  - return only candidate raw features + internal customer key + PU label

TrainingCohortService
  - validate run
  - reconcile counts
  - enforce feature boundary
  - return bounded in-memory customer-grain matrix
```

## Reconstruction

1. Load saved normalized filters for `analysis_run_id`.
2. Reject:
   - missing run;
   - RUNNING;
   - FAILED;
   - malformed saved filters/results.
3. Recompute matching observations using Phase 2 semantics.
4. Group by `customer_id`.
5. Calculate `is_positive` from the saved conversion definition and matching observations only.
6. Join labels to `customers`.
7. Derive age using saved `contact_date_to`.
8. Produce one row per selected customer.

## Required raw internal fields

Internal only:

- `customer_id`
- `pu_label`

Candidate model fields:

- `age`
- `gender`
- `state`
- `individual_yearly_income`
- `marital_status`
- `education`
- `employment_status`
- `resident_status`
- `resident_type`
- `family_member_count`
- `type_of_employment`

No other field is permitted.

## Reconciliation

Before returning the matrix, verify:

```text
row count = saved selected_customer_count
positive count = saved positive_customer_count
unlabeled count = saved unlabeled_customer_count
positive + unlabeled = selected
unique customer_id count = row count
```

Also reconcile matching observation count against the saved Phase 2 summary.

Any unexplained mismatch must stop training.

## Source mutation concern

Saved Phase 2 results are snapshots. Phase 3 deliberately reconstructs from current historical sources.

Therefore, if source history changed since the saved analysis was created, count mismatch is a **hard stop** for this POC.

Do not silently retrain on a different population.

## Query boundary

The cohort reconstruction path must not query `demographics`.

A trace-based test should prove that.

## Data type rules

- `age`: integer/nullable after deterministic derivation.
- income: numeric finite or missing.
- family count: integer/nullable.
- categorical fields: strings/nullable; normalization belongs in Step 3.
- PU label: exact `0`/`1`.

## Tests

Use focused fixtures to prove:

- multiple observations per customer become one training row;
- positive if any matching observation qualifies;
- outside-filter activity does not affect the label;
- all three conversion definitions reconstruct correctly;
- `contacted_only` behavior remains correct;
- inclusive date behavior remains correct;
- age birthday boundaries match Phase 2;
- mismatched saved count stops;
- malformed/failed/missing run stops;
- no demographics SQL;
- no prohibited columns in the returned raw modeling frame.

## Full-data validation

On the populated local DB, use one known completed analysis and record:

- source analysis ID;
- matching observation count;
- customer rows;
- positives;
- unlabeled;
- reconciliation result;
- reconstruction runtime and approximate memory footprint.

## Exit criteria

A valid `analysis_run_id` can deterministically yield a reconciled customer-grain raw training frame with no modeling leakage.
