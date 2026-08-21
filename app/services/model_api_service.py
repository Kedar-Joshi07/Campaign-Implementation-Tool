"""Public-safe composition service for Phase 4 model and job APIs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.ml.evaluation import EVALUATION_CONTRACT_VERSION
from app.ml.model_roles import (
    CHALLENGER_1_MODEL_NAME,
    DIAGNOSTIC_CONTROL_NAME,
    MODEL_ROLE_POLICY_VERSION,
    PRIMARY_MODEL_NAME,
    PRIMARY_ROLE_GOVERNED_SELECTION,
)
from app.repositories.job_repository import JobRepository
from app.repositories.model_run_repository import ModelRunRepository
from app.services.historical_analysis_service import list_historical_analysis_runs
from app.services.model_job_service import (
    ACTIVE_JOB_CONFLICT_MESSAGE,
    ANALYSIS_NOT_AVAILABLE_MESSAGE,
    ModelJobConflictError,
    ModelJobSubmissionError,
    ModelJobValidationError,
    STALE_JOB_INTERRUPTION_MESSAGE,
    submit_model_training_job_request,
)
from app.services.model_training_service import load_verified_model_artifact


MODEL_TRAINING_FAILED_MESSAGE = "Model training could not be completed."
ARTIFACT_VERIFICATION_FAILED_MESSAGE = "The model artifact could not be verified."
JOB_NOT_FOUND_MESSAGE = "The requested job was not found."
MODEL_RUN_NOT_FOUND_MESSAGE = "The requested model run was not found."


class ModelApiError(RuntimeError):
    """Base class for model API service failures."""


class ModelApiValidationError(ModelApiError):
    """Raised when a request cannot be served because input is invalid."""


class ModelApiConflictError(ModelApiError):
    """Raised when a request conflicts with persisted state."""


class ModelApiNotFoundError(ModelApiError):
    """Raised when the requested model/job resource is missing."""


def _decode_json_object(raw: Any, *, field_name: str) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, str):
        raise ModelApiValidationError(f"{field_name} metadata is invalid.")
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ModelApiValidationError(f"{field_name} metadata is invalid.") from exc
    if not isinstance(decoded, dict):
        raise ModelApiValidationError(f"{field_name} metadata is invalid.")
    return decoded


def _public_job_failure_message(row: dict[str, Any]) -> str | None:
    if row["status"] != "FAILED":
        return None
    raw_error = row.get("error_message")
    if not raw_error:
        return MODEL_TRAINING_FAILED_MESSAGE
    if isinstance(raw_error, str) and STALE_JOB_INTERRUPTION_MESSAGE in raw_error:
        return STALE_JOB_INTERRUPTION_MESSAGE
    return MODEL_TRAINING_FAILED_MESSAGE


def _public_job_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": int(row["job_id"]),
        "job_type": str(row["job_type"]),
        "status": str(row["status"]),
        "progress_percent": int(row["progress_percent"]),
        "stage": str(row["stage"]),
        "message": row.get("message"),
        "analysis_run_id": row.get("analysis_run_id"),
        "model_run_id": row.get("model_run_id"),
        "created_at": row["created_at"],
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
    }


def submit_training_request(
    database_path: str | Path,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        job = submit_model_training_job_request(database_path, request_payload)
    except ModelJobConflictError as exc:
        raise ModelApiConflictError(ACTIVE_JOB_CONFLICT_MESSAGE) from exc
    except ModelJobValidationError as exc:
        message = str(exc)
        if message == ANALYSIS_NOT_AVAILABLE_MESSAGE:
            raise ModelApiConflictError(message) from exc
        raise ModelApiValidationError(message) from exc
    except ModelJobSubmissionError as exc:
        raise ModelApiConflictError(str(exc)) from exc
    return _public_job_summary(job)


def get_job_detail(database_path: str | Path, job_id: int) -> dict[str, Any]:
    row = JobRepository(database_path).fetch_job(job_id)
    if row is None:
        raise ModelApiNotFoundError(JOB_NOT_FOUND_MESSAGE)
    result_payload: dict[str, Any] | None = None
    if row.get("result_json"):
        result_payload = _decode_json_object(row["result_json"], field_name="result_json")
    return {
        **_public_job_summary(row),
        "result": result_payload,
        "failure_message": _public_job_failure_message(row),
    }


def list_model_summaries(
    database_path: str | Path,
    *,
    limit: int,
    offset: int,
    status: str | None,
) -> list[dict[str, Any]]:
    rows = ModelRunRepository(database_path).list_runs(
        limit=limit,
        offset=offset,
        status=status,
    )
    summaries: list[dict[str, Any]] = []
    for row in rows:
        metrics = _decode_json_object(row.get("metrics_json"), field_name="metrics_json")
        selected_candidate = row.get("selected_candidate")
        selection_policy = metrics.get("selection_policy") if metrics else None
        model_role_policy_version = metrics.get("model_role_policy_version") if metrics else None
        validation_lift_at_10_percent = None
        if selected_candidate and selected_candidate in metrics.get("candidate_results", {}):
            selected_metrics = metrics["candidate_results"][selected_candidate]
            validation_lift_at_10_percent = (
                selected_metrics.get("top_slice_metrics", {})
                .get("top_10_percent", {})
                .get("known_positive_lift_at_k")
            )
        summaries.append(
            {
                "model_run_id": int(row["model_run_id"]),
                "analysis_run_id": int(row["analysis_run_id"]),
                "model_name": row["model_name"],
                "created_at": row["created_at"],
                "completed_at": row.get("completed_at"),
                "status": row["status"],
                "selected_candidate": selected_candidate,
                "selection_policy": selection_policy,
                "model_role_policy_version": model_role_policy_version,
                "validation_lift_at_10_percent": validation_lift_at_10_percent,
            }
        )
    return summaries


def _artifact_section(database_path: str | Path, row: dict[str, Any]) -> dict[str, Any]:
    artifact_path = row.get("artifact_path")
    artifact_file = None
    if isinstance(artifact_path, str) and artifact_path.strip():
        artifact_file = Path(artifact_path).name
    verified = False
    verification_message = None
    if row["status"] == "COMPLETED":
        try:
            load_verified_model_artifact(database_path, int(row["model_run_id"]))
            verified = True
        except Exception:
            verification_message = ARTIFACT_VERIFICATION_FAILED_MESSAGE
    return {
        "sha256": row.get("artifact_sha256"),
        "artifact_file": artifact_file,
        "verified": verified,
        "verification_message": verification_message,
    }


def _governance_section(metrics: dict[str, Any]) -> dict[str, Any]:
    role_policy_version = metrics.get("model_role_policy_version")
    evaluation_contract_version = metrics.get("evaluation_contract_version")
    is_legacy = role_policy_version is None
    return {
        "is_legacy": is_legacy,
        "model_role_policy_version": role_policy_version,
        "evaluation_contract_version": evaluation_contract_version,
        "primary_candidate": metrics.get("primary_candidate"),
        "challenger_candidates": metrics.get("challenger_candidates", []),
        "diagnostic_controls": metrics.get("diagnostic_controls", []),
        "selection_policy": metrics.get("selection_policy"),
        "selected_candidate": metrics.get("selected_candidate"),
    }


def get_model_run_detail(database_path: str | Path, model_run_id: int) -> dict[str, Any]:
    row = ModelRunRepository(database_path).fetch_run(model_run_id)
    if row is None:
        raise ModelApiNotFoundError(MODEL_RUN_NOT_FOUND_MESSAGE)

    feature_contract = _decode_json_object(
        row.get("feature_contract_json"),
        field_name="feature_contract_json",
    )
    metrics = _decode_json_object(row.get("metrics_json"), field_name="metrics_json")
    governance = _governance_section(metrics)

    return {
        "identity": {
            "model_run_id": int(row["model_run_id"]),
            "analysis_run_id": int(row["analysis_run_id"]),
            "model_name": row["model_name"],
            "created_at": row["created_at"],
            "completed_at": row.get("completed_at"),
            "status": row["status"],
        },
        "cohort": {
            "reconstructed_observation_count": int(row["reconstructed_observation_count"]),
            "selected_customer_count": int(row["selected_customer_count"]),
            "positive_customer_count": int(row["positive_customer_count"]),
            "unlabeled_customer_count": int(row["unlabeled_customer_count"]),
            "train_customer_count": int(row["train_customer_count"]),
            "validation_customer_count": int(row["validation_customer_count"]),
            "train_positive_count": int(row["train_positive_count"]),
            "validation_positive_count": int(row["validation_positive_count"]),
        },
        "governance": governance,
        "candidates": metrics.get("candidate_results", {}),
        "challenger_comparison": metrics.get("challenger_comparison", {}),
        "quality_flags": list(metrics.get("quality_flags", [])),
        "artifact": _artifact_section(database_path, row),
        "feature_contract": {
            "feature_contract_version": feature_contract.get("feature_contract_version"),
            "feature_contract_sha256": feature_contract.get("feature_contract_sha256"),
            "ordered_features": feature_contract.get("ordered_features", []),
        },
        "runtime": {
            "random_seed": row.get("random_seed"),
            "validation_fraction": row.get("validation_fraction"),
        },
    }


def get_model_training_options(database_path: str | Path) -> dict[str, Any]:
    analyses = list_historical_analysis_runs(database_path, limit=100, offset=0)
    completed = [item for item in analyses if item["status"] == "COMPLETED"]
    active_job = JobRepository(database_path).find_active_training_job()

    return {
        "completed_analyses": [
            {
                "analysis_run_id": int(item["analysis_run_id"]),
                "analysis_name": item["analysis_name"],
                "completed_at": item["completed_at"],
                "conversion_definition": item["conversion_definition"],
                "selected_customer_count": int(item["selected_customer_count"]),
                "positive_customer_count": int(item["positive_customer_count"]),
                "unlabeled_customer_count": int(item["unlabeled_customer_count"]),
            }
            for item in completed
        ],
        "defaults": {
            "random_seed": 42,
            "validation_fraction": 0.2,
            "run_elkan_challenger": True,
            "model_name": None,
        },
        "governance": {
            "model_role_policy_version": MODEL_ROLE_POLICY_VERSION,
            "evaluation_contract_version": EVALUATION_CONTRACT_VERSION,
            "primary_candidate": PRIMARY_MODEL_NAME,
            "challenger_candidates": [CHALLENGER_1_MODEL_NAME],
            "diagnostic_controls": [DIAGNOSTIC_CONTROL_NAME],
            "selection_policy": PRIMARY_ROLE_GOVERNED_SELECTION,
        },
        "active_job": _public_job_summary(active_job) if active_job is not None else None,
    }


__all__ = (
    "ARTIFACT_VERIFICATION_FAILED_MESSAGE",
    "JOB_NOT_FOUND_MESSAGE",
    "MODEL_RUN_NOT_FOUND_MESSAGE",
    "MODEL_TRAINING_FAILED_MESSAGE",
    "ModelApiConflictError",
    "ModelApiError",
    "ModelApiNotFoundError",
    "ModelApiValidationError",
    "get_job_detail",
    "get_model_run_detail",
    "get_model_training_options",
    "list_model_summaries",
    "submit_training_request",
)