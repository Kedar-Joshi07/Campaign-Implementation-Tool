"""Persistent job lifecycle repository for Phase 4 model-training orchestration."""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from app.database.connection import get_connection


JOB_TYPE_MODEL_TRAINING = "MODEL_TRAINING"

JOB_STATUS_QUEUED = "QUEUED"
JOB_STATUS_RUNNING = "RUNNING"
JOB_STATUS_COMPLETED = "COMPLETED"
JOB_STATUS_FAILED = "FAILED"

JOB_STAGE_QUEUED = "QUEUED"
JOB_STAGE_STARTING = "STARTING"
JOB_STAGE_RECONSTRUCTING_COHORT = "RECONSTRUCTING_COHORT"
JOB_STAGE_SPLITTING_DATA = "SPLITTING_DATA"
JOB_STAGE_PREPROCESSING = "PREPROCESSING"
JOB_STAGE_TRAINING_PRIMARY = "TRAINING_PRIMARY"
JOB_STAGE_TRAINING_CHALLENGER = "TRAINING_CHALLENGER"
JOB_STAGE_TRAINING_DIAGNOSTIC = "TRAINING_DIAGNOSTIC"
JOB_STAGE_EVALUATING = "EVALUATING"
JOB_STAGE_PERSISTING_ARTIFACT = "PERSISTING_ARTIFACT"
JOB_STAGE_VERIFYING_ARTIFACT = "VERIFYING_ARTIFACT"
JOB_STAGE_COMPLETED = "COMPLETED"
JOB_STAGE_FAILED = "FAILED"

ALL_JOB_STAGES = (
    JOB_STAGE_QUEUED,
    JOB_STAGE_STARTING,
    JOB_STAGE_RECONSTRUCTING_COHORT,
    JOB_STAGE_SPLITTING_DATA,
    JOB_STAGE_PREPROCESSING,
    JOB_STAGE_TRAINING_PRIMARY,
    JOB_STAGE_TRAINING_CHALLENGER,
    JOB_STAGE_TRAINING_DIAGNOSTIC,
    JOB_STAGE_EVALUATING,
    JOB_STAGE_PERSISTING_ARTIFACT,
    JOB_STAGE_VERIFYING_ARTIFACT,
    JOB_STAGE_COMPLETED,
    JOB_STAGE_FAILED,
)

RUNNING_JOB_STAGES = (
    JOB_STAGE_STARTING,
    JOB_STAGE_RECONSTRUCTING_COHORT,
    JOB_STAGE_SPLITTING_DATA,
    JOB_STAGE_PREPROCESSING,
    JOB_STAGE_TRAINING_PRIMARY,
    JOB_STAGE_TRAINING_CHALLENGER,
    JOB_STAGE_TRAINING_DIAGNOSTIC,
    JOB_STAGE_EVALUATING,
    JOB_STAGE_PERSISTING_ARTIFACT,
    JOB_STAGE_VERIFYING_ARTIFACT,
)

_ACTIVE_STATUSES = (JOB_STATUS_QUEUED, JOB_STATUS_RUNNING)
_TERMINAL_STATUSES = (JOB_STATUS_COMPLETED, JOB_STATUS_FAILED)

_ALLOWED_REQUEST_FIELDS = (
    "analysis_run_id",
    "model_name",
    "random_seed",
    "validation_fraction",
    "run_elkan_challenger",
)
_ALLOWED_RESULT_FIELDS = (
    "model_run_id",
    "selected_candidate",
    "selection_policy",
    "quality_flags",
    "challenger_advisory_flags",
    "artifact_sha256",
    "model_role_policy_version",
    "evaluation_contract_version",
)
_FORBIDDEN_JSON_KEYS = {
    "customer_id",
    "customer_ids",
    "person_id",
    "person_ids",
    "email",
    "phone_number",
    "address_line_1",
    "address_line_2",
    "street",
    "postal_code",
    "train_matrix",
    "validation_matrix",
    "validation_scores",
    "sql",
    "query",
    "absolute_path",
}

DEFAULT_RANDOM_SEED = 42
DEFAULT_VALIDATION_FRACTION = 0.20
DEFAULT_RUN_ELKAN_CHALLENGER = True
MAXIMUM_MODEL_NAME_LENGTH = 160
MAXIMUM_MESSAGE_LENGTH = 1_024
MAXIMUM_ERROR_MESSAGE_LENGTH = 4_096
MAXIMUM_REQUEST_JSON_BYTES = 8_192
MAXIMUM_RESULT_JSON_BYTES = 32_768


class JobRepositoryError(RuntimeError):
    """Base class for bounded job repository errors."""


class JobValidationError(JobRepositoryError):
    """Raised when invalid job input is provided."""


class JobStateTransitionError(JobRepositoryError):
    """Raised when a requested state transition violates lifecycle rules."""


class ActiveTrainingJobConflictError(JobRepositoryError):
    """Raised when a MODEL_TRAINING job already exists in QUEUED or RUNNING."""


def _require_positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise JobValidationError(f"{field_name} must be a positive integer.")
    return value


def _bounded_optional_text(value: Any, *, field_name: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise JobValidationError(f"{field_name} must be text when provided.")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise JobValidationError(f"{field_name} must not exceed {maximum} characters.")
    return normalized


def _bounded_required_text(value: Any, *, field_name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise JobValidationError(f"{field_name} must be text.")
    normalized = value.strip()
    if not normalized:
        raise JobValidationError(f"{field_name} must not be blank.")
    if len(normalized) > maximum:
        raise JobValidationError(f"{field_name} must not exceed {maximum} characters.")
    return normalized


def _forbidden_key_present(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if isinstance(key, str) and key.casefold() in _FORBIDDEN_JSON_KEYS:
                return True
            if _forbidden_key_present(nested):
                return True
        return False
    if isinstance(value, list):
        return any(_forbidden_key_present(item) for item in value)
    if isinstance(value, str):
        normalized = value.strip()
        return normalized.startswith(("/", "\\\\")) or (
            len(normalized) >= 3
            and normalized[1] == ":"
            and normalized[2] in {"/", "\\"}
            and normalized[0].isalpha()
        )
    return False


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise JobValidationError("Job JSON payload contains non-serializable values.") from exc


def _validated_json(value: Any, *, maximum_bytes: int) -> str:
    if _forbidden_key_present(value):
        raise JobValidationError(
            "Job JSON payload contains forbidden content."
        )
    encoded = _canonical_json(value)
    if len(encoded.encode("utf-8")) > maximum_bytes:
        raise JobValidationError("Job JSON payload is too large.")
    return encoded


def _normalize_training_request_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise JobValidationError("request payload must be an object.")

    unexpected = sorted(set(payload) - set(_ALLOWED_REQUEST_FIELDS))
    if unexpected:
        joined = ", ".join(unexpected)
        raise JobValidationError(f"request payload contains unsupported fields: {joined}.")

    analysis_run_id = _require_positive_int(payload.get("analysis_run_id"), field_name="analysis_run_id")

    model_name = payload.get("model_name")
    if model_name is not None:
        model_name = _bounded_required_text(
            model_name,
            field_name="model_name",
            maximum=MAXIMUM_MODEL_NAME_LENGTH,
        )

    random_seed = payload.get("random_seed", DEFAULT_RANDOM_SEED)
    if isinstance(random_seed, bool) or not isinstance(random_seed, int):
        raise JobValidationError("random_seed must be an integer.")

    validation_fraction = payload.get("validation_fraction", DEFAULT_VALIDATION_FRACTION)
    if (
        isinstance(validation_fraction, bool)
        or not isinstance(validation_fraction, (int, float))
        or not math.isfinite(float(validation_fraction))
        or not 0 < float(validation_fraction) < 1
    ):
        raise JobValidationError("validation_fraction must be between 0 and 1.")

    run_elkan_challenger = payload.get(
        "run_elkan_challenger",
        DEFAULT_RUN_ELKAN_CHALLENGER,
    )
    if not isinstance(run_elkan_challenger, bool):
        raise JobValidationError("run_elkan_challenger must be a boolean.")

    normalized = {
        "analysis_run_id": analysis_run_id,
        "model_name": model_name,
        "random_seed": random_seed,
        "validation_fraction": float(validation_fraction),
        "run_elkan_challenger": run_elkan_challenger,
    }
    _validated_json(normalized, maximum_bytes=MAXIMUM_REQUEST_JSON_BYTES)
    return normalized


def _normalize_training_result_payload(
    payload: Any,
    *,
    model_run_id: int,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise JobValidationError("result payload must be an object.")

    unexpected = sorted(set(payload) - set(_ALLOWED_RESULT_FIELDS))
    if unexpected:
        joined = ", ".join(unexpected)
        raise JobValidationError(f"result payload contains unsupported fields: {joined}.")

    normalized: dict[str, Any] = {"model_run_id": model_run_id}

    selected_candidate = _bounded_required_text(
        payload.get("selected_candidate"),
        field_name="selected_candidate",
        maximum=120,
    )
    selection_policy = _bounded_required_text(
        payload.get("selection_policy"),
        field_name="selection_policy",
        maximum=120,
    )

    artifact_sha256 = payload.get("artifact_sha256")
    if not isinstance(artifact_sha256, str) or len(artifact_sha256) != 64:
        raise JobValidationError("artifact_sha256 must be a 64-character hex digest.")

    for name in ("quality_flags", "challenger_advisory_flags"):
        values = payload.get(name, [])
        if not isinstance(values, list) or not all(
            isinstance(item, str) and item.strip() for item in values
        ):
            raise JobValidationError(f"{name} must be a list of non-empty strings.")
        normalized[name] = [item.strip() for item in values]

    for name in ("model_role_policy_version", "evaluation_contract_version"):
        value = payload.get(name)
        if value is not None and not isinstance(value, str):
            raise JobValidationError(f"{name} must be text when provided.")
        normalized[name] = value

    normalized["selected_candidate"] = selected_candidate
    normalized["selection_policy"] = selection_policy
    normalized["artifact_sha256"] = artifact_sha256

    _validated_json(normalized, maximum_bytes=MAXIMUM_RESULT_JSON_BYTES)
    return normalized


class JobRepository:
    """Persist and guard Phase 4 MODEL_TRAINING job lifecycle rows."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    @staticmethod
    def _fetch_active_locked(connection: sqlite3.Connection) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT *
            FROM jobs
            WHERE job_type = ? AND status IN ('QUEUED', 'RUNNING')
            ORDER BY created_at DESC, job_id DESC
            LIMIT 1
            """,
            (JOB_TYPE_MODEL_TRAINING,),
        ).fetchone()

    @staticmethod
    def _fetch_job_locked(connection: sqlite3.Connection, *, job_id: int) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()

    def create_training_job(
        self,
        *,
        created_at: str,
        request_payload: dict[str, Any],
        message: str | None = None,
    ) -> int:
        created_timestamp = _bounded_required_text(
            created_at,
            field_name="created_at",
            maximum=64,
        )
        normalized_request = _normalize_training_request_payload(request_payload)
        normalized_message = _bounded_optional_text(
            message,
            field_name="message",
            maximum=MAXIMUM_MESSAGE_LENGTH,
        )
        request_json = _validated_json(
            normalized_request,
            maximum_bytes=MAXIMUM_REQUEST_JSON_BYTES,
        )

        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._fetch_active_locked(connection)
            if existing is not None:
                raise ActiveTrainingJobConflictError(
                    "A model training job is already active."
                )

            try:
                cursor = connection.execute(
                    """
                    INSERT INTO jobs (
                        job_type,
                        status,
                        progress_percent,
                        stage,
                        message,
                        analysis_run_id,
                        created_at,
                        request_json
                    ) VALUES (?, 'QUEUED', 0, 'QUEUED', ?, ?, ?, ?)
                    """,
                    (
                        JOB_TYPE_MODEL_TRAINING,
                        normalized_message,
                        normalized_request["analysis_run_id"],
                        created_timestamp,
                        request_json,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise JobValidationError(
                    "The selected historical analysis run does not exist."
                ) from exc

        return int(cursor.lastrowid)

    def fetch_job(self, job_id: int) -> dict[str, Any] | None:
        normalized_job_id = _require_positive_int(job_id, field_name="job_id")
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id = ?",
                (normalized_job_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def find_active_training_job(self) -> dict[str, Any] | None:
        with get_connection(self.database_path) as connection:
            row = self._fetch_active_locked(connection)
        return dict(row) if row is not None else None

    def mark_running(
        self,
        *,
        job_id: int,
        started_at: str,
        stage: str = JOB_STAGE_STARTING,
        progress_percent: int = 1,
        message: str | None = None,
    ) -> None:
        normalized_job_id = _require_positive_int(job_id, field_name="job_id")
        _bounded_required_text(started_at, field_name="started_at", maximum=64)
        if stage not in RUNNING_JOB_STAGES:
            raise JobValidationError("stage is not valid for RUNNING jobs.")
        if (
            isinstance(progress_percent, bool)
            or not isinstance(progress_percent, int)
            or not 1 <= progress_percent <= 99
        ):
            raise JobValidationError(
                "progress_percent must be between 1 and 99 for RUNNING jobs."
            )
        normalized_message = _bounded_optional_text(
            message,
            field_name="message",
            maximum=MAXIMUM_MESSAGE_LENGTH,
        )

        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._fetch_job_locked(connection, job_id=normalized_job_id)
            if current is None:
                raise JobValidationError("The requested job was not found.")
            if current["status"] != JOB_STATUS_QUEUED:
                raise JobStateTransitionError("Only QUEUED jobs can start running.")

            cursor = connection.execute(
                """
                UPDATE jobs
                SET
                    status = 'RUNNING',
                    progress_percent = ?,
                    stage = ?,
                    message = ?,
                    started_at = ?,
                    finished_at = NULL,
                    error_message = NULL
                WHERE job_id = ? AND status = 'QUEUED'
                """,
                (
                    progress_percent,
                    stage,
                    normalized_message,
                    started_at,
                    normalized_job_id,
                ),
            )
            if cursor.rowcount != 1:
                raise JobStateTransitionError("Job could not transition to RUNNING.")

    def update_progress(
        self,
        *,
        job_id: int,
        progress_percent: int,
        stage: str,
        message: str | None = None,
        model_run_id: int | None = None,
    ) -> None:
        normalized_job_id = _require_positive_int(job_id, field_name="job_id")
        if stage not in RUNNING_JOB_STAGES:
            raise JobValidationError("stage is not valid for RUNNING jobs.")
        if (
            isinstance(progress_percent, bool)
            or not isinstance(progress_percent, int)
            or not 1 <= progress_percent <= 99
        ):
            raise JobValidationError(
                "progress_percent must be between 1 and 99 for RUNNING jobs."
            )
        normalized_message = _bounded_optional_text(
            message,
            field_name="message",
            maximum=MAXIMUM_MESSAGE_LENGTH,
        )
        normalized_model_run_id: int | None = None
        if model_run_id is not None:
            normalized_model_run_id = _require_positive_int(
                model_run_id,
                field_name="model_run_id",
            )

        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._fetch_job_locked(connection, job_id=normalized_job_id)
            if current is None:
                raise JobValidationError("The requested job was not found.")
            if current["status"] != JOB_STATUS_RUNNING:
                raise JobStateTransitionError("Only RUNNING jobs accept progress updates.")
            current_progress = int(current["progress_percent"])
            if progress_percent < current_progress:
                raise JobStateTransitionError("Job progress must be monotonic.")
            existing_model_run_id = current["model_run_id"]
            if (
                existing_model_run_id is not None
                and normalized_model_run_id is not None
                and int(existing_model_run_id) != normalized_model_run_id
            ):
                raise JobStateTransitionError(
                    "model_run_id cannot change once associated with a running job."
                )
            target_model_run_id = (
                existing_model_run_id
                if normalized_model_run_id is None
                else normalized_model_run_id
            )

            try:
                cursor = connection.execute(
                    """
                    UPDATE jobs
                    SET
                        progress_percent = ?,
                        stage = ?,
                        message = ?,
                        model_run_id = ?
                    WHERE job_id = ? AND status = 'RUNNING' AND progress_percent <= ?
                    """,
                    (
                        progress_percent,
                        stage,
                        normalized_message,
                        target_model_run_id,
                        normalized_job_id,
                        progress_percent,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise JobValidationError("The related model run does not exist.") from exc
            if cursor.rowcount != 1:
                raise JobStateTransitionError("Job progress update was rejected.")

    def mark_completed(
        self,
        *,
        job_id: int,
        finished_at: str,
        model_run_id: int,
        result_payload: dict[str, Any],
        message: str | None = None,
    ) -> None:
        normalized_job_id = _require_positive_int(job_id, field_name="job_id")
        _bounded_required_text(finished_at, field_name="finished_at", maximum=64)
        normalized_model_run_id = _require_positive_int(
            model_run_id,
            field_name="model_run_id",
        )
        normalized_message = _bounded_optional_text(
            message,
            field_name="message",
            maximum=MAXIMUM_MESSAGE_LENGTH,
        )
        normalized_result = _normalize_training_result_payload(
            result_payload,
            model_run_id=normalized_model_run_id,
        )
        result_json = _validated_json(
            normalized_result,
            maximum_bytes=MAXIMUM_RESULT_JSON_BYTES,
        )

        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._fetch_job_locked(connection, job_id=normalized_job_id)
            if current is None:
                raise JobValidationError("The requested job was not found.")
            if current["status"] != JOB_STATUS_RUNNING:
                raise JobStateTransitionError("Only RUNNING jobs can complete.")

            try:
                cursor = connection.execute(
                    """
                    UPDATE jobs
                    SET
                        status = 'COMPLETED',
                        progress_percent = 100,
                        stage = 'COMPLETED',
                        message = ?,
                        model_run_id = ?,
                        finished_at = ?,
                        result_json = ?,
                        error_message = NULL
                    WHERE job_id = ? AND status = 'RUNNING'
                    """,
                    (
                        normalized_message,
                        normalized_model_run_id,
                        finished_at,
                        result_json,
                        normalized_job_id,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise JobValidationError("The related model run does not exist.") from exc
            if cursor.rowcount != 1:
                raise JobStateTransitionError("Job could not transition to COMPLETED.")

    def mark_failed(
        self,
        *,
        job_id: int,
        finished_at: str,
        error_message: str,
        model_run_id: int | None = None,
        message: str | None = None,
    ) -> None:
        normalized_job_id = _require_positive_int(job_id, field_name="job_id")
        _bounded_required_text(finished_at, field_name="finished_at", maximum=64)
        normalized_error = _bounded_required_text(
            error_message,
            field_name="error_message",
            maximum=MAXIMUM_ERROR_MESSAGE_LENGTH,
        )
        normalized_message = _bounded_optional_text(
            message,
            field_name="message",
            maximum=MAXIMUM_MESSAGE_LENGTH,
        )
        normalized_model_run_id = None
        if model_run_id is not None:
            normalized_model_run_id = _require_positive_int(
                model_run_id,
                field_name="model_run_id",
            )

        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._fetch_job_locked(connection, job_id=normalized_job_id)
            if current is None:
                raise JobValidationError("The requested job was not found.")
            if current["status"] in _TERMINAL_STATUSES:
                raise JobStateTransitionError("Terminal jobs cannot transition again.")

            existing_model_run_id = current["model_run_id"]
            target_model_run_id = (
                normalized_model_run_id
                if normalized_model_run_id is not None
                else existing_model_run_id
            )
            progress_percent = int(current["progress_percent"])
            if progress_percent > 99:
                progress_percent = 99

            try:
                cursor = connection.execute(
                    """
                    UPDATE jobs
                    SET
                        status = 'FAILED',
                        progress_percent = ?,
                        stage = 'FAILED',
                        message = ?,
                        model_run_id = ?,
                        finished_at = ?,
                        result_json = NULL,
                        error_message = ?
                    WHERE job_id = ? AND status IN ('QUEUED', 'RUNNING')
                    """,
                    (
                        progress_percent,
                        normalized_message,
                        target_model_run_id,
                        finished_at,
                        normalized_error,
                        normalized_job_id,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise JobValidationError("The related model run does not exist.") from exc
            if cursor.rowcount != 1:
                raise JobStateTransitionError("Job could not transition to FAILED.")

    def fail_stale_active_jobs(
        self,
        *,
        finished_at: str,
        error_message: str,
    ) -> int:
        _bounded_required_text(finished_at, field_name="finished_at", maximum=64)
        normalized_error = _bounded_required_text(
            error_message,
            field_name="error_message",
            maximum=MAXIMUM_ERROR_MESSAGE_LENGTH,
        )
        with get_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET
                    status = 'FAILED',
                    progress_percent = CASE
                        WHEN progress_percent < 0 THEN 0
                        WHEN progress_percent > 99 THEN 99
                        ELSE progress_percent
                    END,
                    stage = 'FAILED',
                    finished_at = ?,
                    result_json = NULL,
                    error_message = ?
                WHERE job_type = ? AND status IN ('QUEUED', 'RUNNING')
                """,
                (
                    finished_at,
                    normalized_error,
                    JOB_TYPE_MODEL_TRAINING,
                ),
            )
        return int(cursor.rowcount)


__all__ = (
    "ALL_JOB_STAGES",
    "ActiveTrainingJobConflictError",
    "JOB_STAGE_COMPLETED",
    "JOB_STAGE_FAILED",
    "JOB_STAGE_QUEUED",
    "JOB_STAGE_STARTING",
    "JOB_STATUS_COMPLETED",
    "JOB_STATUS_FAILED",
    "JOB_STATUS_QUEUED",
    "JOB_STATUS_RUNNING",
    "JOB_TYPE_MODEL_TRAINING",
    "JobRepository",
    "JobRepositoryError",
    "JobStateTransitionError",
    "JobValidationError",
    "RUNNING_JOB_STAGES",
)