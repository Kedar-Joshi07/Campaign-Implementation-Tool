from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.main import app
from app.ml.feature_contract import FEATURE_CONTRACT_SHA256
from app.services import model_api_service as model_api_service_module
from app.services import scoring_job_service as scoring_job_service_module
from app.services.model_api_service import (
    MODEL_RUN_NOT_FOUND_MESSAGE,
    MODEL_SCORING_FAILED_MESSAGE,
    SCORING_RUN_NOT_FOUND_MESSAGE,
)
from app.services.model_scoring_compatibility import (
    ModelScoreabilityValidationError,
    ScoreableModelContext,
)
from app.services.scoring_job_service import (
    ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE,
    EXISTING_SCORING_RUN_CONFLICT_MESSAGE,
    MODEL_NOT_SCOREABLE_MESSAGE,
    ScoringJobConflictError,
    ScoringJobSubmissionError,
    ScoringJobValidationError,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "scoring-api.db"
    initialize_database(path)
    return path


@pytest.fixture
def client(database_path: Path):
    app.dependency_overrides[get_database_path] = lambda: database_path
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _insert_analysis_run(database_path: Path, *, status: str = "COMPLETED") -> int:
    completed_at = "2026-08-28T00:00:02Z" if status != "RUNNING" else None
    results_json = "{}" if status == "COMPLETED" else None
    with get_connection(database_path, write=True) as connection:
        customer_import_id = int(
            connection.execute(
                """
                INSERT INTO data_import_runs (
                    dataset_name,
                    source_path,
                    started_at,
                    completed_at,
                    status,
                    rows_read,
                    rows_inserted,
                    rows_rejected,
                    source_checksum
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "customers",
                    "data/customers_fixture.csv",
                    "2026-08-27T23:59:00Z",
                    "2026-08-27T23:59:10Z",
                    "COMPLETED",
                    0,
                    0,
                    0,
                    "c" * 64,
                ),
            ).lastrowid
        )
        campaign_import_id = int(
            connection.execute(
                """
                INSERT INTO data_import_runs (
                    dataset_name,
                    source_path,
                    started_at,
                    completed_at,
                    status,
                    rows_read,
                    rows_inserted,
                    rows_rejected,
                    source_checksum
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "campaign_sales",
                    "data/campaign_sales_fixture.csv",
                    "2026-08-27T23:59:11Z",
                    "2026-08-27T23:59:20Z",
                    "COMPLETED",
                    0,
                    0,
                    0,
                    "d" * 64,
                ),
            ).lastrowid
        )
        cursor = connection.execute(
            """
            INSERT INTO historical_analysis_runs (
                analysis_name, created_at, completed_at, status,
                conversion_definition, filters_json, results_json,
                customer_import_id, customer_source_checksum,
                campaign_sales_import_id, campaign_sales_source_checksum,
                observation_count, selected_customer_count,
                positive_customer_count, unlabeled_customer_count,
                positive_customer_rate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Scoring API fixture",
                "2026-08-28T00:00:00Z",
                completed_at,
                status,
                "ATTRIBUTED_PURCHASE",
                "{}",
                results_json,
                customer_import_id,
                "c" * 64,
                campaign_import_id,
                "d" * 64,
                12,
                5,
                2,
                3,
                0.4,
            ),
        )
        return int(cursor.lastrowid)


def _insert_model_run(database_path: Path, analysis_run_id: int, *, status: str = "RUNNING") -> int:
    completed_at = "2026-08-28T00:20:00Z" if status == "COMPLETED" else None
    with get_connection(database_path, write=True) as connection:
        cursor = connection.execute(
            """
            INSERT INTO model_runs (
                analysis_run_id,
                model_name,
                created_at,
                completed_at,
                status,
                random_seed,
                validation_fraction
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_run_id,
                "Scoring API model",
                "2026-08-28T00:10:00Z",
                completed_at,
                status,
                42,
                0.2,
            ),
        )
        return int(cursor.lastrowid)


def _insert_scoring_job(
    database_path: Path,
    *,
    model_run_id: int,
    status: str,
    created_at: str,
    started_at: str | None,
    finished_at: str | None,
    progress_percent: int,
    stage: str,
    result_payload: dict[str, Any] | None,
    error_message: str | None,
    message: str | None = None,
) -> int:
    with get_connection(database_path, write=True) as connection:
        cursor = connection.execute(
            """
            INSERT INTO jobs (
                job_type,
                status,
                progress_percent,
                stage,
                message,
                analysis_run_id,
                model_run_id,
                created_at,
                started_at,
                finished_at,
                request_json,
                result_json,
                error_message
            ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "PROSPECT_SCORING",
                status,
                progress_percent,
                stage,
                message,
                model_run_id,
                created_at,
                started_at,
                finished_at,
                json.dumps({"model_run_id": model_run_id}, sort_keys=True, separators=(",", ":")),
                (
                    json.dumps(result_payload, sort_keys=True, separators=(",", ":"))
                    if result_payload is not None
                    else None
                ),
                error_message,
            ),
        )
        return int(cursor.lastrowid)


def _insert_scoring_run(
    database_path: Path,
    *,
    job_id: int,
    model_run_id: int,
    status: str,
    created_at: str,
    completed_at: str | None,
    score_summary_json: str | None,
    error_message: str | None,
) -> int:
    with get_connection(database_path, write=True) as connection:
        if status == "COMPLETED":
            scored_person_count = 3
            score_min = 0.1
            score_max = 0.9
            score_mean = 0.4
        elif status == "FAILED":
            scored_person_count = 1
            score_min = None
            score_max = None
            score_mean = None
        else:
            scored_person_count = 1
            score_min = 0.2
            score_max = 0.6
            score_mean = 0.4

        cursor = connection.execute(
            """
            INSERT INTO scoring_runs (
                job_id,
                model_run_id,
                created_at,
                completed_at,
                status,
                demographic_snapshot_count,
                demographic_min_person_id,
                demographic_max_person_id,
                scored_person_count,
                chunk_size,
                last_person_id,
                selected_candidate,
                model_role_policy_version,
                feature_contract_version,
                feature_contract_sha256,
                artifact_sha256,
                score_min,
                score_max,
                score_mean,
                score_summary_json,
                error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                model_run_id,
                created_at,
                completed_at,
                status,
                3,
                "PER_000001",
                "PER_000003",
                scored_person_count,
                1000,
                "PER_000003",
                "BAGGING_PU",
                "2",
                "1",
                "a" * 64,
                "b" * 64,
                score_min,
                score_max,
                score_mean,
                score_summary_json,
                error_message,
            ),
        )
        return int(cursor.lastrowid)


def _insert_demographic_person(database_path: Path, person_id: str) -> None:
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO demographics (
                person_id,
                age,
                gender,
                state,
                individual_yearly_income,
                marital_status,
                education,
                employment_status,
                resident_status,
                resident_type,
                family_member_count,
                number_of_children_in_family,
                number_of_adults_in_family,
                type_of_employment,
                family_yearly_income
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                person_id,
                35,
                "Female",
                "Ohio",
                72_000.0,
                "Single",
                "Bachelors",
                "Employed",
                "Citizen by birth",
                "Inner suburban",
                2,
                0,
                2,
                "Private sector",
                95_000.0,
            ),
        )


def _insert_completed_demographic_import(
    database_path: Path,
    *,
    rows_inserted: int,
    source_checksum: str = "d" * 64,
) -> int:
    with get_connection(database_path, write=True) as connection:
        cursor = connection.execute(
            """
            INSERT INTO data_import_runs (
                dataset_name,
                source_path,
                started_at,
                completed_at,
                status,
                rows_read,
                rows_inserted,
                rows_rejected,
                error_message,
                source_checksum
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "demographics",
                "data/fixture_demographics.csv.gz",
                "2026-08-28T01:00:00Z",
                "2026-08-28T01:00:10Z",
                "COMPLETED",
                rows_inserted,
                rows_inserted,
                0,
                None,
                source_checksum,
            ),
        )
    return int(cursor.lastrowid)


def _scoreable_context(model_run_id: int, analysis_run_id: int) -> ScoreableModelContext:
    return ScoreableModelContext(
        model_run_id=model_run_id,
        analysis_run_id=analysis_run_id,
        selected_candidate="BAGGING_PU",
        model_role_policy_version="2",
        evaluation_contract_version="2",
        feature_contract_version="1",
        feature_contract_sha256=FEATURE_CONTRACT_SHA256,
        artifact_sha256="a" * 64,
        customer_import_id=1,
        customer_source_checksum="c" * 64,
        campaign_sales_import_id=2,
        campaign_sales_source_checksum="d" * 64,
        artifact_payload={"preprocessor": object(), "estimator": object()},
    )


def test_post_score_returns_202_and_persists_queued_job_immediately(
    client: TestClient,
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_analysis_run(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)

    monkeypatch.setattr(
        scoring_job_service_module,
        "validate_scoreable_model",
        lambda *_args, **_kwargs: object(),
    )

    def submit_without_executor(db_path: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
        return scoring_job_service_module.submit_prospect_scoring_job_request(
            db_path,
            payload,
            submitter=lambda *_args, **_kwargs: None,
        )

    monkeypatch.setattr(
        model_api_service_module,
        "submit_prospect_scoring_job_request",
        submit_without_executor,
    )

    response = client.post(f"/api/models/{model_run_id}/score")

    assert response.status_code == 202
    payload = response.json()
    assert payload["job_type"] == "PROSPECT_SCORING"
    assert payload["status"] == "QUEUED"
    assert payload["progress_percent"] == 0
    assert payload["stage"] == "QUEUED"
    assert "analysis_run_id" not in payload
    assert payload["model_run_id"] == model_run_id


def test_post_score_maps_missing_conflict_and_validation_to_expected_status_codes(
    client: TestClient,
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = client.post("/api/models/999999/score")
    assert missing.status_code == 404
    assert missing.json() == {"detail": MODEL_RUN_NOT_FOUND_MESSAGE}

    analysis_run_id = _insert_analysis_run(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)

    monkeypatch.setattr(
        model_api_service_module,
        "submit_prospect_scoring_job_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ScoringJobConflictError(ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE)
        ),
    )
    conflict = client.post(f"/api/models/{model_run_id}/score")
    assert conflict.status_code == 409
    assert conflict.json() == {"detail": ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE}

    monkeypatch.setattr(
        model_api_service_module,
        "submit_prospect_scoring_job_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ScoringJobValidationError(MODEL_NOT_SCOREABLE_MESSAGE)
        ),
    )
    unscoreable = client.post(f"/api/models/{model_run_id}/score")
    assert unscoreable.status_code == 409
    assert unscoreable.json() == {"detail": MODEL_NOT_SCOREABLE_MESSAGE}

    assert client.post("/api/models/0/score").status_code == 422


def test_post_score_submission_failure_is_sanitized_500(
    client: TestClient,
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_analysis_run(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)

    monkeypatch.setattr(
        model_api_service_module,
        "submit_prospect_scoring_job_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ScoringJobSubmissionError("Traceback: private detail")
        ),
    )

    response = client.post(f"/api/models/{model_run_id}/score")

    assert response.status_code == 500
    assert response.json() == {"detail": MODEL_SCORING_FAILED_MESSAGE}
    assert "Traceback" not in response.text


def test_scoring_status_reports_eligibility_and_conflict_signals(
    client: TestClient,
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_analysis_run(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)

    monkeypatch.setattr(
        model_api_service_module,
        "validate_scoreable_model",
        lambda *_args, **_kwargs: _scoreable_context(model_run_id, analysis_run_id),
    )

    eligible = client.get(f"/api/models/{model_run_id}/scoring-status")
    assert eligible.status_code == 200
    eligible_payload = eligible.json()
    assert eligible_payload["eligible"] is True
    assert "reason" not in eligible_payload
    assert eligible_payload["model_run_id"] == model_run_id
    assert eligible_payload["artifact_feature_compatible"] is True
    assert eligible_payload["demographic_source_verified"] is False
    assert "completed_scoring_run" not in eligible_payload

    queued_job_id = _insert_scoring_job(
        database_path,
        model_run_id=model_run_id,
        status="QUEUED",
        created_at="2026-08-28T01:00:00Z",
        started_at=None,
        finished_at=None,
        progress_percent=0,
        stage="QUEUED",
        result_payload=None,
        error_message=None,
    )
    active = client.get(f"/api/models/{model_run_id}/scoring-status")
    assert active.status_code == 200
    active_payload = active.json()
    assert active_payload["eligible"] is False
    assert active_payload["reason"] == ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE
    assert active_payload["demographic_source_verified"] is False
    assert active_payload["active_job"]["job_id"] == queued_job_id

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            UPDATE jobs
            SET status = 'FAILED', stage = 'FAILED', progress_percent = 0,
                finished_at = ?, error_message = ?
            WHERE job_id = ?
            """,
            (
                "2026-08-28T01:00:02Z",
                "fixture",
                queued_job_id,
            ),
        )

    _insert_demographic_person(database_path, "PER_000001")
    _insert_demographic_person(database_path, "PER_000002")
    _insert_demographic_person(database_path, "PER_000003")
    demographic_import_id = _insert_completed_demographic_import(database_path, rows_inserted=3)

    completed_job_id = _insert_scoring_job(
        database_path,
        model_run_id=model_run_id,
        status="COMPLETED",
        created_at="2026-08-28T01:01:00Z",
        started_at="2026-08-28T01:01:00Z",
        finished_at="2026-08-28T01:01:05Z",
        progress_percent=100,
        stage="COMPLETED",
        result_payload={
            "scoring_run_id": 7,
            "model_run_id": model_run_id,
            "scored_person_count": 3,
            "score_min": 0.1,
            "score_max": 0.9,
            "score_mean": 0.4,
            "total_seconds": 1.0,
            "rows_per_second": 3.0,
            "chunk_size": 1000,
            "chunk_count": 1,
            "largest_chunk_rows": 3,
            "largest_transformed_matrix_bytes": 128,
            "selected_candidate": "BAGGING_PU",
            "model_role_policy_version": "2",
            "feature_contract_version": "1",
            "feature_contract_sha256": "a" * 64,
            "artifact_sha256": "a" * 64,
        },
        error_message=None,
    )
    completed_run_id = _insert_scoring_run(
        database_path,
        job_id=completed_job_id,
        model_run_id=model_run_id,
        status="COMPLETED",
        created_at="2026-08-28T01:01:01Z",
        completed_at="2026-08-28T01:01:05Z",
        score_summary_json=json.dumps(
            {
                    "demographic_import_id": demographic_import_id,
                "demographic_source_checksum": "d" * 64,
                "demographic_snapshot_count": 3,
                "demographic_min_person_id": "PER_000001",
                "demographic_max_person_id": "PER_000003",
                "model_run_id": model_run_id,
                "analysis_run_id": analysis_run_id,
                "customer_import_id": 1,
                "customer_source_checksum": "c" * 64,
                "campaign_sales_import_id": 2,
                "campaign_sales_source_checksum": "d" * 64,
                "selected_candidate": "BAGGING_PU",
                "feature_contract_version": "1",
                "feature_contract_sha256": "a" * 64,
                "artifact_sha256": "b" * 64,
                "score_count": 3,
                "score_min": 0.1,
                "score_max": 0.9,
                "score_mean": 0.4,
                "total_seconds": 1.0,
                "rows_per_second": 3.0,
                "chunk_size": 1000,
                "chunk_count": 1,
                "largest_chunk_rows": 3,
                "largest_transformed_matrix_bytes": 128,
                "model_role_policy_version": "2",
                "score_semantics": "LOOK_ALIKE_PROPENSITY_SCORE",
                "age_semantics_note": "fixture",
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        error_message=None,
    )
    with get_connection(database_path, write=True) as connection:
        connection.executemany(
            """
            INSERT INTO propensity_scores (
                scoring_run_id,
                model_run_id,
                person_id,
                propensity_score
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (completed_run_id, model_run_id, "PER_000001", 0.1),
                (completed_run_id, model_run_id, "PER_000002", 0.2),
                (completed_run_id, model_run_id, "PER_000003", 0.9),
            ],
        )

    completed = client.get(f"/api/models/{model_run_id}/scoring-status")
    assert completed.status_code == 200
    completed_payload = completed.json()
    assert completed_payload["eligible"] is False
    assert completed_payload["reason"] == EXISTING_SCORING_RUN_CONFLICT_MESSAGE
    assert completed_payload["demographic_source_verified"] is True
    assert completed_payload["completed_scoring_run"]["scoring_run_id"] == completed_run_id
    assert completed_payload["completed_scoring_run"]["demographic_source_verified"] is True


def test_scoring_status_stale_completed_history_keeps_rescoring_eligible(
    client: TestClient,
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_analysis_run(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)

    monkeypatch.setattr(
        model_api_service_module,
        "validate_scoreable_model",
        lambda *_args, **_kwargs: _scoreable_context(model_run_id, analysis_run_id),
    )

    for person_id in ("PER_000001", "PER_000002", "PER_000003"):
        _insert_demographic_person(database_path, person_id)
    current_import_id = _insert_completed_demographic_import(
        database_path,
        rows_inserted=3,
        source_checksum="e" * 64,
    )

    stale_job_id = _insert_scoring_job(
        database_path,
        model_run_id=model_run_id,
        status="COMPLETED",
        created_at="2026-08-28T01:06:00Z",
        started_at="2026-08-28T01:06:00Z",
        finished_at="2026-08-28T01:06:05Z",
        progress_percent=100,
        stage="COMPLETED",
        result_payload={"scoring_run_id": 9, "model_run_id": model_run_id, "scored_person_count": 3},
        error_message=None,
    )
    stale_run_id = _insert_scoring_run(
        database_path,
        job_id=stale_job_id,
        model_run_id=model_run_id,
        status="COMPLETED",
        created_at="2026-08-28T01:06:01Z",
        completed_at="2026-08-28T01:06:05Z",
        score_summary_json=json.dumps(
            {
                "demographic_import_id": current_import_id,
                "demographic_source_checksum": "d" * 64,
                "demographic_snapshot_count": 3,
                "demographic_min_person_id": "PER_000001",
                "demographic_max_person_id": "PER_000003",
                "model_run_id": model_run_id,
                "analysis_run_id": analysis_run_id,
                "customer_import_id": 1,
                "customer_source_checksum": "c" * 64,
                "campaign_sales_import_id": 2,
                "campaign_sales_source_checksum": "d" * 64,
                "selected_candidate": "BAGGING_PU",
                "feature_contract_version": "1",
                "feature_contract_sha256": "a" * 64,
                "artifact_sha256": "b" * 64,
                "score_count": 3,
                "score_min": 0.12,
                "score_max": 0.92,
                "score_mean": 0.42,
                "total_seconds": 1.0,
                "rows_per_second": 3.0,
                "chunk_size": 1000,
                "chunk_count": 1,
                "largest_chunk_rows": 3,
                "largest_transformed_matrix_bytes": 128,
                "model_role_policy_version": "2",
                "score_semantics": "LOOK_ALIKE_PROPENSITY_SCORE",
                "age_semantics_note": "fixture",
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        error_message=None,
    )
    with get_connection(database_path, write=True) as connection:
        connection.executemany(
            """
            INSERT INTO propensity_scores (
                scoring_run_id,
                model_run_id,
                person_id,
                propensity_score
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (stale_run_id, model_run_id, "PER_000001", 0.12),
                (stale_run_id, model_run_id, "PER_000002", 0.22),
                (stale_run_id, model_run_id, "PER_000003", 0.92),
            ],
        )

    response = client.get(f"/api/models/{model_run_id}/scoring-status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["eligible"] is True
    assert payload["demographic_source_verified"] is False
    assert payload["completed_scoring_run"]["scoring_run_id"] == stale_run_id
    assert payload["completed_scoring_run"]["demographic_source_verified"] is False


def test_scoring_status_handles_unscoreable_and_missing_models(
    client: TestClient,
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert client.get("/api/models/999999/scoring-status").status_code == 404

    analysis_run_id = _insert_analysis_run(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)

    monkeypatch.setattr(
        model_api_service_module,
        "validate_scoreable_model",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ModelScoreabilityValidationError("artifact or feature contract mismatch")
        ),
    )

    response = client.get(f"/api/models/{model_run_id}/scoring-status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["eligible"] is False
    assert payload["reason"] == "artifact or feature contract mismatch"
    assert payload["artifact_feature_compatible"] is False


def test_scoring_status_prefers_current_source_canonical_run_over_newer_stale_run(
    client: TestClient,
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_analysis_run(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)

    monkeypatch.setattr(
        model_api_service_module,
        "validate_scoreable_model",
        lambda *_args, **_kwargs: _scoreable_context(model_run_id, analysis_run_id),
    )

    for person_id in ("PER_000001", "PER_000002", "PER_000003"):
        _insert_demographic_person(database_path, person_id)
    canonical_import_id = _insert_completed_demographic_import(
        database_path,
        rows_inserted=3,
        source_checksum="e" * 64,
    )

    canonical_job_id = _insert_scoring_job(
        database_path,
        model_run_id=model_run_id,
        status="COMPLETED",
        created_at="2026-08-28T01:02:00Z",
        started_at="2026-08-28T01:02:00Z",
        finished_at="2026-08-28T01:02:05Z",
        progress_percent=100,
        stage="COMPLETED",
        result_payload={"scoring_run_id": 7, "model_run_id": model_run_id, "scored_person_count": 3},
        error_message=None,
    )
    canonical_run_id = _insert_scoring_run(
        database_path,
        job_id=canonical_job_id,
        model_run_id=model_run_id,
        status="COMPLETED",
        created_at="2026-08-28T01:02:01Z",
        completed_at="2026-08-28T01:02:05Z",
        score_summary_json=json.dumps(
            {
                "demographic_import_id": canonical_import_id,
                "demographic_source_checksum": "e" * 64,
                "demographic_snapshot_count": 3,
                "demographic_min_person_id": "PER_000001",
                "demographic_max_person_id": "PER_000003",
                "model_run_id": model_run_id,
                "analysis_run_id": analysis_run_id,
                "customer_import_id": 1,
                "customer_source_checksum": "c" * 64,
                "campaign_sales_import_id": 2,
                "campaign_sales_source_checksum": "d" * 64,
                "selected_candidate": "BAGGING_PU",
                "feature_contract_version": "1",
                "feature_contract_sha256": "a" * 64,
                "artifact_sha256": "b" * 64,
                "score_count": 3,
                "score_min": 0.1,
                "score_max": 0.9,
                "score_mean": 0.4,
                "total_seconds": 1.0,
                "rows_per_second": 3.0,
                "chunk_size": 1000,
                "chunk_count": 1,
                "largest_chunk_rows": 3,
                "largest_transformed_matrix_bytes": 128,
                "model_role_policy_version": "2",
                "score_semantics": "LOOK_ALIKE_PROPENSITY_SCORE",
                "age_semantics_note": "fixture",
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        error_message=None,
    )
    with get_connection(database_path, write=True) as connection:
        connection.executemany(
            """
            INSERT INTO propensity_scores (
                scoring_run_id,
                model_run_id,
                person_id,
                propensity_score
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (canonical_run_id, model_run_id, "PER_000001", 0.1),
                (canonical_run_id, model_run_id, "PER_000002", 0.2),
                (canonical_run_id, model_run_id, "PER_000003", 0.9),
            ],
        )

    stale_job_id = _insert_scoring_job(
        database_path,
        model_run_id=model_run_id,
        status="COMPLETED",
        created_at="2026-08-28T01:04:00Z",
        started_at="2026-08-28T01:04:00Z",
        finished_at="2026-08-28T01:04:05Z",
        progress_percent=100,
        stage="COMPLETED",
        result_payload={"scoring_run_id": 8, "model_run_id": model_run_id, "scored_person_count": 3},
        error_message=None,
    )
    stale_run_id = _insert_scoring_run(
        database_path,
        job_id=stale_job_id,
        model_run_id=model_run_id,
        status="COMPLETED",
        created_at="2026-08-28T01:04:01Z",
        completed_at="2026-08-28T01:04:05Z",
        score_summary_json=json.dumps(
            {
                "demographic_import_id": canonical_import_id,
                "demographic_source_checksum": "d" * 64,
                "demographic_snapshot_count": 3,
                "demographic_min_person_id": "PER_000001",
                "demographic_max_person_id": "PER_000003",
                "model_run_id": model_run_id,
                "analysis_run_id": analysis_run_id,
                "customer_import_id": 1,
                "customer_source_checksum": "c" * 64,
                "campaign_sales_import_id": 2,
                "campaign_sales_source_checksum": "d" * 64,
                "selected_candidate": "BAGGING_PU",
                "feature_contract_version": "1",
                "feature_contract_sha256": "a" * 64,
                "artifact_sha256": "b" * 64,
                "score_count": 3,
                "score_min": 0.11,
                "score_max": 0.91,
                "score_mean": 0.41,
                "total_seconds": 1.0,
                "rows_per_second": 3.0,
                "chunk_size": 1000,
                "chunk_count": 1,
                "largest_chunk_rows": 3,
                "largest_transformed_matrix_bytes": 128,
                "model_role_policy_version": "2",
                "score_semantics": "LOOK_ALIKE_PROPENSITY_SCORE",
                "age_semantics_note": "fixture",
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        error_message=None,
    )
    with get_connection(database_path, write=True) as connection:
        connection.executemany(
            """
            INSERT INTO propensity_scores (
                scoring_run_id,
                model_run_id,
                person_id,
                propensity_score
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (stale_run_id, model_run_id, "PER_000001", 0.11),
                (stale_run_id, model_run_id, "PER_000002", 0.21),
                (stale_run_id, model_run_id, "PER_000003", 0.91),
            ],
        )

    response = client.get(f"/api/models/{model_run_id}/scoring-status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["eligible"] is False
    assert payload["reason"] == EXISTING_SCORING_RUN_CONFLICT_MESSAGE
    assert payload["demographic_source_verified"] is True
    assert payload["completed_scoring_run"]["scoring_run_id"] == canonical_run_id
    assert payload["completed_scoring_run"]["demographic_source_verified"] is True

    stale_detail = client.get(f"/api/scoring-runs/{stale_run_id}")
    assert stale_detail.status_code == 200
    assert stale_detail.json()["score_summary"]["demographic_source_verified"] is False


def test_scoring_runs_list_and_detail_support_filters_and_newest_first(
    client: TestClient,
    database_path: Path,
) -> None:
    analysis_run_id = _insert_analysis_run(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)

    failed_job_id = _insert_scoring_job(
        database_path,
        model_run_id=model_run_id,
        status="FAILED",
        created_at="2026-08-28T02:00:00Z",
        started_at="2026-08-28T02:00:00Z",
        finished_at="2026-08-28T02:00:05Z",
        progress_percent=30,
        stage="FAILED",
        result_payload=None,
        error_message="failed fixture",
    )
    _insert_scoring_run(
        database_path,
        job_id=failed_job_id,
        model_run_id=model_run_id,
        status="FAILED",
        created_at="2026-08-28T02:00:01Z",
        completed_at="2026-08-28T02:00:05Z",
        score_summary_json=json.dumps({"partial_scored_person_count": 1}),
        error_message="failed fixture",
    )

    completed_job_id = _insert_scoring_job(
        database_path,
        model_run_id=model_run_id,
        status="COMPLETED",
        created_at="2026-08-28T02:05:00Z",
        started_at="2026-08-28T02:05:00Z",
        finished_at="2026-08-28T02:05:05Z",
        progress_percent=100,
        stage="COMPLETED",
        result_payload={
            "scoring_run_id": 5,
            "model_run_id": model_run_id,
            "scored_person_count": 3,
            "score_min": 0.1,
            "score_max": 0.9,
            "score_mean": 0.4,
            "total_seconds": 1.0,
            "rows_per_second": 3.0,
            "chunk_size": 1000,
            "chunk_count": 1,
            "largest_chunk_rows": 3,
            "largest_transformed_matrix_bytes": 128,
            "selected_candidate": "BAGGING_PU",
            "model_role_policy_version": "2",
            "feature_contract_version": "1",
            "feature_contract_sha256": "a" * 64,
            "artifact_sha256": "a" * 64,
        },
        error_message=None,
    )
    completed_run_id = _insert_scoring_run(
        database_path,
        job_id=completed_job_id,
        model_run_id=model_run_id,
        status="COMPLETED",
        created_at="2026-08-28T02:05:01Z",
        completed_at="2026-08-28T02:05:05Z",
        score_summary_json=json.dumps(
            {
                "score_count": 3,
                "score_min": 0.1,
                "score_max": 0.9,
                "score_mean": 0.4,
                "total_seconds": 1.0,
                "rows_per_second": 3.0,
                "chunk_size": 1000,
                "chunk_count": 1,
                "largest_chunk_rows": 3,
                "largest_transformed_matrix_bytes": 128,
                "selected_candidate": "BAGGING_PU",
                "model_role_policy_version": "2",
                "feature_contract_version": "1",
                "feature_contract_sha256": "a" * 64,
                "artifact_sha256": "a" * 64,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        error_message=None,
    )

    listing = client.get("/api/scoring-runs", params={"limit": 20, "offset": 0})
    assert listing.status_code == 200
    list_payload = listing.json()
    assert len(list_payload) == 2
    assert list_payload[0]["scoring_run_id"] == completed_run_id
    assert list_payload[0]["status"] == "COMPLETED"

    filtered = client.get(
        "/api/scoring-runs",
        params={"status": "FAILED", "model_run_id": model_run_id},
    )
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert len(filtered_payload) == 1
    assert filtered_payload[0]["status"] == "FAILED"

    assert client.get("/api/scoring-runs", params={"status": "QUEUED"}).status_code == 422
    assert client.get("/api/scoring-runs", params={"limit": 0}).status_code == 422
    assert client.get("/api/scoring-runs", params={"offset": -1}).status_code == 422

    detail = client.get(f"/api/scoring-runs/{completed_run_id}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["identity"]["scoring_run_id"] == completed_run_id
    assert detail_payload["population"]["demographic_snapshot_count"] == 3
    assert detail_payload["model_contract"]["selected_candidate"] == "BAGGING_PU"
    assert detail_payload["score_summary"]["score_mean"] == 0.4
    assert detail_payload["job"]["job_id"] == completed_job_id
    for forbidden in ("person_id", "customer_id", "traceback", "select ", "raw_features"):
        assert forbidden not in detail.text.casefold()


def test_scoring_run_detail_404_and_summary_safety_guards(
    client: TestClient,
    database_path: Path,
) -> None:
    missing = client.get("/api/scoring-runs/999999")
    assert missing.status_code == 404
    assert missing.json() == {"detail": SCORING_RUN_NOT_FOUND_MESSAGE}

    analysis_run_id = _insert_analysis_run(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)

    forbidden_job_id = _insert_scoring_job(
        database_path,
        model_run_id=model_run_id,
        status="FAILED",
        created_at="2026-08-28T03:00:00Z",
        started_at="2026-08-28T03:00:00Z",
        finished_at="2026-08-28T03:00:03Z",
        progress_percent=40,
        stage="FAILED",
        result_payload=None,
        error_message="failed",
    )
    forbidden_run_id = _insert_scoring_run(
        database_path,
        job_id=forbidden_job_id,
        model_run_id=model_run_id,
        status="FAILED",
        created_at="2026-08-28T03:00:01Z",
        completed_at="2026-08-28T03:00:03Z",
        score_summary_json=json.dumps({"person_id": "PER_000001"}),
        error_message="failed",
    )

    forbidden = client.get(f"/api/scoring-runs/{forbidden_run_id}")
    assert forbidden.status_code == 422

    non_finite_job_id = _insert_scoring_job(
        database_path,
        model_run_id=model_run_id,
        status="FAILED",
        created_at="2026-08-28T03:10:00Z",
        started_at="2026-08-28T03:10:00Z",
        finished_at="2026-08-28T03:10:03Z",
        progress_percent=40,
        stage="FAILED",
        result_payload=None,
        error_message="failed",
    )
    non_finite_run_id = _insert_scoring_run(
        database_path,
        job_id=non_finite_job_id,
        model_run_id=model_run_id,
        status="FAILED",
        created_at="2026-08-28T03:10:01Z",
        completed_at="2026-08-28T03:10:03Z",
        score_summary_json='{"score_mean": NaN}',
        error_message="failed",
    )

    non_finite = client.get(f"/api/scoring-runs/{non_finite_run_id}")
    assert non_finite.status_code == 422


def test_job_detail_supports_scoring_results_and_sanitized_failures(
    client: TestClient,
    database_path: Path,
) -> None:
    analysis_run_id = _insert_analysis_run(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)

    completed_job_id = _insert_scoring_job(
        database_path,
        model_run_id=model_run_id,
        status="COMPLETED",
        created_at="2026-08-28T04:00:00Z",
        started_at="2026-08-28T04:00:00Z",
        finished_at="2026-08-28T04:00:05Z",
        progress_percent=100,
        stage="COMPLETED",
        result_payload={
            "scoring_run_id": 9,
            "model_run_id": model_run_id,
            "scored_person_count": 3,
            "score_min": 0.1,
            "score_max": 0.9,
            "score_mean": 0.4,
            "total_seconds": 1.0,
            "rows_per_second": 3.0,
            "chunk_size": 1000,
            "chunk_count": 1,
            "largest_chunk_rows": 3,
            "largest_transformed_matrix_bytes": 128,
            "selected_candidate": "BAGGING_PU",
            "model_role_policy_version": "2",
            "feature_contract_version": "1",
            "feature_contract_sha256": "a" * 64,
            "artifact_sha256": "a" * 64,
        },
        error_message=None,
    )

    completed = client.get(f"/api/jobs/{completed_job_id}")
    assert completed.status_code == 200
    completed_payload = completed.json()
    assert completed_payload["job_type"] == "PROSPECT_SCORING"
    assert completed_payload["result"]["scoring_run_id"] == 9

    failed_job_id = _insert_scoring_job(
        database_path,
        model_run_id=model_run_id,
        status="FAILED",
        created_at="2026-08-28T04:10:00Z",
        started_at="2026-08-28T04:10:00Z",
        finished_at="2026-08-28T04:10:04Z",
        progress_percent=60,
        stage="FAILED",
        result_payload=None,
        error_message="Traceback: C:\\\\private\\\\db.sqlite SELECT * FROM propensity_scores",
    )

    failed = client.get(f"/api/jobs/{failed_job_id}")
    assert failed.status_code == 200
    failed_payload = failed.json()
    assert failed_payload["failure_message"] == MODEL_SCORING_FAILED_MESSAGE
    for forbidden in ("Traceback", "SELECT *", "C:\\private"):
        assert forbidden not in failed.text

    forbidden_job_id = _insert_scoring_job(
        database_path,
        model_run_id=model_run_id,
        status="COMPLETED",
        created_at="2026-08-28T04:20:00Z",
        started_at="2026-08-28T04:20:00Z",
        finished_at="2026-08-28T04:20:05Z",
        progress_percent=100,
        stage="COMPLETED",
        result_payload={"person_id": "PER_123"},
        error_message=None,
    )

    forbidden_job = client.get(f"/api/jobs/{forbidden_job_id}")
    assert forbidden_job.status_code == 422
