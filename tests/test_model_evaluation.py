from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from app.ml.evaluation import (
    EVALUATION_CONTRACT_VERSION,
    ModelEvaluationError,
    OBSERVED_LABEL_DISCLAIMER,
    evaluate_and_select_model,
)
from app.ml.preprocessing import CustomerCohortSplit
from app.ml.pu_estimators import (
    BAGGING_PU_NAME,
    ELKAN_NOTO_NAME,
    NAIVE_BASELINE_NAME,
)
from app.ml.training import CandidateTrainingResult, TrainingCandidateSet


def _split(labels: list[int]) -> CustomerCohortSplit:
    count = len(labels)
    return CustomerCohortSplit(
        random_seed=42,
        validation_fraction=0.20,
        train_customer_ids=pd.Series(["TRAIN-1"], dtype="string"),
        validation_customer_ids=pd.Series(
            [f"CUS-PII-{index}" for index in range(count)], dtype="string"
        ),
        train_features=pd.DataFrame(index=[0]),
        validation_features=pd.DataFrame(index=range(count)),
        train_labels=pd.Series([1], dtype="Int8"),
        validation_labels=pd.Series(labels, dtype="Int8"),
    )


def _fitted(
    name: str,
    scores: list[float],
    *,
    genuine: bool,
    fit_seconds: float = 0.02,
) -> CandidateTrainingResult:
    metadata: dict[str, object] = {"algorithm": f"test.{name}"}
    if name == ELKAN_NOTO_NAME:
        metadata["labeling_propensity_c"] = 0.5
    return CandidateTrainingResult(
        name=name,
        status="FITTED",
        is_genuine_pu=genuine,
        estimator=object(),
        fit_seconds=fit_seconds,
        score_seconds=0.01,
        validation_scores=np.asarray(scores, dtype=float),
        warnings=(),
        algorithm_metadata=metadata,
    )


def _skipped(
    name: str = BAGGING_PU_NAME,
    *,
    status: str = "SKIPPED_DISABLED",
) -> CandidateTrainingResult:
    return CandidateTrainingResult(
        name=name,
        status=status,  # type: ignore[arg-type]
        is_genuine_pu=True,
        estimator=None,
        fit_seconds=0.0,
        score_seconds=0.0,
        validation_scores=None,
        warnings=(),
        algorithm_metadata={"algorithm": f"test.{name}"},
        skip_reason="bounded test skip",
    )


def _candidate_set(
    labels: list[int],
    *,
    elkan_scores: list[float] | None = None,
    bagging_scores: list[float] | None = None,
    naive_scores: list[float] | None = None,
    bagging_status: str = "FITTED",
) -> TrainingCandidateSet:
    count = len(labels)
    elkan_scores = elkan_scores or list(np.linspace(0.1, 0.9, count))
    naive_scores = naive_scores or list(np.linspace(0.2, 0.8, count))
    bagging = (
        _fitted(BAGGING_PU_NAME, bagging_scores or elkan_scores, genuine=True)
        if bagging_status == "FITTED"
        else _skipped(status=bagging_status)
    )
    return TrainingCandidateSet(
        elkan_noto=_fitted(ELKAN_NOTO_NAME, elkan_scores, genuine=True),
        naive_diagnostic=_fitted(
            NAIVE_BASELINE_NAME, naive_scores, genuine=False
        ),
        bagging_pu=bagging,
    )


def test_metrics_are_bounded_and_observed_label_diagnostics_are_disclaimed() -> None:
    labels = [1, 0, 1, 0, 0, 1, 0, 0, 1, 0]
    candidates = _candidate_set(
        labels,
        elkan_scores=[0.9, 0.1, 0.8, 0.2, 0.3, 0.7, 0.4, 0.5, 0.6, 0.0],
    )

    result = evaluate_and_select_model(candidates, _split(labels))
    metrics = result.candidate_results[ELKAN_NOTO_NAME]
    diagnostics = metrics["observed_label_diagnostics"]

    assert 0 <= diagnostics["observed_label_roc_auc"] <= 1
    assert 0 <= diagnostics["observed_label_average_precision"] <= 1
    assert diagnostics["disclaimer"] == OBSERVED_LABEL_DISCLAIMER
    assert metrics["validation_context"] == {
        "validation_customer_count": 10,
        "validation_positive_count": 4,
        "validation_unlabeled_count": 6,
        "observed_positive_prevalence": 0.4,
    }
    for top_slice in metrics["top_slice_metrics"].values():
        assert 0 <= top_slice["known_positive_recall_at_k"] <= 1
        assert 0 <= top_slice["known_positive_concentration_at_k"] <= 1
        assert top_slice["known_positive_lift_at_k"] >= 0
    assert 0 <= metrics["separation_diagnostics"]["observed_label_ks_statistic"] <= 1


def test_top_slice_uses_ceil_minimum_one_and_stable_index_for_ties() -> None:
    labels = [1, 0, 1, 0]
    candidates = _candidate_set(
        labels,
        elkan_scores=[0.9, 0.9, 0.2, 0.1],
        bagging_scores=[0.1, 0.2, 0.8, 0.9],
    )

    result = evaluate_and_select_model(candidates, _split(labels))
    slices = result.candidate_results[ELKAN_NOTO_NAME]["top_slice_metrics"]

    for key in ("top_05_percent", "top_10_percent", "top_20_percent"):
        assert slices[key]["top_n"] == 1
        assert slices[key]["known_positives_captured"] == 1
        assert slices[key]["known_positive_recall_at_k"] == 0.5


def test_zero_positive_or_zero_unlabeled_validation_is_rejected() -> None:
    for labels in ([0, 0, 0, 0], [1, 1, 1, 1]):
        with pytest.raises(ModelEvaluationError, match="both validation positives"):
            evaluate_and_select_model(_candidate_set(labels), _split(labels))


def test_nonfinite_fitted_candidate_scores_fail_evaluation() -> None:
    labels = [1, 0, 1, 0]
    candidates = _candidate_set(
        labels,
        naive_scores=[0.1, 0.2, float("nan"), 0.4],
    )

    with pytest.raises(ModelEvaluationError, match="non-finite"):
        evaluate_and_select_model(candidates, _split(labels))


def test_constant_genuine_candidate_is_flagged_and_cannot_win() -> None:
    labels = [1, 0, 1, 0, 1, 0]
    candidates = _candidate_set(
        labels,
        elkan_scores=[0.5] * len(labels),
        bagging_scores=[0.9, 0.1, 0.8, 0.2, 0.7, 0.3],
    )

    result = evaluate_and_select_model(candidates, _split(labels))

    assert "LOW_SCORE_VARIANCE" in result.candidate_results[ELKAN_NOTO_NAME][
        "quality_flags"
    ]
    assert result.selected_candidate == BAGGING_PU_NAME


def test_all_constant_genuine_candidates_fail_instead_of_selecting_naive() -> None:
    labels = [1, 0, 1, 0, 1, 0]
    candidates = _candidate_set(
        labels,
        elkan_scores=[0.5] * len(labels),
        bagging_scores=[0.4] * len(labels),
        naive_scores=[0.9, 0.1, 0.8, 0.2, 0.7, 0.3],
    )

    with pytest.raises(ModelEvaluationError, match="genuine PU candidate"):
        evaluate_and_select_model(candidates, _split(labels))


def test_naive_baseline_cannot_win_official_selection() -> None:
    labels = [1, 0, 1, 0, 1, 0, 1, 0, 1, 0]
    candidates = _candidate_set(
        labels,
        elkan_scores=[0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.0, 0.7, 0.8, 0.9],
        naive_scores=[0.9, 0.0, 0.8, 0.1, 0.7, 0.2, 0.6, 0.3, 0.5, 0.4],
        bagging_status="SKIPPED_DISABLED",
    )

    result = evaluate_and_select_model(candidates, _split(labels))

    assert result.selected_candidate == ELKAN_NOTO_NAME
    assert result.selected_candidate_result.is_genuine_pu is True
    assert "diagnostic-only and ineligible" in result.selection_reason


def test_naive_name_cannot_win_even_if_candidate_role_is_misdeclared() -> None:
    labels = [1, 0, 1, 0, 1, 0]
    scores = [0.9, 0.1, 0.8, 0.2, 0.7, 0.3]
    candidates = TrainingCandidateSet(
        elkan_noto=_skipped(ELKAN_NOTO_NAME),
        naive_diagnostic=_fitted(
            NAIVE_BASELINE_NAME, scores, genuine=True
        ),
        bagging_pu=_skipped(),
    )

    with pytest.raises(ModelEvaluationError, match="genuine PU candidate"):
        evaluate_and_select_model(candidates, _split(labels))


def test_identical_genuine_candidates_use_deterministic_simplicity_tie_break() -> None:
    labels = [1, 0, 1, 0, 1, 0]
    scores = [0.9, 0.1, 0.8, 0.2, 0.7, 0.3]
    candidates = _candidate_set(
        labels,
        elkan_scores=scores,
        bagging_scores=scores,
    )

    first = evaluate_and_select_model(candidates, _split(labels))
    second = evaluate_and_select_model(candidates, _split(labels))

    assert first.selected_candidate == ELKAN_NOTO_NAME
    assert first.canonical_json == second.canonical_json


def test_runtime_skip_is_preserved_as_an_overall_quality_flag() -> None:
    labels = [1, 0, 1, 0, 1, 0]
    candidates = _candidate_set(labels, bagging_status="SKIPPED_RUNTIME")

    result = evaluate_and_select_model(candidates, _split(labels))

    assert "CHALLENGER_SKIPPED_RUNTIME" in result.quality_flags
    assert result.candidate_results[BAGGING_PU_NAME]["quality_flags"] == [
        "CHALLENGER_SKIPPED_RUNTIME"
    ]


def test_canonical_json_is_bounded_finite_and_contains_no_ids_or_scores() -> None:
    labels = [1, 0, 1, 0, 1, 0]
    result = evaluate_and_select_model(_candidate_set(labels), _split(labels))

    parsed = json.loads(result.canonical_json)

    assert parsed["evaluation_contract_version"] == EVALUATION_CONTRACT_VERSION
    assert parsed["selected_candidate"] in {ELKAN_NOTO_NAME, BAGGING_PU_NAME}
    assert "CUS-PII" not in result.canonical_json
    assert "validation_scores" not in result.canonical_json
    assert "customer_id" not in result.canonical_json
    assert "NaN" not in result.canonical_json
    assert "Infinity" not in result.canonical_json


def test_propensity_instability_is_reported_for_elkan_candidate() -> None:
    labels = [1, 0, 1, 0, 1, 0]
    candidates = _candidate_set(labels)
    candidates.elkan_noto.algorithm_metadata["labeling_propensity_c"] = 0.001

    result = evaluate_and_select_model(candidates, _split(labels))

    assert "PU_PROPENSITY_ESTIMATE_UNSTABLE" in result.candidate_results[
        ELKAN_NOTO_NAME
    ]["quality_flags"]
