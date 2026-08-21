# Phase 3 Freeze, Requirements, and Boundaries

## 1. Authoritative starting point

Repository:

`https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Required base commit:

`52396010f945b0328b84453ce25c587b11ed7fd7`

This SHA is the accepted Phase 2 baseline.

Before implementation:

1. Run `git rev-parse HEAD`; it must equal the required SHA unless later commits have been explicitly reviewed.
2. Run `git status --short`; preserve unrelated user changes.
3. Run the full Phase 2 test suite and record the exact baseline result.
4. Run `python scripts/validate_data.py --json` against the populated local database when available.
5. Verify schema version 2 and a healthy `historical_analysis_runs` table.
6. Confirm at least one valid `COMPLETED` historical analysis exists for full-data validation. If none exists locally, create one through the existing Phase 2 workflow; do not commit the local DB.
7. Add a short clarification to Phase 2 evidence documentation that the accepted implementation was subsequently committed as `52396010f945b0328b84453ce25c587b11ed7fd7`. Do not rewrite historical evidence that accurately describes the pre-commit validation moment.

Phase 3 is additive. Do not rewrite or loosen Phase 1 or Phase 2 behavior.

---

## 2. Phase 3 product objective

Phase 3 implements the modeling foundation:

```text
Completed Phase 2 analysis_run_id
        ↓
Validate + reconstruct cohort
        ↓
Reconcile saved counts
        ↓
Customer-grain training matrix
        ↓
Prospect-compatible feature contract
        ↓
Deterministic preprocessing
        ↓
PU model training
        ↓
PU-aware evaluation
        ↓
Model selection
        ↓
Persist model artifact + governed metadata
        ↓
model_run_id
```

The central question is:

> Can the system learn a reproducible look-alike model from known-positive and unlabeled historical customers using only attributes that will later exist for independent prospects?

---

## 3. Frozen technology

Preserve:

- Python 3.11+
- FastAPI/Pydantic
- direct Python `sqlite3`
- HTML/CSS/Vanilla JavaScript
- Pytest
- one local SQLite database
- local on-disk model artifacts

Phase 3 may add:

- NumPy
- pandas only where it materially simplifies bounded in-memory ML preparation; do not use pandas to replace existing SQL aggregation paths
- scikit-learn
- `pulearn`
- joblib

Preferred open-source strategy:

- scikit-learn: BSD-3-Clause, commercially usable
- `pulearn`: BSD-3-Clause
- primary PU method: Elkan & Noto classifier
- challenger PU method: Bagging PU classifier, if runtime remains acceptable
- diagnostic-only naive benchmark: ordinary probabilistic classifier trained with unlabeled treated as negative

The naive benchmark must never be labeled or persisted as the selected PU model merely because its standard supervised metric is larger.

Do not introduce:

- TensorFlow
- PyTorch
- XGBoost/LightGBM unless explicitly approved
- MLflow
- Airflow
- Redis
- Celery
- RabbitMQ
- Kafka
- Spark
- cloud ML services
- AutoML platforms

---

## 4. Phase 1/2 invariants

All of these remain mandatory:

1. `customer_id` belongs to historical customers.
2. `person_id` belongs only to the independent demographic prospect universe.
3. No row-level customer/person linkage exists or is inferred.
4. Synthetic PII is never used as a predictive feature.
5. Existing Phase 1 and Phase 2 APIs continue to work.
6. Historical analyses stay at distinct-customer grain.
7. `positive + unlabeled = selected`.
8. Activity outside saved filters cannot alter the reconstructed label.
9. Unlabeled never means confirmed negative.
10. Existing source datasets remain unchanged.
11. No full historical or demographic dataset is returned to the browser.

---

## 5. Exact Phase 3 input

Phase 3 accepts exactly one authoritative input identifier:

`analysis_run_id`

It must reference a structurally valid `COMPLETED` Phase 2 run.

Before training:

1. Load the saved run.
2. Validate normalized saved filters.
3. Reconstruct the cohort from source `campaign_sales` and `customers`.
4. Recompute:
   - observation count;
   - selected distinct customers;
   - positives;
   - unlabeled.
5. Compare recomputed counts with the saved Phase 2 summary.
6. Stop on unexplained mismatch.
7. Confirm `positive + unlabeled = selected`.
8. Record the source `analysis_run_id` in model metadata.

Do not use `results_json` as the training dataset.

---

## 6. Frozen model feature boundary

Permitted candidate predictive features are exactly:

### Numeric
- `age` — derived from `customers.date_of_birth` using the saved analysis end date
- `individual_yearly_income`
- `family_member_count`

### Categorical
- `gender`
- `state`
- `marital_status`
- `education`
- `employment_status`
- `resident_status`
- `resident_type`
- `type_of_employment`

No other feature may be added without updating the frozen contract and tests.

Prohibited features include:

- `customer_id`
- any name field
- email
- phone
- address lines
- street
- postal/ZIP code
- campaign IDs/names
- product IDs/names
- channel
- offer
- campaign type
- target segment
- response count
- purchase count
- spend
- margin
- recency
- frequency
- prior campaign exposure
- historical engagement
- `pu_label` as an input feature
- `person_id`
- ethnicity
- religion
- occupation industry
- family yearly income
- any inferred/guessed demographic attribute

Campaign/sales data define **membership and label**, not prospect features.

---

## 7. Training grain and label

One training row = one distinct historical customer in the reconstructed cohort.

Canonical Phase 3 label:

- `1` = known positive
- `0` = unlabeled

There must be no duplicate `customer_id` in the internal reconstructed matrix.

`customer_id` may be retained temporarily as an internal row key for reconciliation/debugging, but it must be removed before preprocessing/model fit and must never be persisted inside public metrics or the serialized feature matrix.

Do not create a known-negative class.

---

## 8. Deterministic split

Use a customer-grain deterministic train/validation split.

Default:

- validation fraction: 20%
- random seed: 42
- stratify on PU label where valid

Requirements:

- no customer appears in both splits;
- both splits must contain positives and unlabeled examples;
- refuse training when the cohort is too small to create a meaningful split;
- record split counts in `model_runs`;
- do not use current wall-clock date in feature computation.

Optional cross-validation may be added as a diagnostic only if it remains bounded and deterministic. Do not turn Phase 3 into hyperparameter-search infrastructure.

---

## 9. Preprocessing contract

Build one fitted preprocessing pipeline and persist it with the model.

Recommended behavior:

### Numeric
- coerce/validate finite values;
- impute missing values using a statistic fitted on training data only;
- cap or reject impossible values according to explicit rules;
- scale where required by the base estimator.

### Categorical
- trim strings;
- normalize blank/null to `Unknown/Other`;
- impute missing values;
- one-hot encode;
- handle unseen future categories safely;
- do not fit encoders on validation data.

The entire preprocessing + estimator chain must be serializable/reloadable.

Persist feature names/counts and preprocessing decisions in metadata.

---

## 10. PU algorithms

### Required selected-model candidate: Elkan & Noto

Use `pulearn.ElkanotoPuClassifier` with a probabilistic, deterministic scikit-learn base estimator.

Recommended base estimator for the POC:

`LogisticRegression`

Reasons:

- probability output;
- fast enough for ~121K historical customers;
- interpretable;
- sparse one-hot compatibility;
- deterministic with fixed settings;
- easy to persist.

### Required diagnostic benchmark

Train a naive supervised logistic regression treating unlabeled as negative.

It must be named clearly, for example:

`NAIVE_PU_LABEL_BASELINE`

Its outputs are diagnostic only.

### Challenger

Attempt one bounded challenger if runtime is reasonable:

`BaggingPuClassifier`

Use a deterministic random seed and bounded estimator count.

If the challenger is too slow or incompatible, record a measured/documented `SKIPPED` result. Do not silently replace PU learning with the naive benchmark.

---

## 11. Evaluation philosophy

Because the true labels of unlabeled customers are unknown, ordinary supervised metrics do not mean what they normally mean.

Phase 3 must prioritize ranking/retrieval of held-out known positives.

Required metrics are frozen in `14_MODEL_EVALUATION_CONTRACT.md`.

At minimum record:

- held-out labeled-positive count;
- held-out unlabeled count;
- positive-label prevalence;
- observed-label ROC-AUC — explicitly labeled diagnostic;
- observed-label average precision/PR-AUC — explicitly labeled diagnostic;
- known-positive recall at top 5%, 10%, 20%;
- known-positive lift at top 5%, 10%, 20%;
- mean/median score for held-out positives;
- mean/median score for held-out unlabeled;
- score distribution/stability diagnostics;
- selected-model reason.

Do not report ordinary `accuracy` as the headline model-quality metric.

Do not call observed-label precision “true precision.”

---

## 12. Model selection

The selected POC model should be chosen primarily by:

1. valid PU semantics;
2. no leakage;
3. reproducibility;
4. held-out positive ranking/lift;
5. score separation/stability;
6. reasonable runtime;
7. artifact reloadability.

A challenger with a trivially higher observed-label accuracy must not win merely for that reason.

Store both candidate results if both run, but designate exactly one `SELECTED` model per model run.

---

## 13. Schema version 3

Add an additive, transactional, idempotent schema migration from version 2 to version 3.

Required new table:

`model_runs`

Minimum logical fields:

- `model_run_id` INTEGER PK
- `analysis_run_id` INTEGER NOT NULL FK to `historical_analysis_runs`
- `model_name`
- `created_at`
- `completed_at`
- `status` constrained to `RUNNING`, `COMPLETED`, `FAILED`
- `algorithm`
- `selected_candidate`
- `random_seed`
- `validation_fraction`
- `reconstructed_observation_count`
- `selected_customer_count`
- `positive_customer_count`
- `unlabeled_customer_count`
- `train_customer_count`
- `validation_customer_count`
- `train_positive_count`
- `validation_positive_count`
- `feature_contract_json`
- `preprocessing_json`
- `hyperparameters_json`
- `metrics_json`
- `library_versions_json`
- `artifact_path`
- `artifact_sha256`
- `error_message`

Constraints:

- nonnegative counts;
- selected/positive/unlabeled invariants where enforceable;
- validation fraction in `(0,1)`;
- no BLOB artifact storage;
- no customer ID list;
- no raw SQL;
- no training matrix persistence.

Recommended indexes:

- newest-first model run listing;
- `analysis_run_id`;
- status if measured usage justifies it.

---

## 14. Artifact contract

Model artifacts live outside SQLite, e.g.:

```text
artifacts/
  models/
    model_run_000001/
      pu_model.joblib
      metadata.json
```

Add runtime artifact directories to `.gitignore`.

The joblib artifact should contain only what is required to transform compatible prospect features and produce a score later:

- fitted preprocessing;
- selected fitted PU estimator;
- explicit feature-order metadata if required.

Do not include:

- source customer IDs;
- raw training rows;
- emails/phones/addresses;
- complete Phase 2 result snapshots when not necessary.

After writing:

1. reopen the artifact;
2. rescore a bounded validation fixture;
3. verify prediction equality/tolerance;
4. compute SHA-256;
5. persist checksum and relative artifact path.

Do not store absolute local paths in model metadata intended for future APIs.

---

## 15. Required CLI

Phase 3 must provide a functional CLI such as:

```powershell
python scripts/train_pu_model.py --analysis-run-id 10
```

Recommended options:

- `--analysis-run-id` required
- `--model-name`
- `--random-seed` default 42
- `--validation-fraction` default 0.20
- `--run-challenger` / `--no-run-challenger`
- `--database-path` only if existing project conventions permit it
- `--json` for machine-readable summary

The CLI must:

- initialize/migrate DB;
- reconstruct/reconcile;
- train;
- evaluate;
- persist;
- print the resulting `model_run_id`;
- return nonzero on failure.

No browser UI is required in Phase 3.

---

## 16. Explicitly out of scope

Do not implement:

- 5M demographic scoring
- `propensity_scores` table
- score percentiles/bands
- Audience Explorer
- target audience filtering
- campaign builder
- campaign audience persistence
- campaign export
- Model Training page activation
- background job/process-pool API workflow
- model retraining scheduler
- MLflow/model registry server
- fairness claims or causal claims
- online learning
- automatic hyperparameter tuning
- external marketing activation

---

## 17. Definition of Done

Phase 3 is complete only when:

1. schema v3 migration passes;
2. a completed Phase 2 analysis can be reconstructed exactly;
3. the feature matrix contains only frozen candidate features;
4. preprocessing is deterministic and leakage-safe;
5. a genuine PU model is fitted;
6. validation metrics are calculated under the frozen evaluation contract;
7. an artifact is persisted and reloaded successfully;
8. the same seed/input reproduces the same split and materially identical predictions/metrics;
9. failure paths persist safe status/diagnostics;
10. Phase 1 and 2 tests still pass;
11. no prospect scoring exists;
12. the Phase 4 handoff contract is complete.
