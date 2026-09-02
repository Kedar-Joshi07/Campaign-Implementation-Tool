"""Public-safe composition service for Phase 4 model and job APIs."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from app.database.connection import get_connection
from app.ml.evaluation import EVALUATION_CONTRACT_VERSION
from app.ml.feature_contract import (
    FEATURE_CONTRACT,
    FEATURE_CONTRACT_SHA256,
    FEATURE_CONTRACT_VERSION,
    ORDERED_FEATURES,
)
from app.ml.model_roles import (
    CHALLENGER_1_MODEL_NAME,
    DIAGNOSTIC_CONTROL_NAME,
    MODEL_ROLE_POLICY_VERSION,
    PRIMARY_MODEL_NAME,
    PRIMARY_ROLE_GOVERNED_SELECTION,
)
from app.repositories.job_repository import JobRepository
from app.repositories.model_run_repository import ModelRunRepository
from app.repositories.scoring_repository import ScoringRepository
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
from app.services.model_scoring_compatibility import ModelScoreabilityValidationError
from app.services.model_scoring_compatibility import validate_scoreable_model
from app.services.scoring_job_service import (
    ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE,
    EXISTING_SCORING_RUN_CONFLICT_MESSAGE,
    MODEL_NOT_SCOREABLE_MESSAGE,
    ScoringJobConflictError,
    ScoringJobSubmissionError,
    ScoringJobValidationError,
    submit_prospect_scoring_job_request,
)
from app.services.audience_preparation_service import (
    SCORING_RUN_NOT_FOUND_MESSAGE as AUDIENCE_SCORING_RUN_NOT_FOUND_MESSAGE,
    AudiencePreparationConflictError,
    AudiencePreparationSubmissionError,
    AudiencePreparationValidationError,
    get_audience_preparation_status,
    list_audience_preparation_runs,
    submit_audience_preparation_job_request,
)
from app.services.audience_query_service import (
    AudienceQueryConflictError,
    AudienceQueryValidationError,
    estimate_audience,
    get_audience_filter_options,
    profile_audience,
    search_audience,
)
from app.services.saved_audience_service import (
    SavedAudienceServiceConflictError,
    SavedAudienceServiceNotFoundError,
    SavedAudienceServiceValidationError,
    get_saved_audience_detail,
    list_saved_audiences,
    save_audience,
    validate_saved_audience_currentness,
)
from app.services.model_training_service import load_verified_model_artifact
from app.services.prospect_scoring_service import (
    ProspectScoringVerificationError,
    validate_completed_scoring_run_provenance_lightweight,
)


MODEL_TRAINING_FAILED_MESSAGE = "Model training could not be completed."
MODEL_SCORING_FAILED_MESSAGE = "Prospect scoring could not be completed."
ARTIFACT_VERIFICATION_FAILED_MESSAGE = "The model artifact could not be verified."
JOB_NOT_FOUND_MESSAGE = "The requested job was not found."
MODEL_RUN_NOT_FOUND_MESSAGE = "The requested model run was not found."
SCORING_RUN_NOT_FOUND_MESSAGE = "The requested scoring run was not found."
SAVED_AUDIENCE_NOT_FOUND_MESSAGE = "The requested saved audience was not found."

_FORBIDDEN_PUBLIC_PAYLOAD_KEYS = {
    "customer_id",
    "customer_ids",
    "person_id",
    "person_ids",
    "first_name",
    "last_name",
    "city",
    "email",
    "phone_number",
    "address_line_1",
    "address_line_2",
    "street",
    "postal_code",
    "ethnicity",
    "religion",
    "occupation_industry",
    "family_yearly_income",
    "number_of_children_in_family",
    "number_of_adults_in_family",
    "train_matrix",
    "validation_matrix",
    "validation_scores",
    "raw_features",
    "propensity_scores",
    "score_rows",
    "sql",
    "query",
    "absolute_path",
    "traceback",
}


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
    if _contains_non_finite_numbers(decoded):
        raise ModelApiValidationError(f"{field_name} metadata is invalid.")
    return decoded


def _contains_non_finite_numbers(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_non_finite_numbers(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_non_finite_numbers(item) for item in value)
    if isinstance(value, float):
        return not math.isfinite(value)
    return False


def _contains_forbidden_public_content(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if isinstance(key, str) and key.casefold() in _FORBIDDEN_PUBLIC_PAYLOAD_KEYS:
                return True
            if _contains_forbidden_public_content(nested):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_forbidden_public_content(item) for item in value)
    if isinstance(value, str):
        normalized = value.casefold().strip()
        if "traceback" in normalized:
            return True
        if "select " in normalized or "insert " in normalized or "update " in normalized:
            return True
        if "delete " in normalized or " from " in normalized:
            return True
        if "sqlite" in normalized and ("\\" in normalized or "/" in normalized):
            return True
        if normalized.startswith(("/", "\\\\")):
            return True
        if (
            len(normalized) >= 3
            and normalized[1] == ":"
            and normalized[2] in {"/", "\\"}
            and normalized[0].isalpha()
        ):
            return True
        return False
    return False


def _decode_public_json_object(raw: Any, *, field_name: str) -> dict[str, Any]:
    decoded = _decode_json_object(raw, field_name=field_name)
    if _contains_forbidden_public_content(decoded):
        raise ModelApiValidationError(f"{field_name} metadata is invalid.")
    return decoded


def _validated_feature_contract_section(feature_contract: dict[str, Any]) -> dict[str, Any]:
    if feature_contract != FEATURE_CONTRACT:
        raise ModelApiValidationError("feature_contract metadata is invalid.")

    version = feature_contract.get("version")
    ordered_features = feature_contract.get("ordered_features")
    if version != FEATURE_CONTRACT_VERSION or ordered_features != list(ORDERED_FEATURES):
        raise ModelApiValidationError("feature_contract metadata is invalid.")

    return {
        "feature_contract_version": version,
        "feature_contract_sha256": FEATURE_CONTRACT_SHA256,
        "ordered_features": list(ordered_features),
    }


def _public_job_failure_message(row: dict[str, Any]) -> str | None:
    if row["status"] != "FAILED":
        return None
    raw_error = row.get("error_message")
    if row.get("job_type") == "PROSPECT_SCORING":
        if isinstance(raw_error, str) and "interrupted by application restart" in raw_error:
            return "Prospect scoring was interrupted by application restart."
        return MODEL_SCORING_FAILED_MESSAGE
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
        raise ModelApiError(MODEL_TRAINING_FAILED_MESSAGE) from exc
    return _public_job_summary(job)


def submit_scoring_request(
    database_path: str | Path,
    model_run_id: int,
) -> dict[str, Any]:
    if ModelRunRepository(database_path).fetch_run(model_run_id) is None:
        raise ModelApiNotFoundError(MODEL_RUN_NOT_FOUND_MESSAGE)

    try:
        job = submit_prospect_scoring_job_request(
            database_path,
            {"model_run_id": model_run_id},
        )
    except ScoringJobConflictError as exc:
        raise ModelApiConflictError(str(exc)) from exc
    except ScoringJobValidationError as exc:
        message = str(exc)
        if message in {
            MODEL_NOT_SCOREABLE_MESSAGE,
            EXISTING_SCORING_RUN_CONFLICT_MESSAGE,
            ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE,
        }:
            raise ModelApiConflictError(message) from exc
        raise ModelApiValidationError(message) from exc
    except ScoringJobSubmissionError as exc:
        raise ModelApiError(MODEL_SCORING_FAILED_MESSAGE) from exc

    return _public_job_summary(job)


def submit_audience_preparation_request(
    database_path: str | Path,
    scoring_run_id: int,
    rank_contract_version: str,
) -> dict[str, Any]:
    try:
        job = submit_audience_preparation_job_request(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "rank_contract_version": rank_contract_version,
            },
        )
    except AudiencePreparationConflictError as exc:
        raise ModelApiConflictError(str(exc)) from exc
    except AudiencePreparationValidationError as exc:
        message = str(exc)
        if message == AUDIENCE_SCORING_RUN_NOT_FOUND_MESSAGE:
            raise ModelApiNotFoundError(SCORING_RUN_NOT_FOUND_MESSAGE) from exc
        raise ModelApiValidationError(message) from exc
    except AudiencePreparationSubmissionError as exc:
        raise ModelApiError("Audience preparation could not be completed.") from exc

    return job


def get_audience_options(
    database_path: str | Path,
    *,
    scoring_run_id: int,
) -> dict[str, Any]:
    try:
        return get_audience_filter_options(
            database_path,
            scoring_run_id=scoring_run_id,
        )
    except AudienceQueryConflictError as exc:
        message = str(exc)
        if message == SCORING_RUN_NOT_FOUND_MESSAGE:
            raise ModelApiNotFoundError(message) from exc
        raise ModelApiConflictError(message) from exc
    except AudienceQueryValidationError as exc:
        message = str(exc)
        if message == SCORING_RUN_NOT_FOUND_MESSAGE:
            raise ModelApiNotFoundError(message) from exc
        raise ModelApiValidationError(message) from exc


def estimate_audience_population(
    database_path: str | Path,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        return estimate_audience(database_path, request_payload)
    except AudienceQueryConflictError as exc:
        message = str(exc)
        if message == SCORING_RUN_NOT_FOUND_MESSAGE:
            raise ModelApiNotFoundError(message) from exc
        raise ModelApiConflictError(message) from exc
    except AudienceQueryValidationError as exc:
        message = str(exc)
        if message == SCORING_RUN_NOT_FOUND_MESSAGE:
            raise ModelApiNotFoundError(message) from exc
        raise ModelApiValidationError(message) from exc


def search_audience_rows(
    database_path: str | Path,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        return search_audience(database_path, request_payload)
    except AudienceQueryConflictError as exc:
        message = str(exc)
        if message == SCORING_RUN_NOT_FOUND_MESSAGE:
            raise ModelApiNotFoundError(message) from exc
        raise ModelApiConflictError(message) from exc
    except AudienceQueryValidationError as exc:
        message = str(exc)
        if message == SCORING_RUN_NOT_FOUND_MESSAGE:
            raise ModelApiNotFoundError(message) from exc
        raise ModelApiValidationError(message) from exc


def profile_audience_population(
    database_path: str | Path,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        return profile_audience(database_path, request_payload)
    except AudienceQueryConflictError as exc:
        message = str(exc)
        if message == SCORING_RUN_NOT_FOUND_MESSAGE:
            raise ModelApiNotFoundError(message) from exc
        raise ModelApiConflictError(message) from exc
    except AudienceQueryValidationError as exc:
        message = str(exc)
        if message == SCORING_RUN_NOT_FOUND_MESSAGE:
            raise ModelApiNotFoundError(message) from exc
        raise ModelApiValidationError(message) from exc


def create_saved_audience(
    database_path: str | Path,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        return save_audience(database_path, request_payload)
    except SavedAudienceServiceConflictError as exc:
        raise ModelApiConflictError(str(exc)) from exc
    except SavedAudienceServiceNotFoundError as exc:
        raise ModelApiNotFoundError(str(exc)) from exc
    except SavedAudienceServiceValidationError as exc:
        message = str(exc)
        if message == SCORING_RUN_NOT_FOUND_MESSAGE:
            raise ModelApiNotFoundError(message) from exc
        raise ModelApiValidationError(message) from exc


def list_saved_audience_summaries(
    database_path: str | Path,
    *,
    limit: int,
    offset: int,
    scoring_run_id: int | None,
    model_run_id: int | None,
) -> list[dict[str, Any]]:
    try:
        return list_saved_audiences(
            database_path,
            limit=limit,
            offset=offset,
            scoring_run_id=scoring_run_id,
            model_run_id=model_run_id,
        )
    except SavedAudienceServiceValidationError as exc:
        raise ModelApiValidationError(str(exc)) from exc


def get_saved_audience(
    database_path: str | Path,
    *,
    audience_id: int,
) -> dict[str, Any]:
    try:
        return get_saved_audience_detail(database_path, audience_id=audience_id)
    except SavedAudienceServiceNotFoundError as exc:
        raise ModelApiNotFoundError(str(exc)) from exc
    except SavedAudienceServiceValidationError as exc:
        raise ModelApiValidationError(str(exc)) from exc


def get_saved_audience_currentness(
    database_path: str | Path,
    *,
    audience_id: int,
) -> dict[str, Any]:
    try:
        return validate_saved_audience_currentness(database_path, audience_id=audience_id)
    except SavedAudienceServiceNotFoundError as exc:
        raise ModelApiNotFoundError(str(exc)) from exc
    except SavedAudienceServiceValidationError as exc:
        raise ModelApiValidationError(str(exc)) from exc


def get_job_detail(database_path: str | Path, job_id: int) -> dict[str, Any]:
    row = JobRepository(database_path).fetch_job(job_id)
    if row is None:
        raise ModelApiNotFoundError(JOB_NOT_FOUND_MESSAGE)
    result_payload: dict[str, Any] | None = None
    if row.get("result_json"):
        result_payload = _decode_public_json_object(
            row["result_json"],
            field_name="result_json",
        )
    return {
        **_public_job_summary(row),
        "result": result_payload,
        "failure_message": _public_job_failure_message(row),
    }


def _public_completed_scoring_reference(
    row: dict[str, Any] | None,
    *,
    demographic_source_verified: bool | None = None,
) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = {
        "scoring_run_id": int(row["scoring_run_id"]),
        "status": str(row["status"]),
        "completed_at": row.get("completed_at"),
        "scored_person_count": int(row["scored_person_count"]),
        "score_min": float(row["score_min"]),
        "score_max": float(row["score_max"]),
        "score_mean": float(row["score_mean"]),
    }
    if demographic_source_verified is not None:
        payload["demographic_source_verified"] = bool(demographic_source_verified)
    return payload


def _latest_demographic_count_from_import_metadata(database_path: str | Path) -> int:
    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT rows_inserted
            FROM data_import_runs
            WHERE dataset_name = 'demographics' AND status = 'COMPLETED'
            ORDER BY import_id DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return 0

    rows_inserted = row["rows_inserted"]
    if isinstance(rows_inserted, bool) or not isinstance(rows_inserted, int) or rows_inserted < 0:
        return 0
    return int(rows_inserted)


def _select_completed_scoring_reference_for_status(
    database_path: str | Path,
    *,
    model_run_id: int,
    limit: int = 100,
) -> tuple[dict[str, Any] | None, bool | None, bool]:
    scoring_repository = ScoringRepository(database_path)
    completed_runs = scoring_repository.find_completed_runs_for_model(model_run_id, limit=limit)
    if not completed_runs:
        return None, None, False

    latest_row = completed_runs[0]
    latest_source_verified: bool | None = None
    shared_cache: dict[str, Any] = {}

    for index, row in enumerate(completed_runs):
        try:
            provenance = validate_completed_scoring_run_provenance_lightweight(
                database_path,
                scoring_run_id=int(row["scoring_run_id"]),
                verify_current_source_match=True,
                cache=shared_cache,
            )
        except ProspectScoringVerificationError:
            source_verified = False
            historical_verified = False
        else:
            source_verified = bool(provenance["demographic_source_verified"])
            historical_verified = bool(provenance["historical_source_verified"])

        if index == 0:
            latest_source_verified = source_verified

        if source_verified and historical_verified:
            return row, source_verified, True

    return latest_row, latest_source_verified, False


def get_scoring_status(database_path: str | Path, model_run_id: int) -> dict[str, Any]:
    model_row = ModelRunRepository(database_path).fetch_run(model_run_id)
    if model_row is None:
        raise ModelApiNotFoundError(MODEL_RUN_NOT_FOUND_MESSAGE)

    completed_scoring_run, completed_scoring_run_source_verified, completed_scoring_run_canonical = (
        _select_completed_scoring_reference_for_status(
            database_path,
            model_run_id=model_run_id,
        )
    )

    demographic_count = _latest_demographic_count_from_import_metadata(database_path)
    if demographic_count < 1 and completed_scoring_run is not None:
        demographic_count = int(completed_scoring_run["demographic_snapshot_count"])
    active_job = JobRepository(database_path).find_active_compute_job()

    eligible = True
    reason: str | None = None
    artifact_feature_compatible = True
    historical_source_verified = False
    feature_contract_version: str | None = None
    feature_contract_sha256: str | None = None
    artifact_sha256: str | None = None
    selected_candidate = model_row.get("selected_candidate")

    try:
        compatibility = validate_scoreable_model(database_path, model_run_id)
        selected_candidate = compatibility.selected_candidate
        feature_contract_version = compatibility.feature_contract_version
        feature_contract_sha256 = compatibility.feature_contract_sha256
        artifact_sha256 = compatibility.artifact_sha256
        historical_source_verified = True
    except ModelScoreabilityValidationError as exc:
        artifact_feature_compatible = False
        eligible = False
        reason = str(exc)

    if completed_scoring_run_canonical:
        eligible = False
        reason = EXISTING_SCORING_RUN_CONFLICT_MESSAGE
    elif active_job is not None:
        eligible = False
        reason = ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE

    return {
        "model_run_id": int(model_run_id),
        "eligible": eligible,
        "reason": reason,
        "demographic_source_verified": bool(completed_scoring_run_source_verified),
        "historical_source_verified": bool(historical_source_verified),
        "demographic_count": int(demographic_count),
        "selected_candidate": selected_candidate,
        "artifact_feature_compatible": artifact_feature_compatible,
        "feature_contract_version": feature_contract_version,
        "feature_contract_sha256": feature_contract_sha256,
        "artifact_sha256": artifact_sha256,
        "active_job": _public_job_summary(active_job) if active_job is not None else None,
        "completed_scoring_run": _public_completed_scoring_reference(
            completed_scoring_run,
            demographic_source_verified=completed_scoring_run_source_verified,
        ),
    }


def _public_scoring_run_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "scoring_run_id": int(row["scoring_run_id"]),
        "job_id": int(row["job_id"]),
        "model_run_id": int(row["model_run_id"]),
        "status": str(row["status"]),
        "created_at": row["created_at"],
        "completed_at": row.get("completed_at"),
        "demographic_snapshot_count": int(row["demographic_snapshot_count"]),
        "scored_person_count": int(row["scored_person_count"]),
        "chunk_size": int(row["chunk_size"]),
        "selected_candidate": str(row["selected_candidate"]),
        "score_min": float(row["score_min"]) if row.get("score_min") is not None else None,
        "score_max": float(row["score_max"]) if row.get("score_max") is not None else None,
        "score_mean": float(row["score_mean"]) if row.get("score_mean") is not None else None,
    }


def list_scoring_run_summaries(
    database_path: str | Path,
    *,
    limit: int,
    offset: int,
    status: str | None,
    model_run_id: int | None,
) -> list[dict[str, Any]]:
    rows = ScoringRepository(database_path).list_scoring_runs(
        limit=limit,
        offset=offset,
        status=status,
        model_run_id=model_run_id,
    )
    return [_public_scoring_run_summary(row) for row in rows]


def get_scoring_run_detail(database_path: str | Path, scoring_run_id: int) -> dict[str, Any]:
    row = ScoringRepository(database_path).fetch_scoring_run(scoring_run_id)
    if row is None:
        raise ModelApiNotFoundError(SCORING_RUN_NOT_FOUND_MESSAGE)

    try:
        provenance_check = validate_completed_scoring_run_provenance_lightweight(
            database_path,
            scoring_run_id=int(row["scoring_run_id"]),
            verify_current_source_match=True,
            cache={},
        )
        demographic_source_verified = bool(provenance_check["demographic_source_verified"])
    except ProspectScoringVerificationError:
        demographic_source_verified = False

    score_summary_payload: dict[str, Any] | None = None
    if row.get("score_summary_json"):
        score_summary_payload = _decode_public_json_object(
            row["score_summary_json"],
            field_name="score_summary_json",
        )

    job_row = JobRepository(database_path).fetch_job(int(row["job_id"]))
    return {
        "identity": {
            "scoring_run_id": int(row["scoring_run_id"]),
            "job_id": int(row["job_id"]),
            "model_run_id": int(row["model_run_id"]),
            "status": str(row["status"]),
            "created_at": row["created_at"],
            "completed_at": row.get("completed_at"),
            "failure_message": (
                MODEL_SCORING_FAILED_MESSAGE if row["status"] == "FAILED" else None
            ),
        },
        "population": {
            "demographic_snapshot_count": int(row["demographic_snapshot_count"]),
            "scored_person_count": int(row["scored_person_count"]),
            "chunk_size": int(row["chunk_size"]),
        },
        "model_contract": {
            "selected_candidate": str(row["selected_candidate"]),
            "model_role_policy_version": str(row["model_role_policy_version"]),
            "feature_contract_version": str(row["feature_contract_version"]),
            "feature_contract_sha256": str(row["feature_contract_sha256"]),
            "artifact_sha256": str(row["artifact_sha256"]),
        },
        "score_summary": {
            "score_min": float(row["score_min"]) if row.get("score_min") is not None else None,
            "score_max": float(row["score_max"]) if row.get("score_max") is not None else None,
            "score_mean": float(row["score_mean"]) if row.get("score_mean") is not None else None,
            "summary_payload": score_summary_payload,
            "demographic_source_verified": demographic_source_verified,
        },
        "job": _public_job_summary(job_row) if job_row is not None else None,
    }


def get_audience_run_preparation_status(
    database_path: str | Path,
    *,
    scoring_run_id: int,
    rank_contract_version: str,
) -> dict[str, Any]:
    try:
        payload = get_audience_preparation_status(
            database_path,
            scoring_run_id=scoring_run_id,
            rank_contract_version=rank_contract_version,
        )
    except AudiencePreparationConflictError as exc:
        raise ModelApiConflictError(str(exc)) from exc
    except AudiencePreparationValidationError as exc:
        message = str(exc)
        if message == AUDIENCE_SCORING_RUN_NOT_FOUND_MESSAGE:
            raise ModelApiNotFoundError(SCORING_RUN_NOT_FOUND_MESSAGE) from exc
        raise ModelApiValidationError(message) from exc

    active_job = payload.get("active_job")
    return {
        "scoring_run_id": int(payload["scoring_run_id"]),
        "model_run_id": int(payload["model_run_id"]),
        "status": str(payload["status"]),
        "rank_contract_version": str(payload["rank_contract_version"]),
        "analytics_contract_version": str(payload["analytics_contract_version"]),
        "prepared": bool(payload["prepared"]),
        "analytics_prepared": bool(payload.get("analytics_prepared", False)),
        "is_canonical": bool(payload["is_canonical"]),
        "source_verified": bool(payload["source_verified"]),
        "ready_for_current_audience_actions": bool(payload["ready_for_current_audience_actions"]),
        "currentness_issues": [str(item) for item in payload.get("currentness_issues", [])],
        "boundary_count": int(payload["boundary_count"]),
        "total_population": int(payload["total_population"]),
        "analytics_snapshot_created_at": payload.get("analytics_snapshot_created_at"),
        "active_job": _public_job_summary(active_job) if active_job is not None else None,
    }


def list_audience_run_preparation_summaries(
    database_path: str | Path,
    *,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    try:
        rows = list_audience_preparation_runs(
            database_path,
            limit=limit,
            offset=offset,
        )
    except AudiencePreparationValidationError as exc:
        raise ModelApiValidationError(str(exc)) from exc

    return [
        {
            "scoring_run_id": int(row["scoring_run_id"]),
            "model_run_id": int(row["model_run_id"]),
            "completed_at": row.get("completed_at"),
            "scored_person_count": int(row["scored_person_count"]),
            "prepared": bool(row["prepared"]),
            "analytics_prepared": bool(row.get("analytics_prepared", False)),
            "analytics_contract_version": row.get("analytics_contract_version"),
            "is_canonical": bool(row["is_canonical"]),
            "source_verified": bool(row["source_verified"]),
            "ready_for_current_audience_actions": bool(row["ready_for_current_audience_actions"]),
            "currentness_issues": [str(item) for item in row.get("currentness_issues", [])],
            "rank_contract_version": row.get("rank_contract_version"),
            "boundary_count": int(row["boundary_count"]),
            "analytics_snapshot_created_at": row.get("analytics_snapshot_created_at"),
        }
        for row in rows
    ]


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
        "feature_contract": _validated_feature_contract_section(feature_contract),
        "runtime": {
            "random_seed": row.get("random_seed"),
            "validation_fraction": row.get("validation_fraction"),
        },
    }


def get_model_training_options(database_path: str | Path) -> dict[str, Any]:
    analyses = list_historical_analysis_runs(database_path, limit=100, offset=0)
    completed = [item for item in analyses if item["status"] == "COMPLETED"]
    active_job = JobRepository(database_path).find_active_compute_job()

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
                "is_current": bool(item.get("is_current", False)),
                "trainability_status": (
                    "CURRENT" if bool(item.get("is_current", False)) else "STALE"
                ),
                "trainability_reason": item.get("trainability_reason"),
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
    "MODEL_SCORING_FAILED_MESSAGE",
    "MODEL_RUN_NOT_FOUND_MESSAGE",
    "MODEL_TRAINING_FAILED_MESSAGE",
    "SAVED_AUDIENCE_NOT_FOUND_MESSAGE",
        "create_saved_audience",
        "get_saved_audience",
        "get_saved_audience_currentness",
    "SCORING_RUN_NOT_FOUND_MESSAGE",
    "ModelApiConflictError",
    "ModelApiError",
    "ModelApiNotFoundError",
    "ModelApiValidationError",
    "get_audience_run_preparation_status",
    "get_scoring_run_detail",
    "get_scoring_status",
    "get_job_detail",
    "get_model_run_detail",
    "get_model_training_options",
    "list_audience_run_preparation_summaries",
    "list_saved_audience_summaries",
    "list_scoring_run_summaries",
    "list_model_summaries",
    "submit_audience_preparation_request",
    "submit_scoring_request",
    "submit_training_request",
)