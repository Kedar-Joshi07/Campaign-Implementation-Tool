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
from app.ml.model_roles import (
    CHALLENGER_1_ROLE,
    DIAGNOSTIC_CONTROL_ROLE,
    MODEL_ROLE_POLICY_VERSION,
    PRIMARY_ROLE,
    PRIMARY_ROLE_GOVERNED_SELECTION,
)
from app.ml.preprocessing import CustomerCohortSplit
from app.ml.pu_estimators import BAGGING_PU_NAME, ELKAN_NOTO_NAME, NAIVE_BASELINE_NAME
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


def _role(name: str) -> str:
    return {
        BAGGING_PU_NAME: PRIMARY_ROLE,
        ELKAN_NOTO_NAME: CHALLENGER_1_ROLE,
        NAIVE_BASELINE_NAME: DIAGNOSTIC_CONTROL_ROLE,
    }[name]


def _fitted(
    name: str,
    scores: list[float],
    *,
    genuine: bool,
    fit_seconds: float = 0.02,
) -> CandidateTrainingResult:
    metadata: dict[str, object] = {
        "algorithm": f"test.{name}",
        "candidate_role": _role(name),
    }
    if name == ELKAN_NOTO_NAME:
        metadata["labeling_propensity_c"] = 0.5
    return CandidateTrainingResult(
        name=name,
        candidate_role=_role(name),  # type: ignore[arg-type]
        status="FITTED",
        is_genuine_pu=genuine,
        estimator=object(),
        fit_seconds=fit_seconds,
        score_seconds=0.01,
        validation_scores=np.asarray(scores, dtype=float),
        warnings=(),
        algorithm_metadata=metadata,
    )


def _skipped_elkan(status: str = "SKIPPED_DISABLED") -> CandidateTrainingResult:
    return CandidateTrainingResult(
        name=ELKAN_NOTO_NAME,
        candidate_role=CHALLENGER_1_ROLE,
        status=status,  # type: ignore[arg-type]
        is_genuine_pu=True,
        estimator=None,
        fit_seconds=0.0,
        score_seconds=0.0,
        validation_scores=None,
        warnings=(),
        algorithm_metadata={
            "algorithm": "test.elkan",
            "candidate_role": CHALLENGER_1_ROLE,
        },
        skip_reason="bounded test skip",
    )


def _candidate_set(
    labels: list[int],
    *,
    primary_scores: list[float] | None = None,
    challenger_scores: list[float] | None = None,
    diagnostic_scores: list[float] | None = None,
    challenger_status: str = "FITTED",
) -> TrainingCandidateSet:
    count = len(labels)
    primary_scores = primary_scores or list(np.linspace(0.1, 0.9, count))
    challenger_scores = challenger_scores or primary_scores
    diagnostic_scores = diagnostic_scores or list(np.linspace(0.2, 0.8, count))
    challenger = (
        _fitted(ELKAN_NOTO_NAME, challenger_scores, genuine=True)
        if challenger_status == "FITTED"
        else _skipped_elkan(challenger_status)
    )
    return TrainingCandidateSet(
        primary=_fitted(BAGGING_PU_NAME, primary_scores, genuine=True),
        challenger_1=challenger,
        diagnostic_control=_fitted(
            NAIVE_BASELINE_NAME, diagnostic_scores, genuine=False
        ),
    )


def test_metrics_remain_observed_label_diagnostics_with_frozen_math() -> None:
    labels = [1, 0, 1, 0, 0, 1, 0, 0, 1, 0]
    scores = [0.9, 0.1, 0.8, 0.2, 0.3, 0.7, 0.4, 0.5, 0.6, 0.0]
    result = evaluate_and_select_model(
        _candidate_set(labels, primary_scores=scores), _split(labels)
    )
    metrics = result.candidate_results[BAGGING_PU_NAME]
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


def test_tied_candidates_select_bagging_by_role_policy() -> None:
    labels = [1, 0, 1, 0, 1, 0]
    scores = [0.9, 0.1, 0.8, 0.2, 0.7, 0.3]
    first = evaluate_and_select_model(
        _candidate_set(labels, primary_scores=scores, challenger_scores=scores),
        _split(labels),
    )
    repeated = evaluate_and_select_model(
        _candidate_set(labels, primary_scores=scores, challenger_scores=scores),
        _split(labels),
    )
    assert first.selected_candidate == BAGGING_PU_NAME
    assert first.selection_policy == PRIMARY_ROLE_GOVERNED_SELECTION
    assert first.canonical_json == repeated.canonical_json


def test_better_challenger_is_flagged_but_cannot_replace_primary() -> None:
    labels = [1, 0, 1, 0, 1, 0, 1, 0, 1, 0]
    primary = [0.1, 0.9, 0.2, 0.8, 0.3, 0.7, 0.4, 0.6, 0.5, 0.55]
    challenger = [0.99, 0.01, 0.98, 0.02, 0.97, 0.03, 0.96, 0.04, 0.95, 0.05]
    result = evaluate_and_select_model(
        _candidate_set(
            labels, primary_scores=primary, challenger_scores=challenger
        ),
        _split(labels),
    )
    assert result.selected_candidate == BAGGING_PU_NAME
    assert "CHALLENGER_OUTPERFORMED_PRIMARY" in result.quality_flags
    comparison = result.challenger_comparison
    assert comparison["challenger_outperformed_primary"] is True
    assert comparison["outperformed_metrics"]
    assert {
        "top_05_lift",
        "top_05_recall",
        "top_10_lift",
        "top_10_recall",
        "top_20_lift",
        "top_20_recall",
        "observed_label_roc_auc",
        "observed_label_average_precision",
        "observed_label_ks",
        "known_positive_score_mean",
        "known_positive_score_median",
        "unlabeled_score_mean",
        "unlabeled_score_median",
        "fit_seconds",
        "scoring_seconds",
    } == set(comparison["challenger_minus_primary_deltas"])
    assert comparison["top10_lift_delta"] == comparison[
        "challenger_minus_primary_deltas"
    ]["top_10_lift"]
    assert any(
        delta > 0
        for delta in comparison["challenger_minus_primary_deltas"].values()
    )


def test_perfect_diagnostic_control_cannot_replace_primary() -> None:
    labels = [1, 0, 1, 0, 1, 0]
    result = evaluate_and_select_model(
        _candidate_set(
            labels,
            primary_scores=[0.6, 0.2, 0.5, 0.4, 0.3, 0.1],
            diagnostic_scores=[0.99, 0.01, 0.98, 0.02, 0.97, 0.03],
        ),
        _split(labels),
    )
    assert result.selected_candidate == BAGGING_PU_NAME
    diagnostic = result.candidate_results[NAIVE_BASELINE_NAME]
    assert diagnostic["candidate_role"] == DIAGNOSTIC_CONTROL_ROLE
    assert diagnostic["eligible_for_official_selection"] is False


@pytest.mark.parametrize("status", ("SKIPPED_DISABLED", "SKIPPED_INCOMPATIBLE"))
def test_unavailable_elkan_still_selects_valid_bagging(status: str) -> None:
    labels = [1, 0, 1, 0, 1, 0]
    result = evaluate_and_select_model(
        _candidate_set(labels, challenger_status=status), _split(labels)
    )
    assert result.selected_candidate == BAGGING_PU_NAME
    assert "CHALLENGER_1_SKIPPED" in result.quality_flags
    assert result.challenger_comparison["status"] == status


def test_invalid_or_constant_bagging_primary_fails_instead_of_promoting() -> None:
    labels = [1, 0, 1, 0, 1, 0]
    constant = _candidate_set(labels, primary_scores=[0.5] * len(labels))
    with pytest.raises(ModelEvaluationError, match="constant"):
        evaluate_and_select_model(constant, _split(labels))

    invalid = _candidate_set(labels)
    object.__setattr__(invalid.primary, "status", "SKIPPED_INCOMPATIBLE")
    object.__setattr__(invalid.primary, "estimator", None)
    object.__setattr__(invalid.primary, "validation_scores", None)
    with pytest.raises(ModelEvaluationError, match="mandatory Bagging PU primary"):
        evaluate_and_select_model(invalid, _split(labels))


def test_nonfinite_primary_scores_fail_evaluation() -> None:
    labels = [1, 0, 1, 0, 1, 0]
    candidates = _candidate_set(
        labels, primary_scores=[0.9, 0.1, float("nan"), 0.2, 0.7, 0.3]
    )
    with pytest.raises(ModelEvaluationError, match="non-finite"):
        evaluate_and_select_model(candidates, _split(labels))


def test_canonical_role_v2_json_is_bounded_finite_and_contains_no_ids_or_scores() -> None:
    labels = [1, 0, 1, 0, 1, 0]
    result = evaluate_and_select_model(_candidate_set(labels), _split(labels))
    parsed = json.loads(result.canonical_json)
    assert parsed["evaluation_contract_version"] == EVALUATION_CONTRACT_VERSION == "2"
    assert parsed["model_role_policy_version"] == MODEL_ROLE_POLICY_VERSION == "2"
    assert parsed["primary_candidate"] == BAGGING_PU_NAME
    assert parsed["challenger_candidates"] == [ELKAN_NOTO_NAME]
    assert parsed["diagnostic_controls"] == [NAIVE_BASELINE_NAME]
    assert parsed["selection_policy"] == PRIMARY_ROLE_GOVERNED_SELECTION
    assert parsed["selected_candidate"] == BAGGING_PU_NAME
    assert parsed["candidate_results"][BAGGING_PU_NAME]["candidate_role"] == PRIMARY_ROLE
    assert parsed["candidate_results"][BAGGING_PU_NAME][
        "eligible_for_official_selection"
    ] is True
    assert "CUS-PII" not in result.canonical_json
    assert "validation_scores" not in result.canonical_json
    assert "customer_id" not in result.canonical_json
    assert "NaN" not in result.canonical_json
    assert "Infinity" not in result.canonical_json


def test_candidate_name_and_role_mismatch_is_rejected() -> None:
    labels = [1, 0, 1, 0, 1, 0]
    candidates = _candidate_set(labels)
    object.__setattr__(candidates.primary, "candidate_role", CHALLENGER_1_ROLE)
    with pytest.raises(ModelEvaluationError, match="governed role"):
        evaluate_and_select_model(candidates, _split(labels))
