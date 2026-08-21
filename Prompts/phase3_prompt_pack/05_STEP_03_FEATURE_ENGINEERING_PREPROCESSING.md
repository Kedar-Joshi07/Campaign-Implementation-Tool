# Step 3 — Frozen Feature Contract and Leakage-Safe Preprocessing

## Objective

Transform the reconciled customer-grain raw matrix into a deterministic model-ready matrix without fitting the PU estimator.

Read `13_ML_FEATURE_CONTRACT.md` first.

## Create a feature-contract module

Recommended module:

`app/ml/feature_contract.py`

It should own:

- exact feature names;
- feature types;
- feature order;
- normalization rules;
- valid/impossible ranges;
- a feature-contract version string/hash.

Do not scatter feature lists across services.

## Recommended preprocessing

Use scikit-learn `ColumnTransformer`.

### Numeric features

- age
- individual_yearly_income
- family_member_count

Pipeline:

1. explicit numeric coercion/finite check;
2. replace invalid missing-like values with `NaN`;
3. impute median fitted from training split only;
4. scale using `StandardScaler` for logistic-regression-based estimators.

Hard validation before imputation:

- age outside a clearly documented plausible adult range should not silently become a normal value;
- income < 0 is invalid;
- family member count < 1 is invalid.

The source schema already constrains many values; preprocessing must still fail cleanly if corrupted data bypasses those assumptions.

### Categorical features

- gender
- state
- marital_status
- education
- employment_status
- resident_status
- resident_type
- type_of_employment

Pipeline:

1. convert null/blank to `Unknown/Other`;
2. trim;
3. impute stable fallback if required;
4. one-hot encode with safe unknown-category behavior.

For future scoring, unseen demographic categories must not crash transformation.

## Train/validation split

Implement a deterministic helper:

```text
split_customer_cohort(...)
```

Defaults:

- validation = 0.20
- random seed = 42
- stratify by PU label

Fit the preprocessor on training only.

Then transform validation using the already-fitted preprocessor.

## Critical leakage tests

Prove:

- validation values do not affect imputer medians;
- validation-only categories do not enter training-fitted encoder vocabulary;
- `customer_id` is absent before `fit_transform`;
- PU label is not inside X;
- campaign/product/sales fields cannot be passed;
- current date is not used.

## Feature-name metadata

After fit, derive and record:

- raw feature names;
- transformed feature count;
- transformed feature names when safely available;
- category cardinalities;
- numeric imputation values;
- preprocessing library versions.

Do not persist raw customer values.

## Feature-contract fingerprint

Create a deterministic SHA-256 fingerprint from canonical JSON describing:

- feature contract version;
- ordered raw features;
- numeric/categorical classification;
- preprocessing configuration.

This fingerprint becomes part of model metadata and the later prospect-scoring compatibility check.

## Tests

Add tests for:

- exact frozen raw feature set/order;
- unknown category transformation;
- null/blank categories;
- numeric missing values;
- invalid numeric values;
- deterministic split;
- customer separation between splits;
- positive/unlabeled presence in both splits;
- same seed => same split;
- different seed => generally different split;
- train-only preprocessing fit;
- feature fingerprint stability.

## Do not do

- no PU estimator yet;
- no model selection;
- no demographic scoring;
- no persistence of a customer-level training CSV.

## Exit criteria

A valid reconstructed cohort can be split and transformed reproducibly into train/validation matrices using only prospect-compatible features.
