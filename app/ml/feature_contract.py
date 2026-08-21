"""Frozen prospect-compatible raw feature contract for Phase 3."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np
import pandas as pd


FEATURE_CONTRACT_VERSION = "1"
UNKNOWN_CATEGORY = "Unknown/Other"
MINIMUM_ADULT_AGE = 18
MAXIMUM_ADULT_AGE = 100

ORDERED_FEATURES = (
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
NUMERIC_FEATURES = (
    "age",
    "individual_yearly_income",
    "family_member_count",
)
CATEGORICAL_FEATURES = tuple(
    feature for feature in ORDERED_FEATURES if feature not in NUMERIC_FEATURES
)
INTERNAL_COHORT_COLUMNS = ("customer_id", "pu_label")
RAW_TRAINING_COLUMNS = (*INTERNAL_COHORT_COLUMNS, *ORDERED_FEATURES)

FEATURE_CONTRACT = {
    "version": FEATURE_CONTRACT_VERSION,
    "ordered_features": list(ORDERED_FEATURES),
    "numeric_features": list(NUMERIC_FEATURES),
    "categorical_features": list(CATEGORICAL_FEATURES),
    "normalization": {
        "age": {
            "minimum": MINIMUM_ADULT_AGE,
            "maximum": MAXIMUM_ADULT_AGE,
            "missing": "allowed",
            "integer": True,
            "reference": "saved_contact_date_to",
        },
        "individual_yearly_income": {
            "minimum": 0,
            "finite": True,
            "missing": "allowed",
        },
        "family_member_count": {
            "minimum": 1,
            "missing": "allowed",
            "integer": True,
        },
        "categorical": {
            "null_or_blank": UNKNOWN_CATEGORY,
            "trim_surrounding_whitespace": True,
            "fuzzy_matching": False,
        },
    },
    "preprocessing": {
        "numeric": [
            "coerce_and_validate_finite",
            "median_impute_training_only",
            "standard_scale",
        ],
        "categorical": [
            "canonical_normalization",
            "one_hot_encode",
        ],
        "unknown_categories": "ignore",
        "remainder": "drop",
    },
}
FEATURE_CONTRACT_JSON = json.dumps(
    FEATURE_CONTRACT,
    ensure_ascii=False,
    allow_nan=False,
    sort_keys=True,
    separators=(",", ":"),
)
FEATURE_CONTRACT_SHA256 = hashlib.sha256(
    FEATURE_CONTRACT_JSON.encode("utf-8")
).hexdigest()


class FeatureContractError(ValueError):
    """Raised when raw values or columns violate the frozen feature contract."""


def validate_feature_columns(frame: pd.DataFrame) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise FeatureContractError("Raw model features must be provided as a DataFrame.")
    if tuple(frame.columns) != ORDERED_FEATURES:
        raise FeatureContractError(
            "Raw model features must exactly match the frozen feature order."
        )


def _missing_like_to_nan(value: Any) -> Any:
    if value is None or value is pd.NA:
        return np.nan
    if isinstance(value, str) and not value.strip():
        return np.nan
    try:
        if bool(pd.isna(value)):
            return np.nan
    except (TypeError, ValueError):
        pass
    return value


def normalize_numeric_features(frame: pd.DataFrame) -> pd.DataFrame:
    if tuple(frame.columns) != NUMERIC_FEATURES:
        raise FeatureContractError(
            "Numeric features must exactly match the frozen numeric feature order."
        )

    normalized = pd.DataFrame(index=frame.index)
    for column in NUMERIC_FEATURES:
        values = frame[column].map(_missing_like_to_nan)
        try:
            numeric = pd.to_numeric(values, errors="raise").astype(float)
        except (TypeError, ValueError) as exc:
            raise FeatureContractError(
                f"Feature {column} contains a non-numeric value."
            ) from exc
        present = numeric.dropna()
        if not np.isfinite(present.to_numpy(dtype=float)).all():
            raise FeatureContractError(f"Feature {column} must contain finite values.")
        normalized[column] = numeric

    age = normalized["age"].dropna()
    if not (age.mod(1) == 0).all():
        raise FeatureContractError("Feature age must contain whole years.")
    if not age.between(MINIMUM_ADULT_AGE, MAXIMUM_ADULT_AGE).all():
        raise FeatureContractError(
            f"Feature age must be between {MINIMUM_ADULT_AGE} and "
            f"{MAXIMUM_ADULT_AGE} when present."
        )
    income = normalized["individual_yearly_income"].dropna()
    if not (income >= 0).all():
        raise FeatureContractError(
            "Feature individual_yearly_income must be nonnegative."
        )
    family_count = normalized["family_member_count"].dropna()
    if not (family_count.mod(1) == 0).all():
        raise FeatureContractError("Feature family_member_count must be an integer.")
    if not (family_count >= 1).all():
        raise FeatureContractError(
            "Feature family_member_count must be at least 1 when present."
        )
    return normalized.loc[:, NUMERIC_FEATURES]


def normalize_categorical_features(frame: pd.DataFrame) -> pd.DataFrame:
    if tuple(frame.columns) != CATEGORICAL_FEATURES:
        raise FeatureContractError(
            "Categorical features must exactly match the frozen categorical order."
        )

    normalized = pd.DataFrame(index=frame.index)
    for column in CATEGORICAL_FEATURES:
        values: list[str] = []
        for value in frame[column]:
            if value is None or value is pd.NA:
                values.append(UNKNOWN_CATEGORY)
                continue
            try:
                if bool(pd.isna(value)):
                    values.append(UNKNOWN_CATEGORY)
                    continue
            except (TypeError, ValueError):
                pass
            if not isinstance(value, str):
                raise FeatureContractError(
                    f"Categorical feature {column} must contain strings or missing values."
                )
            trimmed = value.strip()
            values.append(trimmed if trimmed else UNKNOWN_CATEGORY)
        normalized[column] = pd.Series(values, index=frame.index, dtype="string")
    return normalized.loc[:, CATEGORICAL_FEATURES]


def validate_and_normalize_feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    validate_feature_columns(frame)
    numeric = normalize_numeric_features(
        frame.loc[:, NUMERIC_FEATURES]
    )
    categorical = normalize_categorical_features(
        frame.loc[:, CATEGORICAL_FEATURES]
    )
    normalized = pd.concat((numeric, categorical), axis="columns")
    return normalized.loc[:, ORDERED_FEATURES]


__all__ = (
    "CATEGORICAL_FEATURES",
    "FEATURE_CONTRACT",
    "FEATURE_CONTRACT_JSON",
    "FEATURE_CONTRACT_SHA256",
    "FEATURE_CONTRACT_VERSION",
    "FeatureContractError",
    "INTERNAL_COHORT_COLUMNS",
    "MAXIMUM_ADULT_AGE",
    "MINIMUM_ADULT_AGE",
    "NUMERIC_FEATURES",
    "ORDERED_FEATURES",
    "RAW_TRAINING_COLUMNS",
    "UNKNOWN_CATEGORY",
    "normalize_categorical_features",
    "normalize_numeric_features",
    "validate_and_normalize_feature_frame",
    "validate_feature_columns",
)
