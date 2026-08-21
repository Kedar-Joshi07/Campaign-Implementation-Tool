# Phase 4 Handoff Contract

Phase 4 is expected to add model-training orchestration, job lifecycle/API behavior, and the Model Training UI.

This contract freezes what Phase 3 provides.

## Authoritative identifier

Phase 4 receives:

`model_run_id`

A usable model run must be:

- `COMPLETED`;
- structurally valid;
- linked to a valid completed `analysis_run_id`;
- backed by an existing artifact;
- checksum-verified;
- feature-contract-compatible.

## Model-run content

Phase 3 provides governed metadata:

- source `analysis_run_id`;
- selected PU algorithm;
- exact seed and validation fraction;
- reconstructed cohort counts;
- split counts;
- frozen feature contract and hash;
- preprocessing description;
- hyperparameters;
- PU-aware evaluation snapshot;
- exact library versions;
- relative artifact path;
- SHA-256.

## Artifact contract

The artifact must be able to accept a future dataset containing the frozen raw features:

- age
- gender
- state
- individual_yearly_income
- marital_status
- education
- employment_status
- resident_status
- resident_type
- family_member_count
- type_of_employment

and produce a continuous score through the persisted preprocessing + selected PU estimator.

Phase 4 must verify artifact checksum before using it.

## What Phase 4 may add

- background/process job execution;
- `jobs` lifecycle if not already present;
- model training API;
- model run listing/detail API;
- training progress/status;
- Model Training UI;
- training from a selected completed analysis run;
- display of Phase 3 evaluation results.

## What Phase 4 must not silently add

Unless separately approved, Phase 4 still should not:

- score 5M prospects;
- create `propensity_scores`;
- build Audience Explorer;
- create campaigns/exports;
- link customers to persons;
- change the frozen feature contract without compatibility/version handling.

Those belong to the scoring/audience phases.

## Retraining

If Phase 4 launches a new training run from an existing analysis, it should call/reuse the Phase 3 training service rather than reimplement modeling logic in the router/UI.

## Compatibility check

Before training or loading:

1. validate model/feature contract version;
2. validate source analysis;
3. verify artifact if reusing;
4. surface clear failure for incompatible/corrupt model metadata.

## No customer-level handoff

Phase 4 receives no persisted training-customer list and no PII artifact.

The model-run ID plus governed metadata/artifact is the handoff.
