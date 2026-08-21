# Phase 3 PU Model Evaluation Contract

## Why normal supervised evaluation is insufficient

Known-positive customers are labeled.

Unlabeled customers are **not confirmed negatives**.

Therefore, a confusion matrix that treats every unlabeled customer as truly negative is not a ground-truth confusion matrix.

Phase 3 may compute observed-label diagnostics, but must label them honestly.

## Required metrics

### 1. Split context

Persist:

- `validation_customer_count`
- `validation_positive_count`
- `validation_unlabeled_count`
- `observed_positive_prevalence`

### 2. Observed-label diagnostics

Compute against PU labels for comparison only:

- `observed_label_roc_auc`
- `observed_label_average_precision`

Documentation must say:

> These measure separation of labeled positives from unlabeled observations, not true positives from true negatives.

### 3. Top-slice metrics

For `k ∈ {0.05, 0.10, 0.20}`:

Sort validation customers by model score descending.

Use a deterministic tie-breaking policy that does not use PII. If exact customer identity is required internally to break ties, do not persist it; alternatively use stable score/index ordering from the deterministic split.

Compute:

```text
top_n = max(1, ceil(validation_count * k))

known_positive_recall_at_k =
  known positives in top_n / all known positives in validation

known_positive_concentration_at_k =
  known positives in top_n / top_n

known_positive_lift_at_k =
  known_positive_concentration_at_k / observed_positive_prevalence
```

Handle zero denominators explicitly.

### 4. Score summaries

For both labeled-positive and unlabeled validation rows:

- count
- mean
- median
- std
- p10
- p25
- p75
- p90

### 5. Candidate runtime

- fit seconds
- scoring seconds

### 6. Optional/package-native PU diagnostics

May include well-understood metrics from `pulearn`, but do not make the implementation depend on obscure metrics when a transparent POC metric is sufficient.

Record algorithm/library version.

## Prohibited/misleading headline metrics

Do not headline:

- accuracy
- specificity
- true-negative rate
- negative predictive value
- ordinary precision as “true precision”

unless true negatives somehow become available under a separately approved design.

## Selection priorities

1. Genuine PU candidate only.
2. Contract/leakage correctness.
3. finite/nondegenerate scores.
4. known-positive lift/recall.
5. stability/reproducibility.
6. runtime/simplicity.

## Quality flags

Recommended flags:

- `LOW_POSITIVE_COUNT`
- `LOW_SCORE_VARIANCE`
- `LOW_TOP10_LIFT`
- `PU_PROPENSITY_ESTIMATE_UNSTABLE`
- `CHALLENGER_SKIPPED_RUNTIME`
- `OBSERVED_LABEL_METRICS_ONLY`

Flags should explain limitations without pretending the synthetic POC has real-world ground truth.

## Reproducibility

The same split and model configuration should return metrics within a strict deterministic or numerical tolerance.

Persist all metric values as finite JSON numbers.

`allow_nan=False` when serializing.
