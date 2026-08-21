# Phase 3 Handoff Contract

This file freezes what Phase 2 must provide to a future Phase 3 PU-learning implementation. It does not authorize Phase 3 work.

## Authoritative handoff identifier

Phase 3 receives exactly one persisted:

`analysis_run_id`

The identifier refers to one `COMPLETED` row in `historical_analysis_runs`.

Phase 3 must reject missing, failed, unknown, or structurally invalid runs.

## What the saved run represents

A completed run is a reproducible definition of:

1. Which historical `campaign_sales` observations are in scope.
2. Which distinct historical customers are selected.
3. Which selected customers are known positive under the chosen conversion definition.
4. Which selected customers remain unlabeled.
5. Which normalized date range is used for deterministic feature derivation.
6. What aggregate counts/profiles were observed when the run was created.

The saved aggregate `results_json` is an explanatory snapshot. It is not a training matrix.

## Phase 3 reconstruction rule

Phase 3 may load the normalized `filters_json` and reconstruct the customer-grain cohort using the same authoritative cohort-selection service/query semantics established in Phase 2.

Do not persist a massive customer-ID list merely to hand off the cohort. Do not persist SQL supplied by the user. Do not infer a link to demographic `person_id` values.

If Phase 3 needs frozen membership despite changing source data, that is a new explicit design decision requiring a schema extension, source-data version/checksum strategy, and approval. Phase 2 does not silently implement it.

## Frozen label rules

For observations inside the normalized filters:

- `ATTRIBUTED_PURCHASE`: positive when attributed-sale flag and purchase flag are both 1.
- `ANY_PURCHASE`: positive when purchase flag is 1.
- `RESPONSE`: positive when response flag is 1.

At distinct customer grain:

- known positive = any matching observation is positive;
- unlabeled = selected customer without a matching positive observation;
- unlabeled is not negative.

Phase 3 must not relabel unlabeled customers as confirmed negatives without an approved PU-learning method.

## Candidate shared predictive features

Phase 3 may derive a prospect-compatible feature set from historical customers using only concepts that also exist in the independent demographics population:

- age, deterministically derived from date of birth using the saved analysis end date
- gender
- state
- individual yearly income
- marital status
- education
- employment status
- resident status
- resident type
- family member count
- type of employment

Encoding, imputation, rare-category policy, leakage checks, fairness/ethics review, PU algorithm, validation design, hyperparameters, and model persistence are **not** defined by Phase 2. They require the Phase 3 specification.

## Prohibited predictive leakage

Do not include as prospect look-alike inputs:

- `customer_id`
- names, email, phone, address, postal code, or other identifiers
- campaign exposure counts
- prior purchases, responses, engagement, spend, margin, recency, or preferred product
- `pu_label` itself
- target campaign/product fields unless Phase 3 explicitly designs a conditional model with corresponding prospect-time inputs
- any attribute invented by linking historical customers to demographic `person_id`

Campaign and sales variables define the target behavior and may be used for cohort/label construction or descriptive reporting. They are not automatically valid prospect features.

## Reproducibility checks required before training

Phase 3 must, at minimum:

1. Load a completed run.
2. Validate the stored filter schema/version.
3. Recompute selected, positive, and unlabeled counts.
4. Compare recomputed counts with the saved summary.
5. Stop on unexplained mismatch.
6. Confirm positive + unlabeled = selected.
7. Confirm no `person_id` linkage is used.
8. Record the source analysis-run ID in model metadata.

## Boundary

The existence of this contract does not mean Phase 2 has trained a model. A Phase 2 acceptance audit must fail if model artifacts, scoring tables, scoring APIs, model metrics, or enabled model UI are present.

