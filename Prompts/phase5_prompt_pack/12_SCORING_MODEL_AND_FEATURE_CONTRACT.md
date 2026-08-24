# Phase 5 Model and Prospect Feature Contract

Scoreable POC model must be COMPLETED, role-policy 2, evaluation-contract 2, PRIMARY_ROLE_GOVERNED, selected BAGGING_PU, exact feature contract v1 SHA `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`, verified artifact and matching selected candidate.

Use `load_verified_model_artifact`; do not directly load unverified files.

Exact raw order:

```text
age, gender, state, individual_yearly_income, marital_status,
education, employment_status, resident_status, resident_type,
family_member_count, type_of_employment
```

Query person_id separately as identity. Feature DataFrame excludes it.

Inference sequence:

```python
normalized = validate_and_normalize_feature_frame(raw_features)
matrix = artifact['preprocessor'].transform(normalized)
scores = positive_class_scores(artifact['estimator'], matrix, require_unit_interval=True)
```

Never fit/refit or learn demographic imputation/scaling/categories. Persisted one-hot unknown handling remains authoritative. Hard-invalid values fail the run rather than clipping.

POC age: accept demographic snapshot age under frozen 18–100 validation; document assumption, do not change contract hash or fabricate DOB.
