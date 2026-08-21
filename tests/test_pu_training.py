from __future__ import annotations

import warnings
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from pulearn import ElkanotoPuClassifier
from sklearn.base import BaseEstimator

from app.ml import training as training_module
from app.ml.feature_contract import ORDERED_FEATURES, RAW_TRAINING_COLUMNS
from app.ml.preprocessing import prepare_feature_matrices, split_customer_cohort
from app.ml.pu_estimators import (
    BAGGING_PU_NAME,
    ELKAN_NOTO_NAME,
    NAIVE_BASELINE_NAME,
)
from app.ml.training import TrainingAlgorithmError, train_pu_candidates


def _signal_cohort(row_count: int = 120) -> pd.DataFrame:
    rows = []
    for index in range(row_count):
        positive = index % 5 == 0
        rows.append(
            {
                "customer_id": f"CUS_SIGNAL_{index:04d}",
                "pu_label": int(positive),
                "age": 52 + index % 8 if positive else 22 + index % 28,
                "gender": "Female" if index % 2 else "Male",
                "state": "SignalState" if positive else f"State{index % 4}",
                "individual_yearly_income": (
                    140_000 + index * 100 if positive else 28_000 + index * 100
                ),
                "marital_status": "Married" if positive else "Single",
                "education": "Graduate" if positive else "College",
                "employment_status": "Employed",
                "resident_status": "Citizen",
                "resident_type": "Owner" if positive else "Renter",
                "family_member_count": 4 if positive else 1 + index % 2,
                "type_of_employment": "Salaried",
            }
        )
    return pd.DataFrame(rows).loc[:, RAW_TRAINING_COLUMNS]


def _prepared_signal_fixture():
    split = split_customer_cohort(_signal_cohort())
    prepared = prepare_feature_matrices(split)
    return split, prepared


def _assert_score_contract(
    scores: np.ndarray,
    expected_length: int,
    *,
    require_unit_interval: bool,
) -> None:
    assert scores.shape == (expected_length,)
    assert np.isfinite(scores).all()
    assert (scores >= 0).all()
    if require_unit_interval:
        assert (scores <= 1).all()
    assert np.unique(scores).size > 1


def test_required_pu_candidates_and_diagnostic_baseline_fit_and_score() -> None:
    split, prepared = _prepared_signal_fixture()

    candidates = train_pu_candidates(prepared, split, run_challenger=True)

    primary = candidates.elkan_noto
    assert primary.name == ELKAN_NOTO_NAME
    assert primary.status == "FITTED"
    assert primary.is_genuine_pu is True
    assert isinstance(primary.estimator, ElkanotoPuClassifier)
    assert 0 < primary.algorithm_metadata["labeling_propensity_c"] <= 1
    assert primary.algorithm_metadata["pulearn_label_adapter"] == {
        "known_positive": 1,
        "unlabeled": -1,
    }
    _assert_score_contract(
        primary.validation_scores,
        len(split.validation_labels),
        require_unit_interval=False,
    )

    naive = candidates.naive_diagnostic
    assert naive.name == NAIVE_BASELINE_NAME
    assert naive.status == "FITTED"
    assert naive.is_genuine_pu is False
    assert naive.algorithm_metadata["role"] == "diagnostic_only_not_pu_learning"
    assert "unlabeled_treated_as_negative" in naive.algorithm_metadata["known_limitation"]
    _assert_score_contract(
        naive.validation_scores,
        len(split.validation_labels),
        require_unit_interval=True,
    )

    challenger = candidates.bagging_pu
    assert challenger.name == BAGGING_PU_NAME
    assert challenger.status == "FITTED"
    assert challenger.is_genuine_pu is True
    assert challenger.algorithm_metadata["bounded_cpu_jobs"] == 1
    _assert_score_contract(
        challenger.validation_scores,
        len(split.validation_labels),
        require_unit_interval=True,
    )


def test_same_seed_reproduces_all_candidate_scores() -> None:
    split, prepared = _prepared_signal_fixture()

    first = train_pu_candidates(prepared, split, random_seed=42)
    repeated = train_pu_candidates(prepared, split, random_seed=42)

    assert np.allclose(
        first.elkan_noto.validation_scores,
        repeated.elkan_noto.validation_scores,
        rtol=0,
        atol=1e-12,
    )
    assert np.allclose(
        first.naive_diagnostic.validation_scores,
        repeated.naive_diagnostic.validation_scores,
        rtol=0,
        atol=1e-12,
    )
    assert first.bagging_pu.status == repeated.bagging_pu.status == "FITTED"
    assert np.allclose(
        first.bagging_pu.validation_scores,
        repeated.bagging_pu.validation_scores,
        rtol=0,
        atol=1e-12,
    )


@pytest.mark.parametrize("label_value", (0, 1))
def test_training_refuses_all_unlabeled_or_all_positive(label_value: int) -> None:
    split, prepared = _prepared_signal_fixture()
    split.train_labels.loc[:] = label_value

    with pytest.raises(TrainingAlgorithmError, match="both known-positive and unlabeled"):
        train_pu_candidates(prepared, split)


def test_training_refuses_insufficient_known_positives() -> None:
    split, prepared = _prepared_signal_fixture()
    split.train_labels.loc[:] = 0
    split.train_labels.iloc[:4] = 1

    with pytest.raises(TrainingAlgorithmError, match="at least 5 known-positive"):
        train_pu_candidates(prepared, split)


def test_training_requires_validated_feature_metadata_and_numeric_matrices() -> None:
    split, prepared = _prepared_signal_fixture()
    invalid_fingerprint = replace(prepared, feature_contract_sha256="0" * 64)

    with pytest.raises(TrainingAlgorithmError, match="fingerprint"):
        train_pu_candidates(invalid_fingerprint, split)
    with pytest.raises(TrainingAlgorithmError, match="validated Step 3 matrices"):
        train_pu_candidates(split.train_features, split)

    candidates = train_pu_candidates(prepared, split, run_challenger=False)
    assert candidates.elkan_noto.estimator.estimator.n_features_in_ == (
        prepared.transformed_feature_count
    )
    assert tuple(prepared.raw_feature_names) == ORDERED_FEATURES
    assert "customer_id" not in prepared.raw_feature_names
    assert "pu_label" not in prepared.raw_feature_names


def test_challenger_runtime_limit_produces_measured_skip() -> None:
    split, prepared = _prepared_signal_fixture()

    candidates = train_pu_candidates(
        prepared,
        split,
        challenger_runtime_limit_seconds=1e-12,
    )

    assert candidates.elkan_noto.status == "FITTED"
    assert candidates.bagging_pu.status == "SKIPPED_RUNTIME"
    assert candidates.bagging_pu.fit_seconds > 0
    assert "runtime limit" in candidates.bagging_pu.skip_reason
    assert candidates.bagging_pu.estimator is None
    assert candidates.bagging_pu.validation_scores is None


class _WarningProbabilisticEstimator(BaseEstimator):
    def fit(self, matrix: np.ndarray, labels: np.ndarray):
        warnings.warn("fixture training warning", RuntimeWarning, stacklevel=2)
        self.classes_ = np.array([0, 1])
        self.n_features_in_ = matrix.shape[1]
        return self

    def predict_proba(self, matrix: np.ndarray) -> np.ndarray:
        values = matrix.toarray() if hasattr(matrix, "toarray") else np.asarray(matrix)
        positive = 1 / (1 + np.exp(-np.clip(values[:, 0], -10, 10)))
        return np.column_stack((1 - positive, positive))


def test_training_warnings_are_captured_in_candidate_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    split, prepared = _prepared_signal_fixture()

    def build_warning_estimator(*, random_seed: int) -> ElkanotoPuClassifier:
        return ElkanotoPuClassifier(
            estimator=_WarningProbabilisticEstimator(),
            hold_out_ratio=0.1,
            random_state=random_seed,
        )

    monkeypatch.setattr(
        training_module,
        "build_elkan_noto_estimator",
        build_warning_estimator,
    )

    candidates = train_pu_candidates(prepared, split, run_challenger=False)

    assert candidates.elkan_noto.status == "FITTED"
    assert candidates.elkan_noto.warnings == (
        "RuntimeWarning: fixture training warning",
    )
