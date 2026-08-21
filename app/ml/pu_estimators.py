"""Bounded estimator factories and score extraction for Phase 3 PU training."""

from __future__ import annotations

from typing import Any

import numpy as np
from pulearn import BaggingPuClassifier, ElkanotoPuClassifier
from sklearn.linear_model import LogisticRegression


ELKAN_NOTO_NAME = "ELKAN_NOTO_LOGISTIC"
NAIVE_BASELINE_NAME = "NAIVE_PU_LABEL_BASELINE"
BAGGING_PU_NAME = "BAGGING_PU"

ELKAN_HOLD_OUT_RATIO = 0.10
LOGISTIC_MAX_ITERATIONS = 500
CHALLENGER_ESTIMATORS = 10
CHALLENGER_MAX_ITERATIONS = 250


def build_logistic_estimator(
    *,
    random_seed: int,
    max_iterations: int = LOGISTIC_MAX_ITERATIONS,
) -> LogisticRegression:
    """Return the fixed sparse-compatible probabilistic base estimator."""
    return LogisticRegression(
        solver="liblinear",
        penalty="l2",
        C=1.0,
        class_weight=None,
        max_iter=max_iterations,
        random_state=random_seed,
    )


def build_elkan_noto_estimator(*, random_seed: int) -> ElkanotoPuClassifier:
    return ElkanotoPuClassifier(
        estimator=build_logistic_estimator(random_seed=random_seed),
        hold_out_ratio=ELKAN_HOLD_OUT_RATIO,
        random_state=random_seed,
    )


def build_naive_baseline_estimator(*, random_seed: int) -> LogisticRegression:
    return build_logistic_estimator(random_seed=random_seed)


def build_bagging_pu_estimator(*, random_seed: int) -> BaggingPuClassifier:
    return BaggingPuClassifier(
        estimator=build_logistic_estimator(
            random_seed=random_seed,
            max_iterations=CHALLENGER_MAX_ITERATIONS,
        ),
        n_estimators=CHALLENGER_ESTIMATORS,
        max_samples=1.0,
        max_features=1.0,
        bootstrap=True,
        bootstrap_features=False,
        oob_score=False,
        n_jobs=1,
        random_state=random_seed,
        verbose=0,
    )


def positive_class_scores(
    estimator: Any,
    matrix: Any,
    *,
    require_unit_interval: bool,
) -> np.ndarray:
    """Return finite positive-class scores under the candidate's score contract."""
    probabilities = np.asarray(estimator.predict_proba(matrix), dtype=float)
    if probabilities.ndim != 2 or probabilities.shape[0] != matrix.shape[0]:
        raise ValueError("Estimator returned an invalid probability matrix.")
    classes = np.asarray(estimator.classes_)
    positive_indices = np.flatnonzero(classes == 1)
    if len(positive_indices) != 1:
        raise ValueError("Estimator does not expose exactly one positive class.")
    scores = probabilities[:, int(positive_indices[0])]
    if not np.isfinite(scores).all():
        raise ValueError("Estimator returned non-finite positive-class scores.")
    if (scores < 0).any():
        raise ValueError("Estimator returned negative positive-class scores.")
    if require_unit_interval:
        tolerance = np.finfo(float).eps * 8
        if (scores > 1 + tolerance).any():
            raise ValueError("Estimator returned scores above the unit interval.")
        return np.clip(scores, 0.0, 1.0)
    return scores


def estimator_hyperparameters(estimator: Any) -> dict[str, Any]:
    """Return stable, JSON-safe hyperparameters without fitted state."""
    parameters = estimator.get_params(deep=True)
    return {
        key: value
        for key, value in sorted(parameters.items())
        if isinstance(value, (str, int, float, bool, type(None)))
    }


__all__ = (
    "BAGGING_PU_NAME",
    "CHALLENGER_ESTIMATORS",
    "ELKAN_NOTO_NAME",
    "NAIVE_BASELINE_NAME",
    "build_bagging_pu_estimator",
    "build_elkan_noto_estimator",
    "build_naive_baseline_estimator",
    "estimator_hyperparameters",
    "positive_class_scores",
)
