"""Deterministic customer splitting and train-only feature preprocessing."""

from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.utils.validation import check_is_fitted

from app.ml.feature_contract import (
    CATEGORICAL_FEATURES,
    FEATURE_CONTRACT_JSON,
    FEATURE_CONTRACT_SHA256,
    FEATURE_CONTRACT_VERSION,
    NUMERIC_FEATURES,
    ORDERED_FEATURES,
    RAW_TRAINING_COLUMNS,
    FeatureContractError,
    normalize_categorical_features,
    normalize_numeric_features,
    validate_and_normalize_feature_frame,
)


DEFAULT_RANDOM_SEED = 42
DEFAULT_VALIDATION_FRACTION = 0.20


class FeatureSplitError(ValueError):
    """Raised when a customer cohort cannot produce a valid PU split."""


class NumericContractTransformer(TransformerMixin, BaseEstimator):
    """Coerce and hard-validate numeric values before train-only imputation."""

    def fit(self, values: Any, target: Any = None) -> NumericContractTransformer:
        frame = self._as_frame(values)
        normalize_numeric_features(frame)
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        self.n_features_in_ = len(self.feature_names_in_)
        return self

    def transform(self, values: Any) -> pd.DataFrame:
        check_is_fitted(self, "feature_names_in_")
        frame = self._as_frame(values)
        if tuple(frame.columns) != tuple(self.feature_names_in_):
            raise FeatureContractError("Numeric feature order changed after fitting.")
        return normalize_numeric_features(frame)

    def get_feature_names_out(self, input_features: Any = None) -> np.ndarray:
        check_is_fitted(self, "feature_names_in_")
        return np.asarray(
            self.feature_names_in_ if input_features is None else input_features,
            dtype=object,
        )

    @staticmethod
    def _as_frame(values: Any) -> pd.DataFrame:
        if isinstance(values, pd.DataFrame):
            return values.copy()
        return pd.DataFrame(values, columns=NUMERIC_FEATURES)


class CategoricalContractTransformer(TransformerMixin, BaseEstimator):
    """Apply the frozen null/blank/trim categorical normalization."""

    def fit(self, values: Any, target: Any = None) -> CategoricalContractTransformer:
        frame = self._as_frame(values)
        normalize_categorical_features(frame)
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        self.n_features_in_ = len(self.feature_names_in_)
        return self

    def transform(self, values: Any) -> pd.DataFrame:
        check_is_fitted(self, "feature_names_in_")
        frame = self._as_frame(values)
        if tuple(frame.columns) != tuple(self.feature_names_in_):
            raise FeatureContractError("Categorical feature order changed after fitting.")
        return normalize_categorical_features(frame)

    def get_feature_names_out(self, input_features: Any = None) -> np.ndarray:
        check_is_fitted(self, "feature_names_in_")
        return np.asarray(
            self.feature_names_in_ if input_features is None else input_features,
            dtype=object,
        )

    @staticmethod
    def _as_frame(values: Any) -> pd.DataFrame:
        if isinstance(values, pd.DataFrame):
            return values.copy()
        return pd.DataFrame(values, columns=CATEGORICAL_FEATURES)


@dataclass(frozen=True)
class CustomerCohortSplit:
    random_seed: int
    validation_fraction: float
    train_customer_ids: pd.Series
    validation_customer_ids: pd.Series
    train_features: pd.DataFrame
    validation_features: pd.DataFrame
    train_labels: pd.Series
    validation_labels: pd.Series


@dataclass(frozen=True)
class PreparedFeatureMatrices:
    preprocessor: ColumnTransformer
    train_matrix: Any
    validation_matrix: Any
    raw_feature_names: tuple[str, ...]
    transformed_feature_names: tuple[str, ...]
    category_cardinalities: dict[str, int]
    numeric_imputation_values: dict[str, float]
    library_versions: dict[str, str]
    feature_contract_version: str
    feature_contract_json: str
    feature_contract_sha256: str

    @property
    def transformed_feature_count(self) -> int:
        return len(self.transformed_feature_names)


def split_customer_cohort(
    frame: pd.DataFrame,
    *,
    validation_fraction: float = DEFAULT_VALIDATION_FRACTION,
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> CustomerCohortSplit:
    """Create a deterministic stratified split at unique-customer grain."""
    if isinstance(random_seed, bool) or not isinstance(random_seed, int):
        raise FeatureSplitError("random_seed must be an integer.")
    if (
        isinstance(validation_fraction, bool)
        or not isinstance(validation_fraction, (int, float))
        or not np.isfinite(validation_fraction)
        or not 0 < float(validation_fraction) < 1
    ):
        raise FeatureSplitError("validation_fraction must be between 0 and 1.")
    if not isinstance(frame, pd.DataFrame) or tuple(frame.columns) != RAW_TRAINING_COLUMNS:
        raise FeatureContractError(
            "Customer cohort columns must exactly match the frozen raw training boundary."
        )
    if frame["customer_id"].isna().any() or not frame["customer_id"].is_unique:
        raise FeatureSplitError("Customer cohort must contain one unique row per customer.")
    if frame["pu_label"].isna().any() or set(frame["pu_label"].unique()) != {0, 1}:
        raise FeatureSplitError(
            "Customer cohort must contain known-positive and unlabeled rows."
        )

    ordered = frame.sort_values("customer_id", kind="stable").reset_index(drop=True)
    normalized_features = validate_and_normalize_feature_frame(
        ordered.loc[:, ORDERED_FEATURES]
    )
    normalized = pd.concat(
        [ordered.loc[:, ["customer_id", "pu_label"]], normalized_features],
        axis=1,
    )
    try:
        train_rows, validation_rows = train_test_split(
            normalized,
            test_size=float(validation_fraction),
            random_state=random_seed,
            shuffle=True,
            stratify=normalized["pu_label"],
        )
    except ValueError as exc:
        raise FeatureSplitError(
            "Customer cohort is too small for a stratified train/validation split."
        ) from exc

    train_rows = train_rows.reset_index(drop=True)
    validation_rows = validation_rows.reset_index(drop=True)
    for split_name, rows in (
        ("training", train_rows),
        ("validation", validation_rows),
    ):
        if set(rows["pu_label"].unique()) != {0, 1}:
            raise FeatureSplitError(
                f"The {split_name} split must contain positives and unlabeled rows."
            )

    train_ids = train_rows["customer_id"].astype("string")
    validation_ids = validation_rows["customer_id"].astype("string")
    if set(train_ids).intersection(validation_ids):
        raise FeatureSplitError("A customer appears in both training and validation.")

    return CustomerCohortSplit(
        random_seed=random_seed,
        validation_fraction=float(validation_fraction),
        train_customer_ids=train_ids,
        validation_customer_ids=validation_ids,
        train_features=train_rows.loc[:, ORDERED_FEATURES].reset_index(drop=True),
        validation_features=validation_rows.loc[:, ORDERED_FEATURES].reset_index(drop=True),
        train_labels=train_rows["pu_label"].astype("Int8"),
        validation_labels=validation_rows["pu_label"].astype("Int8"),
    )


def build_feature_preprocessor() -> ColumnTransformer:
    numeric_pipeline = Pipeline(
        steps=(
            ("contract", NumericContractTransformer()),
            ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scale", StandardScaler()),
        )
    )
    categorical_pipeline = Pipeline(
        steps=(
            ("contract", CategoricalContractTransformer()),
            (
                "encode",
                OneHotEncoder(
                    handle_unknown="ignore",
                    sparse_output=True,
                    dtype=np.float64,
                ),
            ),
        )
    )
    return ColumnTransformer(
        transformers=(
            ("numeric", numeric_pipeline, list(NUMERIC_FEATURES)),
            ("categorical", categorical_pipeline, list(CATEGORICAL_FEATURES)),
        ),
        remainder="drop",
        sparse_threshold=1.0,
        verbose_feature_names_out=True,
    )


def _assert_finite_matrix(matrix: Any, *, label: str) -> None:
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix)
    if not np.isfinite(values).all():
        raise FeatureContractError(f"The transformed {label} matrix is not finite.")


def prepare_feature_matrices(split: CustomerCohortSplit) -> PreparedFeatureMatrices:
    """Fit on training only, then transform validation with the fitted object."""
    validate_and_normalize_feature_frame(split.train_features)
    validate_and_normalize_feature_frame(split.validation_features)
    normalized_numeric_train = normalize_numeric_features(
        split.train_features.loc[:, NUMERIC_FEATURES]
    )
    empty_numeric = [
        column for column in NUMERIC_FEATURES if normalized_numeric_train[column].isna().all()
    ]
    if empty_numeric:
        raise FeatureContractError(
            "Training data cannot impute an entirely missing numeric feature: "
            + ", ".join(empty_numeric)
            + "."
        )

    preprocessor = build_feature_preprocessor()
    train_matrix = preprocessor.fit_transform(split.train_features, split.train_labels)
    validation_matrix = preprocessor.transform(split.validation_features)
    _assert_finite_matrix(train_matrix, label="training")
    _assert_finite_matrix(validation_matrix, label="validation")

    transformed_names = tuple(str(name) for name in preprocessor.get_feature_names_out())
    categorical_encoder = preprocessor.named_transformers_["categorical"].named_steps[
        "encode"
    ]
    category_cardinalities = {
        feature: len(categories)
        for feature, categories in zip(
            CATEGORICAL_FEATURES,
            categorical_encoder.categories_,
            strict=True,
        )
    }
    imputer = preprocessor.named_transformers_["numeric"].named_steps["impute"]
    numeric_imputation_values = {
        feature: float(value)
        for feature, value in zip(NUMERIC_FEATURES, imputer.statistics_, strict=True)
    }
    library_versions = {
        distribution: importlib.metadata.version(distribution)
        for distribution in ("numpy", "pandas", "scikit-learn")
    }

    return PreparedFeatureMatrices(
        preprocessor=preprocessor,
        train_matrix=train_matrix,
        validation_matrix=validation_matrix,
        raw_feature_names=ORDERED_FEATURES,
        transformed_feature_names=transformed_names,
        category_cardinalities=category_cardinalities,
        numeric_imputation_values=numeric_imputation_values,
        library_versions=library_versions,
        feature_contract_version=FEATURE_CONTRACT_VERSION,
        feature_contract_json=FEATURE_CONTRACT_JSON,
        feature_contract_sha256=FEATURE_CONTRACT_SHA256,
    )


__all__ = (
    "CustomerCohortSplit",
    "DEFAULT_RANDOM_SEED",
    "DEFAULT_VALIDATION_FRACTION",
    "FeatureSplitError",
    "PreparedFeatureMatrices",
    "build_feature_preprocessor",
    "prepare_feature_matrices",
    "split_customer_cohort",
)
