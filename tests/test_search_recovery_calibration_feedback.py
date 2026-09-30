"""Focused recovery, calibrated-selection, and governed-feedback contracts."""

# ruff: noqa: F401, F811 - imported pytest fixture is intentionally injected.

from __future__ import annotations

import csv
import gzip
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.jobs.feedback_retraining_worker import (
    FeedbackRecalibrationWorker,
    FeedbackRetrainingWorker,
    challenger_meets_promotion_gates,
)
from app.routers import potential_customer_search as search_router
from app.services.phase11_feedback_service import (
    FeedbackConflictError,
    FeedbackValidationError,
    _comparable_feedback_drift,
    calculate_population_stability_index,
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
            "strategy": "CAMPAIGN_CONNECTED_THREE_WAY_V1",
            "strategy_version": "CAMPAIGN_CONNECTED_THREE_WAY_V1",
            "calibration_count": 200,
            "test_count": 200,
            "calibration_group_count": 2,
            "test_group_count": 2,
            "group_overlap_count": 0,
            "three_way_isolated": True,
            "model_training_group_ids": ["train-a"],
            "calibration_fit_group_ids": ["fit-a"],
            "calibration_evaluation_group_ids": ["eval-a"],
            "overlap_counts": {
                "model_training_calibration_fit": 0,
                "model_training_calibration_evaluation": 0,
                "calibration_fit_calibration_evaluation": 0,
            },
            "calibration_fit_class_balance": {"positive": 100, "negative": 100},
            "calibration_evaluation_class_balance": {
                "positive": 100,
                "negative": 100,
            },
            "candidate_selection_partition": "calibration_evaluation",
            "evaluation_records_used_for_fit": 0,
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


def test_psi_is_deterministic_and_requires_like_for_like_nonempty_populations() -> None:
    reference = {0: 50, 1: 30, 2: 20}
    identical = calculate_population_stability_index(reference, dict(reference))
    shifted = calculate_population_stability_index(
        reference, {0: 10, 1: 20, 2: 70}
    )

    assert identical == pytest.approx(0.0)
    assert shifted == pytest.approx(
        calculate_population_stability_index(reference, {0: 10, 1: 20, 2: 70})
    )
    assert shifted > 0.20
    with pytest.raises(FeedbackValidationError, match="nonempty"):
        calculate_population_stability_index(reference, {})
    with pytest.raises(FeedbackValidationError, match="nonnegative integers"):
        calculate_population_stability_index(reference, {0: float("nan")})


def test_unavailable_psi_never_manufactures_an_adaptive_trigger() -> None:
    status, _reason = evaluate_adaptive_feedback_gate(
        labels=1_000,
        positives=100,
        negatives=900,
        runs=2,
        new_label_ratio=0.099,
        population_stability_index=None,
    )
    assert status == "WAITING_FOR_DATA"


def test_feedback_drift_uses_same_selection_basis_and_persists_reference_lineage(
    case,
) -> None:
    path, ids, _values, _repository = case
    run_ids = [_search(case, campaign_name=f"Comparable {index}") for index in range(2)]
    with get_connection(path, write=True) as connection:
        calibration_id = int(connection.execute(
            """INSERT INTO score_calibration_artifacts (
                   calibration_contract_version,scoring_run_id,model_run_id,
                   outcome_definition,method,split_seed,split_lineage_json,
                   artifact_json,metrics_json,artifact_sha256,source_checksum,
                   status,created_at,promoted_at
               ) VALUES ('2',?,?,'ATTRIBUTED_PURCHASE','SIGMOID',1729,
                         '{}','{}','{}',?,?,'PROMOTED',?,?)""",
            (
                ids["scoring_run_id"],
                ids["model_run_id"],
                "7" * 64,
                "8" * 64,
                "2026-09-20T09:00:00Z",
                "2026-09-20T09:00:00Z",
            ),
        ).lastrowid)
        connection.execute(
            """UPDATE campaign_search_runs
               SET calibration_artifact_id=?,scoring_run_id=?
               WHERE search_run_id IN (?,?)""",
            (calibration_id, ids["scoring_run_id"], *run_ids),
        )
        scored = (
            ("REF-1", 0.10),
            ("REF-2", 0.20),
            ("NEW-1", 0.80),
            ("NEW-2", 0.90),
        )
        connection.executemany(
            """INSERT INTO calibrated_propensity_scores (
                   calibration_artifact_id,scoring_run_id,person_id,raw_score,
                   calibrated_probability,propensity_bucket,rank_position,
                   total_population,percentile_bucket,decile,rank_band
               ) VALUES (?,?,?,?,?,NULL,?,4,?,1,'HIGH')""",
            (
                (
                    calibration_id,
                    ids["scoring_run_id"],
                    person_id,
                    probability,
                    probability,
                    index,
                    index,
                )
                for index, (person_id, probability) in enumerate(scored, start=1)
            ),
        )
        basis = "9" * 64
        batch_ids: list[int] = []
        for index, run_id in enumerate(run_ids):
            batch_id = int(connection.execute(
                """INSERT INTO campaign_feedback_batches (
                       search_run_id,attempt_number,outcome_definition,source_name,
                       idempotency_key,payload_sha256,selection_basis_sha256,
                       row_count,positive_count,negative_count,status,created_at
                   ) VALUES (?,1,'ATTRIBUTED_PURCHASE','test',?,?,?,?,1,1,
                             'ACCEPTED','2026-09-20T10:00:00Z')""",
                (
                    run_id,
                    f"psi-{index}",
                    str(index + 1) * 64,
                    basis,
                    2,
                ),
            ).lastrowid)
            batch_ids.append(batch_id)
            people = ("REF-1", "REF-2") if index == 0 else ("NEW-1", "NEW-2")
            connection.executemany(
                """INSERT INTO campaign_feedback_outcomes (
                       feedback_batch_id,person_id,outcome,outcome_at
                   ) VALUES (?,?,?,'2026-09-20T10:00:00Z')""",
                ((batch_id, person_id, offset) for offset, person_id in enumerate(people)),
            )
        reference_id = int(connection.execute(
            """INSERT INTO feedback_retraining_decisions (
                   decision_contract_version,scoring_run_id,status,label_count,
                   positive_count,negative_count,distinct_run_count,new_label_ratio,
                   population_stability_index,trigger_reason,latest_feedback_batch_id,
                   drift_lineage_json,created_at,completed_at
               ) VALUES ('1',?,'PROMOTED',2,1,1,1,1.0,NULL,'reference',?,
                         '{}','2026-09-20T10:00:00Z','2026-09-20T10:00:01Z')""",
            (ids["scoring_run_id"], batch_ids[0]),
        ).lastrowid)
        reference = dict(connection.execute(
            """SELECT * FROM feedback_retraining_decisions
               WHERE retraining_decision_id=?""",
            (reference_id,),
        ).fetchone())
        psi, lineage = _comparable_feedback_drift(
            connection,
            scoring_run_id=ids["scoring_run_id"],
            reference_decision=reference,
            current_batch_id=batch_ids[1],
        )

    assert psi is not None and psi > 0.20, lineage
    assert lineage["status"] == "COMPARABLE"
    assert lineage["population_basis"] == "IDENTICAL_SEARCH_SELECTION_BASIS"
    assert lineage["selection_basis_sha256"] == basis
    assert lineage["reference_decision_id"] == reference_id
    assert lineage["reference_population_count"] == 2
    assert lineage["comparison_population_count"] == 2
    assert len(lineage["distribution_sha256"]) == 64


def test_challenger_promotion_requires_calibration_and_ranking_gates() -> None:
    incumbent = {
        "brier_score": .20,
        "log_loss": .40,
        "expected_calibration_error": .10,
        "roc_auc": .70,
        "average_precision": .40,
        "top_decile_lift": 2.0,
    }
    passing = {
        "brier_score": .19,
        "log_loss": .39,
        "expected_calibration_error": .09,
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
    for key in passing:
        assert (
            challenger_meets_promotion_gates(
                passing | {key: float("nan")}, incumbent
            )
            is False
        )


def test_public_feedback_language_is_recalibration_not_model_retraining() -> None:
    root = Path(__file__).resolve().parents[1]
    frontend = (root / "frontend/js/business-search-status.js").read_text(
        encoding="utf-8"
    )
    page = (root / "frontend/index.html").read_text(encoding="utf-8")
    worker_source = inspect.getsource(FeedbackRecalibrationWorker)

    assert "result.recalibration_reason" in frontend
    assert "result.retraining_reason" not in frontend
    assert "may recalibrate existing scores" in page
    assert "does not retrain the prediction model" in page
    assert "INSERT INTO model_runs" not in worker_source
    assert '"operation": "RECALIBRATION"' in worker_source
    assert "b.feedback_batch_id<=?" in worker_source
    assert '"feedback_batch_cutoff": batch_cutoff' in worker_source


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
    assert rows[1]["trigger_reason"] == "Interrupted recalibration recovered at application startup."
    assert submitted == [(path, int(row["retraining_decision_id"])) for row in rows]
    assert FeedbackRetrainingWorker is FeedbackRecalibrationWorker


def test_schema_30_bounds_legacy_duplicate_waiting_decisions(case) -> None:
    path, ids, _values, _repository = case
    with get_connection(path, write=True) as connection:
        connection.execute("DROP INDEX idx_feedback_recalibration_waiting")
        for ordinal in range(2):
            connection.execute(
                """INSERT INTO feedback_retraining_decisions (
                       decision_contract_version,scoring_run_id,status,label_count,
                       positive_count,negative_count,distinct_run_count,new_label_ratio,
                       population_stability_index,trigger_reason,created_at
                   ) VALUES ('1',?,'WAITING_FOR_DATA',10,5,5,1,0,NULL,?,?)""",
                (
                    ids["scoring_run_id"],
                    f"legacy waiting {ordinal}",
                    f"2026-09-20T10:00:0{ordinal}Z",
                ),
            )
        connection.execute(
            "UPDATE app_metadata SET value='29' WHERE key='schema_version'"
        )

    initialize_database(path)
    with get_connection(path) as connection:
        statuses = [
            row["status"]
            for row in connection.execute(
                """SELECT status FROM feedback_retraining_decisions
                   ORDER BY retraining_decision_id"""
            )
        ]
        indexes = {
            row["name"]
            for row in connection.execute(
                "PRAGMA index_list(feedback_retraining_decisions)"
            )
        }
    assert statuses == ["REJECTED", "WAITING_FOR_DATA"]
    assert "idx_feedback_recalibration_waiting" in indexes


def test_published_calibration_has_exact_bucket_boundaries_and_attestation(
    case, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, ids, _values, _repository = case
    attestation_checks: list[int] = []
    monkeypatch.setattr(
        "app.services.propensity_calibration_service.has_current_attestation",
        lambda _path, generation: (
            attestation_checks.append(int(generation["generation_id"])) or True
        ),
    )
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
    assert [(row["person_id"], row["propensity_bucket"]) for row in rows] == [
        (person_id, bucket) for person_id, _score, bucket in scored
    ]
    assert repeated["calibration_artifact_id"] == published["calibration_artifact_id"]
    assert repeated["calibrated_person_count"] == len(scored)
    assert attestation_checks == [ids["generation_id"], ids["generation_id"]]


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
    assert first["recalibration_status"] == "WAITING_FOR_DATA"
    assert "recalibration" in first["recalibration_reason"].lower()

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


def test_small_feedback_batches_update_one_bounded_waiting_decision(
    case, tmp_path: Path
) -> None:
    path, ids, _values, _repository = case
    runs: list[int] = []
    for index in range(2):
        run_id = _search(case, campaign_name=f"Feedback run {index}")
        relative = (
            f"artifacts/results/result_snapshot_{index + 1:06d}/members.csv.gz"
        )
        members = [f"P-{index}-1", f"P-{index}-2"]
        _write_membership(tmp_path, relative, members)
        snapshot_id = _snapshot(
            case,
            run_id,
            result_cache_key_sha256=str(index + 1) * 64,
            storage_uri=relative,
            snapshot_sha256=str(index + 3) * 64,
            resolved_count=2,
        )
        _complete(case, run_id, snapshot_id)
        result = ingest_feedback(
            path,
            run_id,
            rows=[
                {
                    "person_id": members[0],
                    "outcome": 1,
                    "outcome_at": "2026-09-20T10:00:00Z",
                },
                {
                    "person_id": members[1],
                    "outcome": 0,
                    "outcome_at": "2026-09-20T10:00:00Z",
                },
            ],
            source_name="governed-test",
            idempotency_key=f"bounded-feedback-{index}",
            project_root=tmp_path,
        )
        assert result["recalibration_status"] == "WAITING_FOR_DATA"
        runs.append(run_id)

    with get_connection(path) as connection:
        decisions = connection.execute(
            """SELECT * FROM feedback_retraining_decisions
               WHERE scoring_run_id=? ORDER BY retraining_decision_id""",
            (ids["scoring_run_id"],),
        ).fetchall()
        batches = connection.execute(
            """SELECT selection_basis_sha256 FROM campaign_feedback_batches
               ORDER BY feedback_batch_id"""
        ).fetchall()
    assert len(decisions) == 1
    assert decisions[0]["status"] == "WAITING_FOR_DATA"
    assert decisions[0]["decision_kind"] == "RECALIBRATION"
    assert decisions[0]["label_count"] == 4
    assert decisions[0]["distinct_run_count"] == 2
    assert decisions[0]["latest_feedback_batch_id"] == 2
    assert len({row["selection_basis_sha256"] for row in batches}) == 1


def test_feedback_during_active_recalibration_uses_one_bounded_successor(
    case, tmp_path: Path
) -> None:
    path, ids, _values, _repository = case
    for index in range(2):
        run_id = _search(case, campaign_name=f"Concurrent feedback {index}")
        relative = (
            f"artifacts/results/result_snapshot_{index + 10:06d}/members.csv.gz"
        )
        member = f"ACTIVE-{index}"
        _write_membership(tmp_path, relative, [member])
        snapshot_id = _snapshot(
            case,
            run_id,
            result_cache_key_sha256=str(index + 5) * 64,
            storage_uri=relative,
            snapshot_sha256=str(index + 7) * 64,
            resolved_count=1,
        )
        _complete(case, run_id, snapshot_id)
        result = ingest_feedback(
            path,
            run_id,
            rows=[
                {
                    "person_id": member,
                    "outcome": index,
                    "outcome_at": "2026-09-20T10:00:00Z",
                }
            ],
            source_name="concurrency-test",
            idempotency_key=f"active-feedback-{index}",
            project_root=tmp_path,
        )
        if index == 0:
            with get_connection(path, write=True) as connection:
                connection.execute(
                    """UPDATE feedback_retraining_decisions SET status='TRAINING'
                       WHERE scoring_run_id=? AND status='WAITING_FOR_DATA'""",
                    (ids["scoring_run_id"],),
                )
        else:
            assert result["recalibration_status"] == "WAITING_FOR_DATA"
            assert "already active" in result["recalibration_reason"]

    with get_connection(path) as connection:
        decisions = connection.execute(
            """SELECT status,latest_feedback_batch_id
               FROM feedback_retraining_decisions
               WHERE scoring_run_id=? ORDER BY retraining_decision_id""",
            (ids["scoring_run_id"],),
        ).fetchall()
    assert [row["status"] for row in decisions] == ["TRAINING", "WAITING_FOR_DATA"]
    assert [row["latest_feedback_batch_id"] for row in decisions] == [1, 2]


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
