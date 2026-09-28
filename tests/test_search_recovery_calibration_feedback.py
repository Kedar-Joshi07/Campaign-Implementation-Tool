"""Focused recovery, calibrated-selection, and governed-feedback contracts."""

# ruff: noqa: F401, F811 - imported pytest fixture is intentionally injected.

from __future__ import annotations

import csv
import gzip
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.dependencies import get_database_path
from app.jobs.feedback_retraining_worker import (
    FeedbackRetrainingWorker,
    challenger_meets_promotion_gates,
)
from app.routers import potential_customer_search as search_router
from app.services.phase11_feedback_service import (
    FeedbackConflictError,
    FeedbackValidationError,
    evaluate_adaptive_feedback_gate,
    ingest_feedback,
)
from app.services.propensity_calibration_service import (
    FittedCalibration,
    PropensityCalibrationError,
    fit_held_out_calibration,
    publish_fitted_calibration,
)
from tests.test_phase11_search_result_registry import (
    _complete,
    _search,
    _snapshot,
    case,
)


def _identity_calibration() -> FittedCalibration:
    return FittedCalibration(
        method="ISOTONIC",
        artifact={
            "method": "ISOTONIC",
            "x_thresholds": [0.0, 1.0],
            "y_thresholds": [0.0, 1.0],
        },
        metrics={
            "brier_score": 0.1,
            "log_loss": 0.3,
            "expected_calibration_error": 0.02,
            "roc_auc": 0.8,
            "average_precision": 0.7,
            "top_decile_lift": 2.0,
        },
        split_lineage={
            "seed": 1729,
            "strategy": "TEST_IDENTITY",
            "calibration_count": 200,
            "test_count": 200,
            "calibration_group_count": 2,
            "test_group_count": 2,
            "group_overlap_count": 0,
        },
    )


def test_calibration_fit_is_deterministic_and_group_disjoint() -> None:
    scores = np.tile(np.linspace(0.05, 0.95, 100), 4)
    outcomes = np.tile(np.asarray([0, 1] * 50), 4)
    groups = np.repeat(np.asarray(["run-a", "run-b", "run-c", "run-d"]), 100)

    first = fit_held_out_calibration(scores, outcomes, groups)
    second = fit_held_out_calibration(scores, outcomes, groups)

    assert first == second
    assert first.method in {"SIGMOID", "ISOTONIC"}
    assert first.split_lineage["group_overlap_count"] == 0
    assert set(first.metrics) == {
        "brier_score", "log_loss", "expected_calibration_error",
        "roc_auc", "average_precision", "top_decile_lift",
    }


@pytest.mark.parametrize(
    ("overrides", "expected"),
    (
        ({}, "QUEUED"),
        ({"labels": 999}, "WAITING_FOR_DATA"),
        ({"positives": 99}, "WAITING_FOR_DATA"),
        ({"negatives": 99}, "WAITING_FOR_DATA"),
        ({"runs": 1}, "WAITING_FOR_DATA"),
        ({"new_label_ratio": .099, "population_stability_index": .199}, "WAITING_FOR_DATA"),
        ({"new_label_ratio": 0.0, "population_stability_index": .20}, "QUEUED"),
    ),
)
def test_adaptive_feedback_gate_has_exact_governed_boundaries(overrides, expected) -> None:
    values = {
        "labels": 1_000,
        "positives": 100,
        "negatives": 900,
        "runs": 2,
        "new_label_ratio": .10,
        "population_stability_index": 0.0,
    }
    status, reason = evaluate_adaptive_feedback_gate(**(values | overrides))
    assert status == expected
    assert reason


def test_challenger_promotion_requires_calibration_and_ranking_gates() -> None:
    incumbent = {
        "brier_score": .20,
        "roc_auc": .70,
        "average_precision": .40,
        "top_decile_lift": 2.0,
    }
    passing = {
        "brier_score": .19,
        "roc_auc": .69,
        "average_precision": .39,
        "top_decile_lift": 2.0,
    }
    assert challenger_meets_promotion_gates(passing, incumbent) is True
    assert challenger_meets_promotion_gates(passing, None) is True
    for key, value in (
        ("brier_score", .20),
        ("roc_auc", .689),
        ("average_precision", .389),
        ("top_decile_lift", 1.999),
    ):
        assert challenger_meets_promotion_gates(passing | {key: value}, incumbent) is False
    assert challenger_meets_promotion_gates(passing | {"brier_score": float("nan")}, incumbent) is False


def test_feedback_worker_recovers_queued_and_interrupted_decisions(case, monkeypatch) -> None:
    path, ids, _values, _repository = case
    with get_connection(path, write=True) as connection:
        for status in ("QUEUED", "TRAINING"):
            connection.execute(
                """INSERT INTO feedback_retraining_decisions (
                       decision_contract_version,scoring_run_id,status,label_count,
                       positive_count,negative_count,distinct_run_count,new_label_ratio,
                       population_stability_index,trigger_reason,created_at
                   ) VALUES ('1',?,?,?,?,?,?,?,?,?,?)""",
                (
                    ids["scoring_run_id"], status, 1_000, 100, 900, 2,
                    .10, 0.0, "test", "2026-09-20T10:00:00Z",
                ),
            )
    worker = FeedbackRetrainingWorker()
    submitted: list[tuple[Path, int]] = []
    monkeypatch.setattr(worker, "submit", lambda database_path, decision_id: submitted.append((Path(database_path), decision_id)))
    try:
        assert worker.resume_durable_decisions(path) == 2
    finally:
        worker.shutdown()

    with get_connection(path) as connection:
        rows = connection.execute(
            "SELECT retraining_decision_id,status,trigger_reason FROM feedback_retraining_decisions ORDER BY retraining_decision_id"
        ).fetchall()
    assert [row["status"] for row in rows] == ["QUEUED", "QUEUED"]
    assert rows[1]["trigger_reason"] == "Interrupted challenger recovered at application startup."
    assert submitted == [(path, int(row["retraining_decision_id"])) for row in rows]


def test_published_calibration_has_exact_bucket_boundaries_and_attestation(case) -> None:
    path, ids, _values, _repository = case
    scored = (
        ("P-050", 0.50, "0.50"),
        ("P-059", 0.599999, "0.50"),
        ("P-060", 0.60, "0.60"),
        ("P-070", 0.70, "0.70"),
        ("P-080", 0.80, "0.80"),
        ("P-090", 0.90, "0.90"),
        ("P-100", 1.00, "0.90"),
    )
    with get_connection(path, write=True) as connection:
        connection.executemany(
            """INSERT INTO demographics (
                   person_id,age,state,individual_yearly_income,family_member_count,
                   number_of_children_in_family,number_of_adults_in_family,
                   family_yearly_income
               ) VALUES (?,40,'Ohio',50000,1,0,1,50000)""",
            ((person_id,) for person_id, _score, _bucket in scored),
        )
        connection.execute(
            """UPDATE scoring_runs SET demographic_snapshot_count=?,scored_person_count=?,
                   demographic_min_person_id=?,demographic_max_person_id=?,
                   score_min=.5,score_max=1.0,score_mean=.767142714
               WHERE scoring_run_id=?""",
            (len(scored), len(scored), scored[0][0], scored[-1][0], ids["scoring_run_id"]),
        )
        connection.executemany(
            """INSERT INTO propensity_scores (
                   scoring_run_id,model_run_id,person_id,propensity_score
               ) VALUES (?,?,?,?)""",
            (
                (ids["scoring_run_id"], ids["model_run_id"], person_id, score)
                for person_id, score, _bucket in scored
            ),
        )

    published = publish_fitted_calibration(
        path,
        ids["scoring_run_id"],
        _identity_calibration(),
        source_checksum="2" * 64,
        promote=True,
        batch_size=3,
    )
    repeated = publish_fitted_calibration(
        path,
        ids["scoring_run_id"],
        _identity_calibration(),
        source_checksum="2" * 64,
        promote=True,
        batch_size=2,
    )

    with get_connection(path) as connection:
        rows = connection.execute(
            """SELECT person_id,propensity_bucket FROM calibrated_propensity_scores
               WHERE calibration_artifact_id=? ORDER BY person_id""",
            (published["calibration_artifact_id"],),
        ).fetchall()
        attestation = connection.execute(
            "SELECT verification_status,verified_row_count FROM intelligence_verification_attestations"
        ).fetchone()
    assert [(row["person_id"], row["propensity_bucket"]) for row in rows] == [
        (person_id, bucket) for person_id, _score, bucket in scored
    ]
    assert repeated["calibration_artifact_id"] == published["calibration_artifact_id"]
    assert repeated["calibrated_person_count"] == len(scored)
    assert tuple(attestation) == ("VERIFIED", len(scored))


def test_failed_deep_verification_cannot_publish_calibration(case) -> None:
    path, ids, _values, _repository = case
    with get_connection(path, write=True) as connection:
        connection.execute(
            "UPDATE scoring_runs SET scored_person_count=1 WHERE scoring_run_id=?",
            (ids["scoring_run_id"],),
        )

    with pytest.raises(PropensityCalibrationError, match="deep verification"):
        publish_fitted_calibration(
            path,
            ids["scoring_run_id"],
            _identity_calibration(),
            source_checksum="2" * 64,
            promote=True,
        )

    with get_connection(path) as connection:
        artifacts = connection.execute(
            "SELECT status FROM score_calibration_artifacts"
        ).fetchall()
    assert artifacts == []


def _write_membership(root: Path, relative_path: str, members: list[str]) -> None:
    artifact = root / relative_path
    artifact.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(artifact, "wt", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "person_id", "propensity_score", "percentile_bucket",
                "decile", "rank_band",
            ),
        )
        writer.writeheader()
        for index, person_id in enumerate(members, start=1):
            writer.writerow({
                "person_id": person_id,
                "propensity_score": 0.5,
                "percentile_bucket": index,
                "decile": 1,
                "rank_band": "HIGH",
            })


def test_feedback_is_membership_bound_and_idempotent(case, tmp_path: Path) -> None:
    path, _ids, _values, _repository = case
    search_run_id = _search(case)
    relative = "artifacts/results/result_snapshot_000001/members.csv.gz"
    _write_membership(tmp_path, relative, ["P-1", "P-2"])
    snapshot_id = _snapshot(
        case,
        search_run_id,
        resolved_count=2,
        storage_uri=relative,
    )
    _complete(case, search_run_id, snapshot_id)
    rows = [
        {"person_id": "P-1", "outcome": 1, "outcome_at": "2026-09-20T10:00:00Z"},
        {"person_id": "P-2", "outcome": 0, "outcome_at": "2026-09-20T10:00:00Z"},
    ]

    first = ingest_feedback(
        path,
        search_run_id,
        rows=rows,
        source_name="governed-test",
        idempotency_key="feedback-batch-0001",
        project_root=tmp_path,
    )
    repeated = ingest_feedback(
        path,
        search_run_id,
        rows=rows,
        source_name="governed-test",
        idempotency_key="feedback-batch-0001",
        project_root=tmp_path,
    )
    assert first == repeated
    assert first["positive_count"] == first["negative_count"] == 1
    assert first["retraining_status"] == "WAITING_FOR_DATA"

    with pytest.raises(FeedbackConflictError, match="different feedback"):
        ingest_feedback(
            path,
            search_run_id,
            rows=rows[:1],
            source_name="governed-test",
            idempotency_key="feedback-batch-0001",
            project_root=tmp_path,
        )
    with pytest.raises(FeedbackValidationError, match="immutable result"):
        ingest_feedback(
            path,
            search_run_id,
            rows=[{
                "person_id": "P-unknown", "outcome": 1,
                "outcome_at": "2026-09-20T10:00:00Z",
            }],
            source_name="governed-test",
            idempotency_key="feedback-batch-0002",
            project_root=tmp_path,
        )


def test_feedback_rejects_future_outcome_timestamp(case, tmp_path: Path) -> None:
    path, _ids, _values, _repository = case
    search_run_id = _search(case)
    relative = "artifacts/results/result_snapshot_000001/members.csv.gz"
    _write_membership(tmp_path, relative, ["P-1"])
    snapshot_id = _snapshot(case, search_run_id, resolved_count=1, storage_uri=relative)
    _complete(case, search_run_id, snapshot_id)
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    with pytest.raises(FeedbackValidationError, match="cannot be in the future"):
        ingest_feedback(
            path,
            search_run_id,
            rows=[{"person_id": "P-1", "outcome": 1, "outcome_at": future}],
            source_name="governed-test",
            idempotency_key="future-feedback",
            project_root=tmp_path,
        )


def test_feedback_api_accepts_json_and_csv_then_lists_batches(
    case, tmp_path: Path, monkeypatch,
) -> None:
    path, _ids, _values, _repository = case
    search_run_id = _search(case)
    relative = "artifacts/results/result_snapshot_000001/members.csv.gz"
    _write_membership(tmp_path, relative, ["P-1", "P-2"])
    snapshot_id = _snapshot(case, search_run_id, resolved_count=2, storage_uri=relative)
    _complete(case, search_run_id, snapshot_id)

    application = FastAPI()
    application.include_router(search_router.router)
    application.dependency_overrides[get_database_path] = lambda: path
    monkeypatch.setattr(search_router, "PROJECT_ROOT", tmp_path)
    client = TestClient(application)
    endpoint = f"/api/potential-customer-search/runs/{search_run_id}/feedback"

    json_response = client.post(
        endpoint,
        headers={"Idempotency-Key": "json-feedback-0001"},
        json={
            "source_name": "governed-json",
            "rows": [{
                "person_id": "P-1", "outcome": 1,
                "outcome_at": "2026-09-20T10:00:00Z",
            }],
        },
    )
    csv_response = client.post(
        endpoint,
        headers={
            "Content-Type": "text/csv",
            "Idempotency-Key": "csv-feedback-0001",
            "X-Feedback-Source": "governed-csv",
        },
        content=(
            "person_id,outcome,outcome_at,outcome_value\n"
            "P-2,0,2026-09-20T10:00:00Z,0\n"
        ),
    )

    assert json_response.status_code == csv_response.status_code == 201
    assert json_response.json()["positive_count"] == 1
    assert csv_response.json()["negative_count"] == 1
    listed = client.get(endpoint)
    assert listed.status_code == 200
    assert [item["feedback_batch_id"] for item in listed.json()] == [
        json_response.json()["feedback_batch_id"],
        csv_response.json()["feedback_batch_id"],
    ]


def test_feedback_templates_are_downloadable_and_match_the_ingestion_contract() -> None:
    application = FastAPI()
    application.include_router(search_router.router)
    client = TestClient(application)

    csv_response = client.get("/api/potential-customer-search/feedback-template.csv")
    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")
    assert "purchase_outcome_feedback_template.csv" in csv_response.headers["content-disposition"]
    assert csv_response.text.splitlines()[0] == "person_id,outcome,outcome_at,outcome_value"
    assert "REPLACE_WITH_PERSON_ID" in csv_response.text

    json_response = client.get("/api/potential-customer-search/feedback-template.json")
    assert json_response.status_code == 200
    assert json_response.headers["content-type"].startswith("application/json")
    assert "purchase_outcome_feedback_template.json" in json_response.headers["content-disposition"]
    assert set(json_response.json()) == {"source_name", "rows"}
    assert set(json_response.json()["rows"][0]) == {
        "person_id", "outcome", "outcome_at", "outcome_value",
    }
