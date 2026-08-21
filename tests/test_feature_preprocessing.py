from __future__ import annotations

import hashlib
import importlib.metadata
import inspect
import json

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from app.ml import feature_contract, preprocessing
from app.ml.feature_contract import (
    CATEGORICAL_FEATURES,
    FEATURE_CONTRACT_JSON,
    FEATURE_CONTRACT_SHA256,
    NUMERIC_FEATURES,
    ORDERED_FEATURES,
    RAW_TRAINING_COLUMNS,
    UNKNOWN_CATEGORY,
    FeatureContractError,
    normalize_categorical_features,
    normalize_numeric_features,
    validate_and_normalize_feature_frame,
)
from app.ml.preprocessing import (
    FeatureSplitError,
    prepare_feature_matrices,
    split_customer_cohort,
)


EXPECTED_FINGERPRINT = "a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535"


def _raw_cohort(row_count: int = 100) -> pd.DataFrame:
    rows = []
    for index in range(row_count):
        rows.append(
            {
                "customer_id": f"CUS_{index:04d}",
                "pu_label": 1 if index % 5 == 0 else 0,
                "age": 20 + index % 60,
                "gender": " Female " if index % 2 else "Male",
                "state": ("Ohio", "Texas", "Maine")[index % 3],
                "individual_yearly_income": 30_000 + index * 1_000,
                "marital_status": "Single" if index % 2 else "Married",
                "education": "College",
                "employment_status": "Employed",
                "resident_status": "Citizen",
                "resident_type": "Owner" if index % 2 else "Renter",
                "family_member_count": 1 + index % 5,
                "type_of_employment": "Salaried",
            }
        )
    return pd.DataFrame(rows).loc[:, RAW_TRAINING_COLUMNS]


def _matrix_is_finite(matrix: object) -> bool:
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix)
    return bool(np.isfinite(values).all())


def test_frozen_feature_order_and_fingerprint_are_exact_and_stable() -> None:
    assert ORDERED_FEATURES == (
        "age",
        "gender",
        "state",
        "individual_yearly_income",
        "marital_status",
        "education",
        "employment_status",
        "resident_status",
        "resident_type",
        "family_member_count",
        "type_of_employment",
    )
    assert NUMERIC_FEATURES == (
        "age",
        "individual_yearly_income",
        "family_member_count",
    )
    assert CATEGORICAL_FEATURES == tuple(
        feature for feature in ORDERED_FEATURES if feature not in NUMERIC_FEATURES
    )
    assert FEATURE_CONTRACT_SHA256 == EXPECTED_FINGERPRINT
    assert hashlib.sha256(FEATURE_CONTRACT_JSON.encode("utf-8")).hexdigest() == (
        EXPECTED_FINGERPRINT
    )
    assert json.dumps(
        json.loads(FEATURE_CONTRACT_JSON),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ) == FEATURE_CONTRACT_JSON


def test_canonical_category_and_numeric_missing_normalization() -> None:
    categorical = pd.DataFrame(
        [
            {
                "gender": None,
                "state": "  ",
                "marital_status": " Single ",
                "education": pd.NA,
                "employment_status": "Employed",
                "resident_status": " Citizen ",
                "resident_type": "Owner",
                "type_of_employment": "Salaried",
            }
        ]
    ).loc[:, CATEGORICAL_FEATURES]
    numeric = pd.DataFrame(
        [{"age": " ", "individual_yearly_income": None, "family_member_count": pd.NA}]
    ).loc[:, NUMERIC_FEATURES]

    normalized_categories = normalize_categorical_features(categorical)
    normalized_numeric = normalize_numeric_features(numeric)

    assert normalized_categories.iloc[0].to_dict() == {
        "gender": UNKNOWN_CATEGORY,
        "state": UNKNOWN_CATEGORY,
        "marital_status": "Single",
        "education": UNKNOWN_CATEGORY,
        "employment_status": "Employed",
        "resident_status": "Citizen",
        "resident_type": "Owner",
        "type_of_employment": "Salaried",
    }
    assert normalized_numeric.isna().all().all()


@pytest.mark.parametrize(
    ("column", "invalid_value", "message"),
    (
        ("age", 17, "age must be between"),
        ("age", 101, "age must be between"),
        ("age", 35.5, "whole years"),
        ("age", "not-a-number", "non-numeric"),
        ("individual_yearly_income", -1, "nonnegative"),
        ("individual_yearly_income", np.inf, "finite"),
        ("family_member_count", 0, "at least 1"),
        ("family_member_count", 2.5, "integer"),
    ),
)
def test_invalid_numeric_values_fail_before_imputation(
    column: str,
    invalid_value: object,
    message: str,
) -> None:
    features = _raw_cohort(10).loc[:, ORDERED_FEATURES]
    features[column] = features[column].astype("object")
    features.loc[0, column] = invalid_value

    with pytest.raises(FeatureContractError, match=message):
        validate_and_normalize_feature_frame(features)


def test_split_is_deterministic_stratified_and_customer_separated() -> None:
    cohort = _raw_cohort()

    first = split_customer_cohort(cohort)
    repeated = split_customer_cohort(cohort.sample(frac=1, random_state=99))
    different_seed = split_customer_cohort(cohort, random_seed=7)

    assert first.train_customer_ids.tolist() == repeated.train_customer_ids.tolist()
    assert first.validation_customer_ids.tolist() == repeated.validation_customer_ids.tolist()
    assert first.validation_customer_ids.tolist() != (
        different_seed.validation_customer_ids.tolist()
    )
    assert len(first.train_customer_ids) == 80
    assert len(first.validation_customer_ids) == 20
    assert not set(first.train_customer_ids).intersection(first.validation_customer_ids)
    assert set(first.train_labels.unique()) == {0, 1}
    assert set(first.validation_labels.unique()) == {0, 1}
    assert tuple(first.train_features.columns) == ORDERED_FEATURES
    assert "customer_id" not in first.train_features
    assert "pu_label" not in first.train_features


def test_split_rejects_leakage_columns_duplicates_and_invalid_class_balance() -> None:
    extra_column = _raw_cohort(20).assign(campaign_id="CMP_LEAK")
    duplicate_customer = _raw_cohort(20)
    duplicate_customer.loc[1, "customer_id"] = duplicate_customer.loc[0, "customer_id"]
    one_class = _raw_cohort(20)
    one_class["pu_label"] = 0

    with pytest.raises(FeatureContractError, match="frozen raw training boundary"):
        split_customer_cohort(extra_column)
    with pytest.raises(FeatureSplitError, match="unique row"):
        split_customer_cohort(duplicate_customer)
    with pytest.raises(FeatureSplitError, match="known-positive and unlabeled"):
        split_customer_cohort(one_class)


def test_preprocessing_fits_only_training_and_handles_unseen_categories() -> None:
    split = split_customer_cohort(_raw_cohort())
    split.train_features.loc[:, "individual_yearly_income"] = 100.0
    split.train_features.loc[0, "individual_yearly_income"] = np.nan
    split.validation_features.loc[:, "individual_yearly_income"] = 1_000_000_000.0
    split.train_features.loc[:, "state"] = "Ohio"
    split.train_features.loc[0, "state"] = None
    split.train_features.loc[1, "state"] = "  "
    split.validation_features.loc[:, "state"] = "ValidationOnly"

    prepared = prepare_feature_matrices(split)
    encoder = prepared.preprocessor.named_transformers_["categorical"].named_steps[
        "encode"
    ]
    state_index = CATEGORICAL_FEATURES.index("state")
    state_categories = set(encoder.categories_[state_index])

    assert prepared.numeric_imputation_values["individual_yearly_income"] == 100.0
    assert "ValidationOnly" not in state_categories
    assert state_categories == {"Ohio", UNKNOWN_CATEGORY}
    assert prepared.train_matrix.shape[0] == len(split.train_labels)
    assert prepared.validation_matrix.shape[0] == len(split.validation_labels)
    assert prepared.train_matrix.shape[1] == prepared.transformed_feature_count
    assert prepared.validation_matrix.shape[1] == prepared.transformed_feature_count
    assert _matrix_is_finite(prepared.train_matrix)
    assert _matrix_is_finite(prepared.validation_matrix)


def test_numeric_missing_values_are_imputed_from_training_statistics() -> None:
    split = split_customer_cohort(_raw_cohort())
    split.train_features["age"] = split.train_features["age"].astype(float)
    split.train_features["family_member_count"] = split.train_features[
        "family_member_count"
    ].astype(float)
    split.train_features.loc[0, "age"] = np.nan
    split.train_features.loc[1, "family_member_count"] = np.nan
    split.validation_features["age"] = np.nan
    split.validation_features["individual_yearly_income"] = np.nan
    split.validation_features["family_member_count"] = np.nan

    prepared = prepare_feature_matrices(split)

    assert np.isfinite(
        np.asarray(list(prepared.numeric_imputation_values.values()), dtype=float)
    ).all()
    assert _matrix_is_finite(prepared.train_matrix)
    assert _matrix_is_finite(prepared.validation_matrix)


def test_entirely_missing_training_numeric_feature_is_rejected() -> None:
    split = split_customer_cohort(_raw_cohort())
    split.train_features["age"] = np.nan

    with pytest.raises(FeatureContractError, match="entirely missing.*age"):
        prepare_feature_matrices(split)


def test_preprocessing_metadata_is_bounded_and_contains_no_customer_values() -> None:
    split = split_customer_cohort(_raw_cohort())
    prepared = prepare_feature_matrices(split)

    assert prepared.raw_feature_names == ORDERED_FEATURES
    assert prepared.transformed_feature_count == len(prepared.transformed_feature_names)
    assert set(prepared.category_cardinalities) == set(CATEGORICAL_FEATURES)
    assert set(prepared.numeric_imputation_values) == set(NUMERIC_FEATURES)
    assert prepared.library_versions == {
        distribution: importlib.metadata.version(distribution)
        for distribution in ("numpy", "pandas", "scikit-learn")
    }
    assert prepared.feature_contract_sha256 == EXPECTED_FINGERPRINT
    serialized_metadata = json.dumps(
        {
            "raw_feature_names": prepared.raw_feature_names,
            "transformed_feature_names": prepared.transformed_feature_names,
            "category_cardinalities": prepared.category_cardinalities,
            "numeric_imputation_values": prepared.numeric_imputation_values,
            "library_versions": prepared.library_versions,
            "feature_contract_sha256": prepared.feature_contract_sha256,
        },
        sort_keys=True,
    )
    assert "CUS_" not in serialized_metadata


def test_feature_pipeline_has_no_current_date_or_model_fit_logic() -> None:
    source = inspect.getsource(feature_contract) + inspect.getsource(preprocessing)

    assert "date.today" not in source
    assert "datetime.now" not in source
    assert "pulearn" not in source
    assert "LogisticRegression" not in source
    assert ".predict" not in source
