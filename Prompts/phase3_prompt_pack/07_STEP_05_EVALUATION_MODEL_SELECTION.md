# Step 5 — PU-Aware Evaluation and Model Selection

## Objective

Evaluate Phase 3 candidates without pretending unlabeled customers are true negatives.

Read `14_MODEL_EVALUATION_CONTRACT.md`.

## Required validation outputs

For every fitted candidate, calculate:

### Dataset/split context
- validation customer count;
- validation known-positive count;
- validation unlabeled count;
- observed positive-label prevalence.

### Observed-label diagnostics
These compare known-positive labels to unlabeled labels and must be named accordingly:

- `observed_label_roc_auc`
- `observed_label_average_precision`

These are diagnostics, not true population ROC-AUC/precision.

### Ranking/retrieval
At top 5%, 10%, 20% of validation scores:

- number of customers in the slice;
- number of held-out known positives captured;
- `known_positive_recall_at_k`;
- `known_positive_concentration_at_k`;
- `known_positive_lift_at_k`.

Lift definition:

```text
(positive share in top slice) / (positive share in full validation set)
```

### Score distribution
For positive and unlabeled validation groups:

- mean;
- median;
- standard deviation;
- selected quantiles.

### Separation/stability
Record a bounded score-separation diagnostic such as:

- difference in mean score;
- KS statistic between positive and unlabeled observed-label score distributions, if implemented without adding heavy dependencies;
- package-native PU diagnostics if stable and documented.

## Model selection rule

The selected official model must be a genuine PU model.

Selection priority:

1. no leakage/contract failure;
2. valid finite outputs;
3. higher held-out known-positive lift/recall at practically relevant top slices;
4. score separation;
5. reproducibility;
6. runtime;
7. simpler model if performance is materially tied.

The naive baseline cannot win official selection.

If Elkan-Noto fails and Bagging PU succeeds, Bagging may be selected.

If all genuine PU candidates fail, the model run must fail. Do not select naive baseline as fallback.

## Minimum quality guardrails

Do not invent arbitrary “90% accuracy” targets.

Instead require basic evidence that the selected model is not degenerate:

- finite nonconstant validation scores;
- validation positives exist;
- top-10% known-positive lift meaningfully above random baseline, unless the dataset genuinely has no predictive signal;
- positive score distribution should not be materially worse than unlabeled under the primary ranking metric.

If the model is weak but technically valid, persist it only if the POC policy explicitly allows `COMPLETED_WITH_WARNING`; otherwise mark the run failed/quality-rejected. Keep the status contract simple if possible: `COMPLETED` with a quality flag inside metrics is acceptable.

## Evaluation JSON

Persist canonical bounded JSON containing:

```text
evaluation_contract_version
candidate_results
selected_candidate
selection_reason
quality_flags
```

Do not store per-customer validation scores in SQLite.

## Tests

- metric bounds;
- top-k edge cases;
- ties;
- very small validation set;
- zero positive validation set rejected earlier;
- deterministic ranking tie-break policy;
- baseline cannot be selected;
- selected candidate must be PU;
- non-finite scores fail;
- constant scores produce a quality warning/failure;
- JSON contains no customer IDs/PII.

## Full-data evidence

Train/evaluate on at least one real completed historical analysis.

Record:

- analysis run ID;
- cohort counts;
- split counts;
- candidate runtimes;
- evaluation metrics;
- selected candidate;
- selection reason.

Do not expose this as an application claim of real-world performance; the data are synthetic.

## Exit criteria

The system can defend why one genuine PU model was selected using a transparent, reproducible evaluation snapshot.
