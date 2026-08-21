# Step 4 — Genuine PU Training, Diagnostic Baseline, and Challenger

## Objective

Train genuine PU-learning candidate models using the Step 3 matrices.

Do not add browser APIs/UI.

## Required algorithms

### Candidate A — Primary

`ELKAN_NOTO_LOGISTIC`

Use:

- `pulearn.ElkanotoPuClassifier`
- probabilistic scikit-learn `LogisticRegression`
- fixed random seed where supported
- bounded `max_iter`
- sparse-compatible solver/configuration

The estimator must output a continuous positive-class score/probability-like quantity.

Record the learned Elkan-Noto labeling propensity value (`c`) when available and finite.

### Candidate B — Diagnostic only

`NAIVE_PU_LABEL_BASELINE`

Use ordinary logistic regression with:

- positive label = 1
- unlabeled = 0 treated as if negative

This is **not** PU learning.

Purpose:

- sanity-check that features contain signal;
- provide a reference ranking;
- reveal whether PU correction materially changes ordering.

Never select this candidate as the official PU model.

### Candidate C — Challenger

`BAGGING_PU`

Use `pulearn.BaggingPuClassifier` with bounded settings.

Recommended starting constraints:

- 10–20 estimators;
- deterministic random state;
- bounded CPU usage;
- a simple probabilistic base estimator;
- no unbounded hyperparameter search.

If runtime is excessive for the POC, mark it `SKIPPED_RUNTIME` with measured evidence.

## Training service

Recommended structure:

```text
app/ml/
  feature_contract.py
  preprocessing.py
  pu_estimators.py
  training.py
```

Training service input:

- training matrix;
- validation matrix;
- seed;
- feature contract metadata.

Output for each candidate:

- fitted estimator/pipeline;
- fit duration;
- score duration;
- validation scores;
- algorithm metadata;
- warnings/diagnostics.

## Label convention

Normalize explicitly to:

```text
1 = labeled/known positive
0 = unlabeled
```

Do not rely on implicit library assumptions.

## No hidden negatives

Do not:

- randomly sample unlabeled and call them true negatives;
- create negative labels from no-response/no-purchase records;
- train ordinary supervised model and rename it PU;
- calculate class weights using assumptions not in the approved design without documenting them.

## Stability

Same:

- analysis run;
- data;
- seed;
- hyperparameters;
- library versions

should yield materially identical outputs.

## Tests

Add compact synthetic PU fixtures where the expected signal is deliberately embedded.

Test:

- Elkan-Noto fits;
- output score length/range/finite values;
- naive baseline is clearly flagged non-PU;
- bagging PU fits on bounded fixture;
- label convention accepted;
- no prohibited feature reaches estimator;
- same seed reproducibility;
- training refuses all-positive or all-unlabeled cohorts;
- insufficient positives fail with actionable message;
- warnings are captured/documented rather than swallowed.

## Exit criteria

At least one genuine PU candidate successfully trains and scores a held-out customer validation set.
