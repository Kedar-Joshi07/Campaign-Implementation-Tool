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
from app.ml.feature_contract import (
    FEATURE_CONTRACT_JSON,
    FEATURE_CONTRACT_SHA256,
    FEATURE_CONTRACT_VERSION,
    ORDERED_FEATURES,
)
from app.services import model_api_service as model_api_service_module
from app.services import model_job_service as model_job_service_module
from app.services.model_api_service import (
    JOB_NOT_FOUND_MESSAGE,
    MODEL_RUN_NOT_FOUND_MESSAGE,
    MODEL_TRAINING_FAILED_MESSAGE,
)
from app.services.model_job_service import (
    ACTIVE_JOB_CONFLICT_MESSAGE,
    ANALYSIS_NOT_AVAILABLE_MESSAGE,
    ModelJobConflictError,
    ModelJobSubmissionError,
    ModelJobValidationError,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "private" / "model-api.db"
    initialize_database(path)
    return path


@pytest.fixture
def client(database_path: Path):
    app.dependency_overrides[get_database_path] = lambda: database_path
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _insert_analysis_run(database_path: Path, *, status: str) -> int:
    completed_at = "2026-08-21T00:00:02Z" if status != "RUNNING" else None
    results_json = "{}" if status == "COMPLETED" else None
    filters_json = json.dumps(
        {
            "campaign_ids": [],
            "product_ids": [],
            "product_categories": [],
            "campaign_channels": [],
            "campaign_types": [],
            "contact_date_from": "2025-01-01",
            "contact_date_to": "2025-12-31",
            "contacted_only": True,
            "conversion_definition": "ATTRIBUTED_PURCHASE",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    with get_connection(database_path, write=True) as connection:
        cursor = connection.execute(
            """
            INSERT INTO historical_analysis_runs (
                analysis_name, created_at, completed_at, status,
                conversion_definition, filters_json, results_json,
                observation_count, selected_customer_count,
                positive_customer_count, unlabeled_customer_count,
                positive_customer_rate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"Analysis {status}",
                "2026-08-21T00:00:00Z",
                completed_at,
                status,
                "ATTRIBUTED_PURCHASE",
                filters_json,
                results_json,
                12,
                5,
                2,
                3,
                0.4,
            ),
        )
        return int(cursor.lastrowid)


def _insert_model_run(
    database_path: Path,
    *,
    analysis_run_id: int,
    status: str,
    model_name: str,
    selected_candidate: str | None,
    metrics: dict[str, Any] | None,
    created_at: str,
) -> int:
    completed_at = "2026-08-21T00:20:00Z" if status != "RUNNING" else None
    feature_contract_json = FEATURE_CONTRACT_JSON
    preprocessing_json = json.dumps({"transformed_feature_count": 3})
    hyperparameters_json = json.dumps({"model_role_policy_version": "2"})
    metrics_json = json.dumps(metrics, sort_keys=True, separators=(",", ":")) if metrics else None
    library_versions_json = json.dumps({"python": "3.12.0"})
    with get_connection(database_path, write=True) as connection:
        cursor = connection.execute(
            """
            INSERT INTO model_runs (
                analysis_run_id,
                model_name,
                created_at,
                completed_at,
                status,
                algorithm,
                selected_candidate,
                random_seed,
                validation_fraction,
                reconstructed_observation_count,
                selected_customer_count,
                positive_customer_count,
                unlabeled_customer_count,
                train_customer_count,
                validation_customer_count,
                train_positive_count,
                validation_positive_count,
                feature_contract_json,
                preprocessing_json,
                hyperparameters_json,
                metrics_json,
                library_versions_json,
                artifact_path,
                artifact_sha256,
                error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_run_id,
                model_name,
                created_at,
                completed_at,
                status,
                "pulearn.BaggingPuClassifier" if selected_candidate else None,
                selected_candidate,
                42,
                0.2,
                12,
                5,
                2,
                3,
                4,
                1,
                1,
                1,
                feature_contract_json,
                preprocessing_json,
                hyperparameters_json,
                metrics_json,
                library_versions_json,
                "artifacts/models/model_run_000123/pu_model.joblib" if status == "COMPLETED" else None,
                "a" * 64 if status == "COMPLETED" else None,
                None,
            ),
        )
        return int(cursor.lastrowid)


def _v2_metrics(selected_candidate: str, *, challenger_status: str) -> dict[str, Any]:
    challenger_snapshot: dict[str, Any]
    if challenger_status == "FITTED":
        challenger_snapshot = {
            "name": "ELKAN_NOTO_LOGISTIC",
            "candidate_role": "CHALLENGER_1",
            "status": "FITTED",
            "is_genuine_pu": True,
            "top_slice_metrics": {
                "top_10_percent": {
                    "known_positive_lift_at_k": 1.25,
                    "known_positive_recall_at_k": 0.2,
                }
            },
            "runtime": {"fit_seconds": 0.1, "scoring_seconds": 0.01},
            "quality_flags": [],
        }
    else:
        challenger_snapshot = {
            "name": "ELKAN_NOTO_LOGISTIC",
            "candidate_role": "CHALLENGER_1",
            "status": challenger_status,
            "is_genuine_pu": True,
            "skip_reason": "disabled by request",
            "runtime": {"fit_seconds": 0.0, "scoring_seconds": 0.0},
            "quality_flags": ["CHALLENGER_1_SKIPPED"],
        }

    return {
        "evaluation_contract_version": "2",
        "model_role_policy_version": "2",
        "primary_candidate": "BAGGING_PU",
        "challenger_candidates": ["ELKAN_NOTO_LOGISTIC"],
        "diagnostic_controls": ["NAIVE_PU_LABEL_BASELINE"],
        "selection_policy": "PRIMARY_ROLE_GOVERNED",
        "selected_candidate": selected_candidate,
        "quality_flags": ["OBSERVED_LABEL_METRICS_ONLY"],
        "candidate_results": {
            "BAGGING_PU": {
                "name": "BAGGING_PU",
                "candidate_role": "PRIMARY",
                "status": "FITTED",
                "is_genuine_pu": True,
                "top_slice_metrics": {
                    "top_10_percent": {
                        "known_positive_lift_at_k": 1.4,
                        "known_positive_recall_at_k": 0.3,
                    }
                },
                "runtime": {"fit_seconds": 0.2, "scoring_seconds": 0.02},
                "quality_flags": [],
            },
            "ELKAN_NOTO_LOGISTIC": challenger_snapshot,
            "NAIVE_PU_LABEL_BASELINE": {
                "name": "NAIVE_PU_LABEL_BASELINE",
                "candidate_role": "DIAGNOSTIC_CONTROL",
                "status": "FITTED",
                "is_genuine_pu": False,
                "top_slice_metrics": {
                    "top_10_percent": {
                        "known_positive_lift_at_k": 1.1,
                        "known_positive_recall_at_k": 0.2,
                    }
                },
                "runtime": {"fit_seconds": 0.05, "scoring_seconds": 0.01},
                "quality_flags": [],
            },
        },
        "challenger_comparison": {
            "challenger": "ELKAN_NOTO_LOGISTIC",
            "primary": "BAGGING_PU",
            "status": "EVALUATED" if challenger_status == "FITTED" else challenger_status,
            "challenger_outperformed_primary": challenger_status == "FITTED",
            "outperformed_metrics": ["top_20_recall"] if challenger_status == "FITTED" else [],
            "challenger_minus_primary_deltas": {
                "top_10_lift": -0.15,
                "top_10_recall": -0.1,
            },
        },
    }


def test_openapi_exposes_phase5_model_job_and_scoring_endpoints(client: TestClient) -> None:
    schema = client.get("/openapi.json")

    assert schema.status_code == 200
    paths = schema.json()["paths"]
    model_operations = {
        (path, method)
        for path, operations in paths.items()
        for method in operations
        if (
            path.startswith("/api/models")
            or path.startswith("/api/jobs")
            or path.startswith("/api/scoring-runs")
            or path.startswith("/api/audience")
        )
    }
    assert model_operations == {
        ("/api/audience/estimate", "post"),
        ("/api/audience/options", "get"),
        ("/api/audience/profile", "post"),
        ("/api/audience/search", "post"),
        ("/api/audience/runs", "get"),
        ("/api/audience/runs/{scoring_run_id}/prepare", "post"),
        ("/api/audience/runs/{scoring_run_id}/preparation-status", "get"),
        ("/api/audiences", "get"),
        ("/api/audiences", "post"),
        ("/api/audiences/{audience_id}", "get"),
        ("/api/audiences/{audience_id}/currentness", "get"),
        ("/api/models/train", "post"),
        ("/api/models/{model_run_id}/score", "post"),
        ("/api/models/{model_run_id}/scoring-status", "get"),
        ("/api/jobs/{job_id}", "get"),
        ("/api/models", "get"),
        ("/api/models/{model_run_id}", "get"),
        ("/api/models/training-options", "get"),
        ("/api/scoring-runs", "get"),
        ("/api/scoring-runs/{scoring_run_id}", "get"),
    }


def test_train_returns_202_and_persists_queued_job_immediately(
    client: TestClient,
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_analysis_run(database_path, status="COMPLETED")

    def submit_without_executor(db_path: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
        return model_job_service_module.submit_model_training_job_request(
            db_path,
            payload,
            submitter=lambda *_args, **_kwargs: None,
        )

    monkeypatch.setattr(
        model_api_service_module,
        "submit_model_training_job_request",
        submit_without_executor,
    )

    response = client.post(
        "/api/models/train",
        json={
            "analysis_run_id": analysis_run_id,
            "model_name": " Holiday model ",
            "random_seed": 13,
            "validation_fraction": 0.3,
            "run_elkan_challenger": False,
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["job_type"] == "MODEL_TRAINING"
    assert payload["status"] == "QUEUED"
    assert payload["progress_percent"] == 0
    assert payload["stage"] == "QUEUED"
    assert payload["analysis_run_id"] == analysis_run_id


def test_train_conflict_and_unusable_analysis_map_to_409(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        model_api_service_module,
        "submit_model_training_job_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ModelJobConflictError(ACTIVE_JOB_CONFLICT_MESSAGE)
        ),
    )
    conflict = client.post("/api/models/train", json={"analysis_run_id": 10})
    assert conflict.status_code == 409
    assert conflict.json() == {"detail": ACTIVE_JOB_CONFLICT_MESSAGE}

    monkeypatch.setattr(
        model_api_service_module,
        "submit_model_training_job_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ModelJobValidationError(ANALYSIS_NOT_AVAILABLE_MESSAGE)
        ),
    )
    unusable = client.post("/api/models/train", json={"analysis_run_id": 10})
    assert unusable.status_code == 409
    assert unusable.json() == {"detail": ANALYSIS_NOT_AVAILABLE_MESSAGE}


def test_train_request_validation_is_422(client: TestClient) -> None:
    response = client.post(
        "/api/models/train",
        json={"analysis_run_id": 0, "unexpected": "value"},
    )
    assert response.status_code == 422


def test_train_worker_submission_failure_maps_to_500(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        model_api_service_module,
        "submit_model_training_job_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ModelJobSubmissionError("internal worker failure")
        ),
    )

    response = client.post("/api/models/train", json={"analysis_run_id": 10})

    assert response.status_code == 500
    assert response.json() == {"detail": MODEL_TRAINING_FAILED_MESSAGE}
    assert "internal worker failure" not in response.text


def test_get_job_returns_sanitized_failed_job_and_404_for_unknown(
    client: TestClient,
    database_path: Path,
) -> None:
    analysis_run_id = _insert_analysis_run(database_path, status="COMPLETED")
    repository = model_job_service_module.JobRepository(database_path)
    job_id = repository.create_training_job(
        created_at="2026-08-21T01:00:00Z",
        request_payload={"analysis_run_id": analysis_run_id},
    )
    repository.mark_failed(
        job_id=job_id,
        finished_at="2026-08-21T01:00:01Z",
        error_message="Traceback:\nC:\\private\\db.sqlite\nSELECT * FROM model_runs",
        message="internal failure",
    )

    response = client.get(f"/api/jobs/{job_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "FAILED"
    assert payload["failure_message"] == "Model training could not be completed."
    public_text = response.text
    for forbidden in ("Traceback", "SELECT *", "C:\\private"):
        assert forbidden not in public_text

    unknown = client.get("/api/jobs/999999")
    assert unknown.status_code == 404
    assert unknown.json() == {"detail": JOB_NOT_FOUND_MESSAGE}


def test_models_list_supports_pagination_filtering_and_newest_first(
    client: TestClient,
    database_path: Path,
) -> None:
    analysis_run_id = _insert_analysis_run(database_path, status="COMPLETED")
    _insert_model_run(
        database_path,
        analysis_run_id=analysis_run_id,
        status="RUNNING",
        model_name="Running model",
        selected_candidate=None,
        metrics=None,
        created_at="2026-08-21T01:00:00Z",
    )
    completed_id = _insert_model_run(
        database_path,
        analysis_run_id=analysis_run_id,
        status="COMPLETED",
        model_name="Completed model",
        selected_candidate="BAGGING_PU",
        metrics=_v2_metrics("BAGGING_PU", challenger_status="FITTED"),
        created_at="2026-08-21T01:10:00Z",
    )

    listing = client.get("/api/models", params={"limit": 20, "offset": 0})
    assert listing.status_code == 200
    payload = listing.json()
    assert payload[0]["model_run_id"] == completed_id
    assert payload[0]["status"] == "COMPLETED"
    assert payload[0]["validation_lift_at_10_percent"] == 1.4

    filtered = client.get("/api/models", params={"status": "RUNNING"})
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["status"] == "RUNNING"

    assert client.get("/api/models", params={"limit": 0}).status_code == 422
    assert client.get("/api/models", params={"offset": -1}).status_code == 422
    assert client.get("/api/models", params={"status": "QUEUED"}).status_code == 422


def test_model_detail_supports_role_policy_v2_and_challenger_skipped(
    client: TestClient,
    database_path: Path,
) -> None:
    analysis_run_id = _insert_analysis_run(database_path, status="COMPLETED")
    model_run_id = _insert_model_run(
        database_path,
        analysis_run_id=analysis_run_id,
        status="COMPLETED",
        model_name="V2 model",
        selected_candidate="BAGGING_PU",
        metrics=_v2_metrics("BAGGING_PU", challenger_status="SKIPPED_DISABLED"),
        created_at="2026-08-21T02:00:00Z",
    )

    detail = client.get(f"/api/models/{model_run_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["identity"]["model_run_id"] == model_run_id
    assert payload["governance"]["is_legacy"] is False
    assert payload["governance"]["model_role_policy_version"] == "2"
    assert payload["governance"]["selection_policy"] == "PRIMARY_ROLE_GOVERNED"
    assert payload["feature_contract"]["feature_contract_version"] == FEATURE_CONTRACT_VERSION
    assert payload["feature_contract"]["feature_contract_sha256"] == FEATURE_CONTRACT_SHA256
    assert payload["feature_contract"]["ordered_features"] == list(ORDERED_FEATURES)
    assert payload["candidates"]["ELKAN_NOTO_LOGISTIC"]["status"] == "SKIPPED_DISABLED"
    assert payload["artifact"]["verified"] is False
    assert payload["artifact"]["verification_message"] == (
        "The model artifact could not be verified."
    )


def test_model_detail_rejects_malformed_feature_contract_metadata(
    client: TestClient,
    database_path: Path,
) -> None:
    analysis_run_id = _insert_analysis_run(database_path, status="COMPLETED")
    model_run_id = _insert_model_run(
        database_path,
        analysis_run_id=analysis_run_id,
        status="COMPLETED",
        model_name="Malformed feature contract",
        selected_candidate="BAGGING_PU",
        metrics=_v2_metrics("BAGGING_PU", challenger_status="FITTED"),
        created_at="2026-08-21T02:05:00Z",
    )

    malformed_contract = json.dumps(
        {
            "version": "1",
            "ordered_features": ["age", "gender"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "UPDATE model_runs SET feature_contract_json = ? WHERE model_run_id = ?",
            (malformed_contract, model_run_id),
        )

    detail = client.get(f"/api/models/{model_run_id}")

    assert detail.status_code == 422
    assert detail.json() == {"detail": "feature_contract metadata is invalid."}


def test_model_detail_legacy_run_is_not_reinterpreted_as_v2(
    client: TestClient,
    database_path: Path,
) -> None:
    analysis_run_id = _insert_analysis_run(database_path, status="COMPLETED")
    model_run_id = _insert_model_run(
        database_path,
        analysis_run_id=analysis_run_id,
        status="COMPLETED",
        model_name="Legacy model",
        selected_candidate="ELKAN_NOTO_LOGISTIC",
        metrics={
            "selected_candidate": "ELKAN_NOTO_LOGISTIC",
            "selection_policy": "HIGHEST_TOP10_LIFT",
            "candidate_results": {
                "ELKAN_NOTO_LOGISTIC": {
                    "top_slice_metrics": {
                        "top_10_percent": {"known_positive_lift_at_k": 1.3}
                    }
                }
            },
            "quality_flags": ["OBSERVED_LABEL_METRICS_ONLY"],
        },
        created_at="2026-08-21T03:00:00Z",
    )

    detail = client.get(f"/api/models/{model_run_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["governance"]["is_legacy"] is True
    assert payload["governance"]["model_role_policy_version"] is None


def test_model_detail_not_found_and_no_sensitive_leakage(
    client: TestClient,
    database_path: Path,
) -> None:
    missing = client.get("/api/models/999999")
    assert missing.status_code == 404
    assert missing.json() == {"detail": MODEL_RUN_NOT_FOUND_MESSAGE}

    analysis_run_id = _insert_analysis_run(database_path, status="COMPLETED")
    model_run_id = _insert_model_run(
        database_path,
        analysis_run_id=analysis_run_id,
        status="COMPLETED",
        model_name="Leakage check model",
        selected_candidate="BAGGING_PU",
        metrics=_v2_metrics("BAGGING_PU", challenger_status="FITTED"),
        created_at="2026-08-21T03:10:00Z",
    )

    detail = client.get(f"/api/models/{model_run_id}")
    assert detail.status_code == 200
    text = detail.text
    for forbidden in (
        "customer_id",
        "person_id",
        "validation_scores",
        "train_matrix",
        "SELECT ",
        "C:\\private",
    ):
        assert forbidden not in text


def test_model_detail_reports_artifact_checksum_drift_safely(
    client: TestClient,
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    analysis_run_id = _insert_analysis_run(database_path, status="COMPLETED")
    model_run_id = _insert_model_run(
        database_path,
        analysis_run_id=analysis_run_id,
        status="COMPLETED",
        model_name="Artifact drift model",
        selected_candidate="BAGGING_PU",
        metrics=_v2_metrics("BAGGING_PU", challenger_status="FITTED"),
        created_at="2026-08-21T03:30:00Z",
    )

    artifact_path = tmp_path / "artifacts" / "models" / "model_run_000123" / "pu_model.joblib"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"checksum-mismatch-fixture")

    detail = client.get(f"/api/models/{model_run_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["artifact"]["verified"] is False
    assert payload["artifact"]["verification_message"] == (
        "The model artifact could not be verified."
    )


def test_training_options_return_completed_analyses_defaults_governance_and_active_job(
    client: TestClient,
    database_path: Path,
) -> None:
    completed_id = _insert_analysis_run(database_path, status="COMPLETED")
    _insert_analysis_run(database_path, status="FAILED")
    repository = model_job_service_module.JobRepository(database_path)
    repository.create_training_job(
        created_at="2026-08-21T04:00:00Z",
        request_payload={"analysis_run_id": completed_id},
    )

    options = client.get("/api/models/training-options")

    assert options.status_code == 200
    payload = options.json()
    assert len(payload["completed_analyses"]) == 1
    assert payload["completed_analyses"][0]["analysis_run_id"] == completed_id
    assert payload["defaults"] == {
        "random_seed": 42,
        "validation_fraction": 0.2,
        "run_elkan_challenger": True,
        "model_name": None,
    }
    assert payload["governance"]["model_role_policy_version"] == "2"
    assert payload["governance"]["evaluation_contract_version"] == "2"
    assert payload["active_job"]["status"] == "QUEUED"