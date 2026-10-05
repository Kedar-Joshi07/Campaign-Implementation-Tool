"""Prompt 13.6 leakage-safe feedback and like-for-like comparison tests."""

from __future__ import annotations

import numpy as np
import pytest

from app.jobs.feedback_retraining_worker import (
    build_challenger_comparison_evidence,
    compare_calibrations_on_evaluation_window,
    evaluation_population_sha256,
)
from app.services.feedback_grouping import build_feedback_grouping
from app.services.propensity_calibration_service import (
    PropensityCalibrationError,
    fit_held_out_calibration,
)


def test_feedback_connected_components_prevent_person_leakage_and_are_deterministic() -> None:
    rows = [
        {"search_run_id": 1, "person_id": "P1"},
        {"search_run_id": 2, "person_id": "P1"},
        {"search_run_id": 2, "person_id": "P2"},
        {"search_run_id": 3, "person_id": "P2"},
        {"search_run_id": 4, "person_id": "P3"},
    ]
    grouping = build_feedback_grouping(rows)
    reordered = build_feedback_grouping(list(reversed(rows)))
    by_event = {
        (row["search_run_id"], row["person_id"]): group
        for row, group in zip(rows, grouping.row_group_ids, strict=True)
    }
    reordered_by_event = {
        (row["search_run_id"], row["person_id"]): group
        for row, group in zip(
            reversed(rows), reordered.row_group_ids, strict=True
        )
    }

    assert by_event[(1, "P1")] == by_event[(2, "P1")]
    assert by_event[(2, "P2")] == by_event[(3, "P2")]
    assert by_event[(1, "P1")] == by_event[(3, "P2")]
    assert by_event[(4, "P3")] != by_event[(1, "P1")]
    assert by_event == reordered_by_event
    assert grouping.grouping_sha256 == reordered.grouping_sha256


def test_repeated_feedback_events_remain_at_original_grain_without_duplication() -> None:
    rows = [
        {"search_run_id": 10, "person_id": "P1"},
        {"search_run_id": 11, "person_id": "P1"},
        {"search_run_id": 11, "person_id": "P2"},
    ]
    grouping = build_feedback_grouping(rows)
    assert len(grouping.row_group_ids) == len(rows)
    assert len(grouping.independent_group_ids) == 1


def test_insufficient_feedback_components_and_classes_fail_closed() -> None:
    scores = np.linspace(0.05, 0.95, 200)
    labels = np.asarray([0, 1] * 100)
    with pytest.raises(PropensityCalibrationError, match="two independent"):
        fit_held_out_calibration(scores, labels, np.asarray(["one"] * 200))

    groups = np.repeat(np.asarray(["fit", "evaluate"]), 100)
    class_insufficient = np.concatenate(
        (np.zeros(100, dtype=np.int8), np.ones(100, dtype=np.int8))
    )
    with pytest.raises(PropensityCalibrationError, match="lacks both outcome"):
        fit_held_out_calibration(
            scores,
            class_insufficient,
            groups,
            calibration_fit_group_ids=("fit",),
            calibration_evaluation_group_ids=("evaluate",),
            model_training_group_ids=("model",),
        )


def test_candidate_and_incumbent_use_the_identical_evaluation_window() -> None:
    scores = np.linspace(0.01, 0.99, 400)
    labels = (scores >= 0.5).astype(np.int8)
    candidate = {
        "method": "ISOTONIC",
        "x_thresholds": [0.0, 1.0],
        "y_thresholds": [0.0, 1.0],
    }
    incumbent = {
        "method": "ISOTONIC",
        "x_thresholds": [0.0, 1.0],
        "y_thresholds": [0.5, 0.5],
    }

    candidate_metrics, incumbent_metrics, promote = (
        compare_calibrations_on_evaluation_window(
            candidate, incumbent, scores, labels
        )
    )

    assert candidate_metrics["brier_score"] < incumbent_metrics["brier_score"]
    assert promote is True


def test_historical_incumbent_metrics_are_never_the_comparison_oracle() -> None:
    scores = np.linspace(0.01, 0.99, 400)
    labels = (scores >= 0.5).astype(np.int8)
    candidate = {
        "method": "ISOTONIC",
        "x_thresholds": [0.0, 1.0],
        "y_thresholds": [0.5, 0.5],
    }
    incumbent = {
        "method": "ISOTONIC",
        "x_thresholds": [0.0, 1.0],
        "y_thresholds": [0.0, 1.0],
    }
    misleading_historical_metrics = {
        "brier_score": 0.99,
        "log_loss": 9.0,
        "expected_calibration_error": 0.99,
        "roc_auc": 0.0,
        "average_precision": 0.0,
        "top_decile_lift": 0.0,
    }

    candidate_metrics, recomputed_incumbent, promote = (
        compare_calibrations_on_evaluation_window(
            candidate, incumbent, scores, labels
        )
    )

    assert candidate_metrics["brier_score"] < misleading_historical_metrics[
        "brier_score"
    ]
    assert candidate_metrics["brier_score"] > recomputed_incumbent["brier_score"]
    assert recomputed_incumbent != misleading_historical_metrics
    assert promote is False


def test_comparison_evidence_persists_one_population_and_both_identities() -> None:
    scores = np.linspace(0.01, 0.99, 400)
    labels = (scores >= 0.5).astype(np.int8)
    candidate_artifact = {
        "method": "ISOTONIC",
        "x_thresholds": [0.0, 1.0],
        "y_thresholds": [0.0, 1.0],
    }
    incumbent_artifact = {
        "method": "ISOTONIC",
        "x_thresholds": [0.0, 1.0],
        "y_thresholds": [0.5, 0.5],
    }
    candidate, incumbent, promote = compare_calibrations_on_evaluation_window(
        candidate_artifact, incumbent_artifact, scores, labels
    )
    records = [
        {
            "feedback_batch_id": 7,
            "search_run_id": index // 200 + 1,
            "person_id": f"P{index:04d}",
            "outcome": int(label),
            "raw_score": float(score),
        }
        for index, (score, label) in enumerate(
            zip(scores, labels, strict=True), start=1
        )
    ]
    evidence = build_challenger_comparison_evidence(
        candidate_metrics=candidate,
        incumbent_recomputed_metrics=incumbent,
        incumbent_historical_metrics={"brier_score": 0.99},
        evaluation_records=records,
        evaluation_group_ids={"component-a", "component-b"},
        feedback_batch_cutoff=7,
        model_run_id=3,
        candidate_calibration_artifact_id=12,
        incumbent_calibration_artifact_id=11,
        feedback_grouping_sha256="a" * 64,
    )

    assert evidence["promotion_checks_passed"] is promote is True
    assert evidence["comparison_metric_source"] == (
        "RECOMPUTED_SAME_EVALUATION_POPULATION"
    )
    assert evidence["evaluation_record_count"] == len(records)
    assert evidence["evaluation_positive_count"] == int(labels.sum())
    assert evidence["evaluation_negative_count"] == len(labels) - int(labels.sum())
    assert evidence["evaluation_population_sha256"] == (
        evaluation_population_sha256(records)
    )
    assert evidence["candidate_calibration_artifact_id"] == 12
    assert evidence["incumbent_calibration_artifact_id"] == 11
    assert evidence["incumbent_historical_metrics"] == {"brier_score": 0.99}


def test_evaluation_population_identity_changes_on_any_record_mutation() -> None:
    records = [
        {
            "feedback_batch_id": 1,
            "search_run_id": 2,
            "person_id": "P1",
            "outcome": 1,
            "raw_score": 0.8,
        }
    ]
    original = evaluation_population_sha256(records)
    assert evaluation_population_sha256(
        [{**records[0], "outcome": 0}]
    ) != original
