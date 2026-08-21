"""Governed PU candidates with mandatory Bagging PU as the primary model."""

from __future__ import annotations

import math
import time
import warnings
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from scipy import sparse

from app.ml.feature_contract import FEATURE_CONTRACT_SHA256, ORDERED_FEATURES
from app.ml.model_roles import (
    CHALLENGER_1_ROLE,
    DIAGNOSTIC_CONTROL_ROLE,
    PRIMARY_ROLE,
    CandidateRole,
)
from app.ml.preprocessing import CustomerCohortSplit, PreparedFeatureMatrices
from app.ml.pu_estimators import (
    BAGGING_PU_NAME,
    ELKAN_HOLD_OUT_RATIO,
    ELKAN_NOTO_NAME,
    NAIVE_BASELINE_NAME,
    build_bagging_pu_estimator,
    build_elkan_noto_estimator,
    build_naive_baseline_estimator,
    estimator_hyperparameters,
    positive_class_scores,
)


MINIMUM_POSITIVE_COUNT = 5
MINIMUM_UNLABELED_COUNT = 5
MAXIMUM_ELKAN_DENSE_BYTES = 512 * 1024 * 1024

CandidateStatus = Literal["FITTED", "SKIPPED_DISABLED", "SKIPPED_INCOMPATIBLE"]


class TrainingAlgorithmError(RuntimeError):
    """Raised when the required governed training contract cannot be satisfied."""


@dataclass(frozen=True)
class CandidateTrainingResult:
    name: str
    candidate_role: CandidateRole
    status: CandidateStatus
    is_genuine_pu: bool
    estimator: Any | None
    fit_seconds: float
    score_seconds: float
    validation_scores: np.ndarray | None
    warnings: tuple[str, ...]
    algorithm_metadata: dict[str, Any]
    skip_reason: str | None = None


@dataclass(frozen=True)
class TrainingCandidateSet:
    primary: CandidateTrainingResult
    challenger_1: CandidateTrainingResult
    diagnostic_control: CandidateTrainingResult

    @property
    def bagging_pu(self) -> CandidateTrainingResult:
        """Compatibility alias for callers written under role-policy v1."""
        return self.primary

    @property
    def elkan_noto(self) -> CandidateTrainingResult:
        """Compatibility alias for callers written under role-policy v1."""
        return self.challenger_1

    @property
    def naive_diagnostic(self) -> CandidateTrainingResult:
        """Compatibility alias for callers written under role-policy v1."""
        return self.diagnostic_control


def _validate_training_inputs(
    prepared: PreparedFeatureMatrices,
    split: CustomerCohortSplit,
) -> np.ndarray:
    if not isinstance(prepared, PreparedFeatureMatrices) or not isinstance(
        split, CustomerCohortSplit
    ):
        raise TrainingAlgorithmError(
            "PU training requires the validated Step 3 matrices and split."
        )
    if prepared.raw_feature_names != ORDERED_FEATURES:
        raise TrainingAlgorithmError("Raw feature metadata does not match the contract.")
    if prepared.feature_contract_sha256 != FEATURE_CONTRACT_SHA256:
        raise TrainingAlgorithmError("Feature contract fingerprint does not match.")
    if prepared.train_matrix.shape[0] != len(split.train_labels):
        raise TrainingAlgorithmError("Training matrix and label counts do not match.")
    if prepared.validation_matrix.shape[0] != len(split.validation_labels):
        raise TrainingAlgorithmError("Validation matrix and label counts do not match.")
    if prepared.train_matrix.shape[1] != prepared.transformed_feature_count:
        raise TrainingAlgorithmError("Training feature count does not match metadata.")
    if prepared.validation_matrix.shape[1] != prepared.transformed_feature_count:
        raise TrainingAlgorithmError("Validation feature count does not match metadata.")

    labels = np.asarray(split.train_labels, dtype=np.int8)
    if not set(np.unique(labels)) <= {0, 1}:
        raise TrainingAlgorithmError(
            "Training labels must use 1 for known positive and 0 for unlabeled."
        )
    positive_count = int(np.sum(labels == 1))
    unlabeled_count = int(np.sum(labels == 0))
    if positive_count == 0 or unlabeled_count == 0:
        raise TrainingAlgorithmError(
            "PU training requires both known-positive and unlabeled customers."
        )
    if positive_count < MINIMUM_POSITIVE_COUNT:
        raise TrainingAlgorithmError(
            f"PU training requires at least {MINIMUM_POSITIVE_COUNT} known-positive "
            "training customers."
        )
    if unlabeled_count < MINIMUM_UNLABELED_COUNT:
        raise TrainingAlgorithmError(
            f"PU training requires at least {MINIMUM_UNLABELED_COUNT} unlabeled "
            "training customers."
        )
    return labels


def _warning_messages(captured: list[warnings.WarningMessage]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(f"{item.category.__name__}: {item.message}" for item in captured)
    )


def _bounded_dense_training_matrix(matrix: Any) -> tuple[np.ndarray, int]:
    dense_bytes = int(
        matrix.shape[0] * matrix.shape[1] * np.dtype(np.float64).itemsize
    )
    if dense_bytes > MAXIMUM_ELKAN_DENSE_BYTES:
        raise TrainingAlgorithmError(
            "Elkan-Noto dense compatibility conversion exceeds the bounded memory limit."
        )
    dense = matrix.toarray() if sparse.issparse(matrix) else np.asarray(matrix)
    dense = np.asarray(dense, dtype=np.float64)
    if not np.isfinite(dense).all():
        raise TrainingAlgorithmError("Training matrix contains non-finite values.")
    return dense, dense_bytes


def _elkan_holdout_has_positive(labels: np.ndarray, *, random_seed: int) -> bool:
    indices = np.arange(len(labels))
    np.random.RandomState(random_seed).shuffle(indices)
    holdout_size = int(math.ceil(len(labels) * ELKAN_HOLD_OUT_RATIO))
    return bool(np.any(labels[indices[:holdout_size]] == 1))


def _train_bagging_primary(
    prepared: PreparedFeatureMatrices,
    labels: np.ndarray,
    *,
    random_seed: int,
) -> CandidateTrainingResult:
    estimator = build_bagging_pu_estimator(random_seed=random_seed)
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        fit_started = time.perf_counter()
        try:
            estimator.fit(prepared.train_matrix, labels)
        except Exception as exc:
            raise TrainingAlgorithmError(
                "Mandatory Bagging PU primary training failed."
            ) from exc
        fit_seconds = time.perf_counter() - fit_started
        score_started = time.perf_counter()
        try:
            scores = positive_class_scores(
                estimator, prepared.validation_matrix, require_unit_interval=True
            )
        except Exception as exc:
            raise TrainingAlgorithmError(
                "Mandatory Bagging PU primary validation scoring failed."
            ) from exc
        score_seconds = time.perf_counter() - score_started

    return CandidateTrainingResult(
        name=BAGGING_PU_NAME,
        candidate_role=PRIMARY_ROLE,
        status="FITTED",
        is_genuine_pu=True,
        estimator=estimator,
        fit_seconds=fit_seconds,
        score_seconds=score_seconds,
        validation_scores=scores,
        warnings=_warning_messages(captured),
        algorithm_metadata={
            "algorithm": "pulearn.BaggingPuClassifier",
            "base_estimator": "sklearn.linear_model.LogisticRegression",
            "candidate_role": PRIMARY_ROLE,
            "eligible_for_official_selection": True,
            "label_input_contract": {"known_positive": 1, "unlabeled": 0},
            "bounded_cpu_jobs": 1,
            "hyperparameters": estimator_hyperparameters(estimator),
        },
    )


def _train_elkan_challenger(
    prepared: PreparedFeatureMatrices,
    labels: np.ndarray,
    *,
    random_seed: int,
) -> CandidateTrainingResult:
    if not _elkan_holdout_has_positive(labels, random_seed=random_seed):
        raise TrainingAlgorithmError(
            "The deterministic Elkan-Noto holdout contains no known-positive customer."
        )
    dense_train, dense_bytes = _bounded_dense_training_matrix(prepared.train_matrix)
    pulearn_labels = np.where(labels == 1, 1, -1).astype(np.int8)
    estimator = build_elkan_noto_estimator(random_seed=random_seed)
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        fit_started = time.perf_counter()
        try:
            estimator.fit(dense_train, pulearn_labels)
        except Exception as exc:
            raise TrainingAlgorithmError(
                "Elkan-Noto challenger training failed with the tested dependencies."
            ) from exc
        fit_seconds = time.perf_counter() - fit_started
        c_value = float(estimator.c)
        if not math.isfinite(c_value) or not 0 < c_value <= 1:
            raise TrainingAlgorithmError(
                "Elkan-Noto returned an invalid labeling propensity estimate."
            )
        score_started = time.perf_counter()
        try:
            scores = positive_class_scores(
                estimator, prepared.validation_matrix, require_unit_interval=False
            )
        except Exception as exc:
            raise TrainingAlgorithmError(
                "Elkan-Noto challenger validation scoring failed."
            ) from exc
        score_seconds = time.perf_counter() - score_started

    return CandidateTrainingResult(
        name=ELKAN_NOTO_NAME,
        candidate_role=CHALLENGER_1_ROLE,
        status="FITTED",
        is_genuine_pu=True,
        estimator=estimator,
        fit_seconds=fit_seconds,
        score_seconds=score_seconds,
        validation_scores=scores,
        warnings=_warning_messages(captured),
        algorithm_metadata={
            "algorithm": "pulearn.ElkanotoPuClassifier",
            "base_estimator": "sklearn.linear_model.LogisticRegression",
            "candidate_role": CHALLENGER_1_ROLE,
            "eligible_for_official_selection": False,
            "label_input_contract": {"known_positive": 1, "unlabeled": 0},
            "pulearn_label_adapter": {"known_positive": 1, "unlabeled": -1},
            "hold_out_ratio": ELKAN_HOLD_OUT_RATIO,
            "labeling_propensity_c": c_value,
            "score_contract": (
                "finite_nonnegative_pulearn_c_corrected; may exceed 1; "
                "no clipping so ranking is preserved"
            ),
            "dense_compatibility_bytes": dense_bytes,
            "hyperparameters": estimator_hyperparameters(estimator),
        },
    )


def _skipped_elkan_challenger(
    *, status: CandidateStatus, reason: str
) -> CandidateTrainingResult:
    return CandidateTrainingResult(
        name=ELKAN_NOTO_NAME,
        candidate_role=CHALLENGER_1_ROLE,
        status=status,
        is_genuine_pu=True,
        estimator=None,
        fit_seconds=0.0,
        score_seconds=0.0,
        validation_scores=None,
        warnings=(),
        algorithm_metadata={
            "algorithm": "pulearn.ElkanotoPuClassifier",
            "candidate_role": CHALLENGER_1_ROLE,
            "eligible_for_official_selection": False,
            "label_input_contract": {"known_positive": 1, "unlabeled": 0},
        },
        skip_reason=reason,
    )


def _train_naive_diagnostic(
    prepared: PreparedFeatureMatrices,
    labels: np.ndarray,
    *,
    random_seed: int,
) -> CandidateTrainingResult:
    estimator = build_naive_baseline_estimator(random_seed=random_seed)
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        fit_started = time.perf_counter()
        try:
            estimator.fit(prepared.train_matrix, labels)
        except Exception as exc:
            raise TrainingAlgorithmError("Naive diagnostic training failed.") from exc
        fit_seconds = time.perf_counter() - fit_started
        score_started = time.perf_counter()
        try:
            scores = positive_class_scores(
                estimator, prepared.validation_matrix, require_unit_interval=True
            )
        except Exception as exc:
            raise TrainingAlgorithmError("Naive diagnostic scoring failed.") from exc
        score_seconds = time.perf_counter() - score_started

    return CandidateTrainingResult(
        name=NAIVE_BASELINE_NAME,
        candidate_role=DIAGNOSTIC_CONTROL_ROLE,
        status="FITTED",
        is_genuine_pu=False,
        estimator=estimator,
        fit_seconds=fit_seconds,
        score_seconds=score_seconds,
        validation_scores=scores,
        warnings=_warning_messages(captured),
        algorithm_metadata={
            "algorithm": "sklearn.linear_model.LogisticRegression",
            "candidate_role": DIAGNOSTIC_CONTROL_ROLE,
            "role": DIAGNOSTIC_CONTROL_ROLE,
            "is_genuine_pu": False,
            "unlabeled_treatment": (
                "temporarily_treated_as_negative_for_diagnostic_only"
            ),
            "eligible_for_selection": False,
            "eligible_for_official_selection": False,
            "label_input_contract": {"known_positive": 1, "unlabeled": 0},
            "hyperparameters": estimator_hyperparameters(estimator),
        },
    )


def train_pu_candidates(
    prepared: PreparedFeatureMatrices,
    split: CustomerCohortSplit,
    *,
    random_seed: int | None = None,
    run_elkan_challenger: bool = True,
) -> TrainingCandidateSet:
    """Fit the mandatory primary, optional challenger, and diagnostic control."""
    seed = split.random_seed if random_seed is None else random_seed
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TrainingAlgorithmError("random_seed must be an integer.")
    if not isinstance(run_elkan_challenger, bool):
        raise TrainingAlgorithmError("run_elkan_challenger must be a boolean.")
    labels = _validate_training_inputs(prepared, split)

    primary = _train_bagging_primary(prepared, labels, random_seed=seed)
    if run_elkan_challenger:
        try:
            challenger = _train_elkan_challenger(prepared, labels, random_seed=seed)
        except TrainingAlgorithmError as exc:
            challenger = _skipped_elkan_challenger(
                status="SKIPPED_INCOMPATIBLE",
                reason=(
                    "Elkan-Noto challenger was incompatible with the bounded "
                    f"configuration: {exc}"
                ),
            )
    else:
        challenger = _skipped_elkan_challenger(
            status="SKIPPED_DISABLED",
            reason="Elkan-Noto challenger was disabled by the caller.",
        )
    diagnostic = _train_naive_diagnostic(prepared, labels, random_seed=seed)
    return TrainingCandidateSet(
        primary=primary,
        challenger_1=challenger,
        diagnostic_control=diagnostic,
    )


__all__ = (
    "CandidateTrainingResult",
    "TrainingAlgorithmError",
    "TrainingCandidateSet",
    "train_pu_candidates",
)
