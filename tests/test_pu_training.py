from __future__ import annotations

import inspect
import warnings
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from pulearn import BaggingPuClassifier, ElkanotoPuClassifier
from sklearn.base import BaseEstimator

from app.ml import training as training_module
from app.ml.feature_contract import ORDERED_FEATURES, RAW_TRAINING_COLUMNS
from app.ml.model_roles import (
    CHALLENGER_1_ROLE,
    DIAGNOSTIC_CONTROL_ROLE,
    PRIMARY_ROLE,
)
from app.ml.preprocessing import prepare_feature_matrices, split_customer_cohort
from app.ml.pu_estimators import BAGGING_PU_NAME, ELKAN_NOTO_NAME, NAIVE_BASELINE_NAME
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


def _assert_scores(scores: np.ndarray, size: int, *, unit_interval: bool) -> None:
    assert scores.shape == (size,)
    assert np.isfinite(scores).all()
    assert (scores >= 0).all()
    if unit_interval:
        assert (scores <= 1).all()
    assert np.unique(scores).size > 1


def test_governed_roles_fit_in_primary_challenger_diagnostic_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    split, prepared = _prepared_signal_fixture()
    calls: list[str] = []
    originals = {
        "primary": training_module._train_bagging_primary,
        "challenger": training_module._train_elkan_challenger,
        "diagnostic": training_module._train_naive_diagnostic,
    }

    def primary(*args, **kwargs):
        calls.append("primary")
        return originals["primary"](*args, **kwargs)

    def challenger(*args, **kwargs):
        calls.append("challenger")
        return originals["challenger"](*args, **kwargs)

    def diagnostic(*args, **kwargs):
        calls.append("diagnostic")
        return originals["diagnostic"](*args, **kwargs)

    monkeypatch.setattr(training_module, "_train_bagging_primary", primary)
    monkeypatch.setattr(training_module, "_train_elkan_challenger", challenger)
    monkeypatch.setattr(training_module, "_train_naive_diagnostic", diagnostic)
    candidates = train_pu_candidates(prepared, split)

    assert calls == ["primary", "challenger", "diagnostic"]
    assert candidates.primary.name == BAGGING_PU_NAME
    assert candidates.primary.candidate_role == PRIMARY_ROLE
    assert candidates.primary.status == "FITTED"
    assert isinstance(candidates.primary.estimator, BaggingPuClassifier)
    assert candidates.primary.algorithm_metadata["bounded_cpu_jobs"] == 1
    _assert_scores(
        candidates.primary.validation_scores,
        len(split.validation_labels),
        unit_interval=True,
    )

    assert candidates.challenger_1.name == ELKAN_NOTO_NAME
    assert candidates.challenger_1.candidate_role == CHALLENGER_1_ROLE
    assert candidates.challenger_1.status == "FITTED"
    assert isinstance(candidates.challenger_1.estimator, ElkanotoPuClassifier)
    assert 0 < candidates.challenger_1.algorithm_metadata["labeling_propensity_c"] <= 1
    _assert_scores(
        candidates.challenger_1.validation_scores,
        len(split.validation_labels),
        unit_interval=False,
    )

    diagnostic_result = candidates.diagnostic_control
    assert diagnostic_result.name == NAIVE_BASELINE_NAME
    assert diagnostic_result.candidate_role == DIAGNOSTIC_CONTROL_ROLE
    assert diagnostic_result.is_genuine_pu is False
    assert diagnostic_result.algorithm_metadata["eligible_for_selection"] is False
    assert diagnostic_result.algorithm_metadata["unlabeled_treatment"] == (
        "temporarily_treated_as_negative_for_diagnostic_only"
    )


def test_same_seed_reproduces_all_candidate_scores() -> None:
    split, prepared = _prepared_signal_fixture()
    first = train_pu_candidates(prepared, split, random_seed=42)
    repeated = train_pu_candidates(prepared, split, random_seed=42)
    for first_result, repeated_result in zip(
        (first.primary, first.challenger_1, first.diagnostic_control),
        (repeated.primary, repeated.challenger_1, repeated.diagnostic_control),
        strict=True,
    ):
        assert first_result.name == repeated_result.name
        assert first_result.candidate_role == repeated_result.candidate_role
        assert first_result.status == repeated_result.status == "FITTED"
        assert np.allclose(
            first_result.validation_scores,
            repeated_result.validation_scores,
            rtol=0,
            atol=1e-12,
        )


def test_bagging_primary_is_mandatory_and_has_no_runtime_skip_control() -> None:
    signature = inspect.signature(train_pu_candidates)
    assert "run_challenger" not in signature.parameters
    assert "challenger_runtime_limit_seconds" not in signature.parameters
    assert signature.parameters["run_elkan_challenger"].default is True


class _FailingEstimator:
    def fit(self, matrix: object, labels: object) -> object:
        raise ValueError("forced fixture failure")


def test_bagging_fit_failure_fails_the_governed_training_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    split, prepared = _prepared_signal_fixture()
    monkeypatch.setattr(
        training_module,
        "build_bagging_pu_estimator",
        lambda *, random_seed: _FailingEstimator(),
    )
    with pytest.raises(TrainingAlgorithmError, match="Mandatory Bagging PU primary"):
        train_pu_candidates(prepared, split, run_elkan_challenger=False)


def test_elkan_can_be_disabled_without_disabling_primary() -> None:
    split, prepared = _prepared_signal_fixture()
    candidates = train_pu_candidates(
        prepared, split, run_elkan_challenger=False
    )
    assert candidates.primary.status == "FITTED"
    assert candidates.challenger_1.status == "SKIPPED_DISABLED"
    assert "disabled" in candidates.challenger_1.skip_reason
    assert candidates.diagnostic_control.status == "FITTED"


def test_elkan_incompatibility_is_bounded_skip_and_primary_remains_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    split, prepared = _prepared_signal_fixture()
    monkeypatch.setattr(
        training_module,
        "build_elkan_noto_estimator",
        lambda *, random_seed: _FailingEstimator(),
    )
    candidates = train_pu_candidates(prepared, split)
    assert candidates.primary.status == "FITTED"
    assert candidates.challenger_1.status == "SKIPPED_INCOMPATIBLE"
    assert candidates.challenger_1.estimator is None
    assert "bounded configuration" in candidates.challenger_1.skip_reason


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
    candidates = train_pu_candidates(prepared, split, run_elkan_challenger=False)
    assert candidates.primary.estimator.n_features_ == (
        prepared.transformed_feature_count
    )
    assert tuple(prepared.raw_feature_names) == ORDERED_FEATURES
    assert "customer_id" not in prepared.raw_feature_names
    assert "pu_label" not in prepared.raw_feature_names


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


def test_elkan_training_warnings_are_captured(
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
        training_module, "build_elkan_noto_estimator", build_warning_estimator
    )
    candidates = train_pu_candidates(prepared, split)
    assert candidates.challenger_1.status == "FITTED"
    assert candidates.challenger_1.warnings == (
        "RuntimeWarning: fixture training warning",
    )
