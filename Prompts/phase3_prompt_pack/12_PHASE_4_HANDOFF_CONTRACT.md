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

## Post-Phase-3 role-policy-v2 handoff — 2026-08-21

For model runs created after the algorithm-role update, Phase 4 must interpret:

- PRIMARY and selected artifact estimator: `BAGGING_PU` + Logistic Regression;
- CHALLENGER_1: `ELKAN_NOTO_LOGISTIC` + Logistic Regression;
- DIAGNOSTIC_CONTROL: `NAIVE_PU_LABEL_BASELINE`, never selection-eligible;
- `model_role_policy_version`: `2`;
- `evaluation_contract_version`: `2`;
- `selection_policy`: `PRIMARY_ROLE_GOVERNED`.

Elkan challenger metrics and challenger-minus-primary deltas are advisory. A
`CHALLENGER_OUTPERFORMED_PRIMARY` flag must not be interpreted as an automatic
promotion. Any promotion requires a separately approved governance policy.
Unlabeled observations remain unlabeled; Naive temporarily treats them as
negative only for diagnostic comparison. Observed-label metrics are not
true-negative performance, and scores are look-alike/PU rankings rather than
guaranteed calibrated purchase probabilities.

Final reference validation model runs 5 and 6 both selected Bagging and have identical
10,107-byte artifacts with SHA-256
`a6f50f3391997bec539f1371306a81d314079020686b588a28b3c44815a1a210`.
Historical role-policy-v1 rows/artifacts remain immutable and supported; missing
role-policy metadata must be treated as legacy v1 only when inspection requires
that distinction. Phase 4 must continue checksum verification and must not
rewrite old rows/artifacts.
