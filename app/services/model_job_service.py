"""Model-training job orchestration service for Phase 4 background execution."""

from __future__ import annotations

import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.database.schema import initialize_database
from app.jobs.executor import submit_model_training_job
from app.repositories.historical_repository import HistoricalRepository
from app.repositories.job_repository import (
    ActiveTrainingJobConflictError,
    JobRepository,
    JobValidationError,
)
from app.repositories.scoring_repository import ScoringRepository


ANALYSIS_NOT_AVAILABLE_MESSAGE = "The selected historical analysis is not available for training."
ACTIVE_JOB_CONFLICT_MESSAGE = "A model training job is already active."
SUBMISSION_FAILURE_MESSAGE = "Model training could not be completed."
STALE_JOB_INTERRUPTION_MESSAGE = (
    "Model training was interrupted by application restart."
)
STALE_SCORING_INTERRUPTION_MESSAGE = (
    "Prospect scoring was interrupted by application restart."
)
MAXIMUM_INTERNAL_ERROR_LENGTH = 4_096


class ModelJobServiceError(RuntimeError):
    """Base class for model-job orchestration errors."""


class ModelJobValidationError(ModelJobServiceError):
    """Raised when a training request cannot be accepted."""


class ModelJobConflictError(ModelJobServiceError):
    """Raised when a model-training job is already active."""


class ModelJobSubmissionError(ModelJobServiceError):
    """Raised when worker submission fails after persisting a queued job."""


WorkerSubmitter = Callable[[str | Path, int], Any]


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _analysis_run_id_from_request(payload: Any) -> int:
    if not isinstance(payload, dict):
        raise ModelJobValidationError("Training request must be a JSON object.")
    analysis_run_id = payload.get("analysis_run_id")
    if (
        isinstance(analysis_run_id, bool)
        or not isinstance(analysis_run_id, int)
        or analysis_run_id <= 0
    ):
        raise ModelJobValidationError(ANALYSIS_NOT_AVAILABLE_MESSAGE)
    return analysis_run_id


def _ensure_completed_analysis(database_path: Path, analysis_run_id: int) -> None:
    run = HistoricalRepository(database_path).fetch_analysis_run(analysis_run_id)
    if run is None or run["status"] != "COMPLETED":
        raise ModelJobValidationError(ANALYSIS_NOT_AVAILABLE_MESSAGE)


def _bounded_internal_error(exc: Exception) -> str:
    diagnostic = traceback.format_exc()[-MAXIMUM_INTERNAL_ERROR_LENGTH:]
    if diagnostic.strip():
        return diagnostic
    return f"{type(exc).__name__}: {exc}"[:MAXIMUM_INTERNAL_ERROR_LENGTH]


def submit_model_training_job_request(
    database_path: str | Path | None,
    request_payload: dict[str, Any],
    *,
    submitter: WorkerSubmitter | None = None,
) -> dict[str, Any]:
    """Persist a queued job and submit background execution immediately."""
    path = initialize_database(database_path)
    analysis_run_id = _analysis_run_id_from_request(request_payload)
    _ensure_completed_analysis(path, analysis_run_id)
    repository = JobRepository(path)

    try:
        job_id = repository.create_training_job(
            created_at=_utc_timestamp(),
            request_payload=request_payload,
        )
    except ActiveTrainingJobConflictError as exc:
        raise ModelJobConflictError(ACTIVE_JOB_CONFLICT_MESSAGE) from exc
    except JobValidationError as exc:
        raise ModelJobValidationError(str(exc)) from exc

    worker_submitter = submit_model_training_job if submitter is None else submitter
    try:
        worker_submitter(path, job_id)
    except Exception as exc:
        repository.mark_failed(
            job_id=job_id,
            finished_at=_utc_timestamp(),
            error_message=_bounded_internal_error(exc),
            message=SUBMISSION_FAILURE_MESSAGE,
        )
        raise ModelJobSubmissionError(SUBMISSION_FAILURE_MESSAGE) from exc

    row = repository.fetch_job(job_id)
    if row is None:
        raise ModelJobServiceError("Queued job could not be reloaded.")
    return row


def reconcile_stale_model_training_jobs(
    database_path: str | Path | None,
) -> int:
    """Fail stale active compute jobs and stale RUNNING scoring runs at startup."""
    path = initialize_database(database_path)
    stale_jobs_failed = JobRepository(path).fail_stale_active_jobs(
        finished_at=_utc_timestamp(),
        error_message=STALE_JOB_INTERRUPTION_MESSAGE,
    )
    ScoringRepository(path).fail_running_scoring_runs(
        completed_at=_utc_timestamp(),
        error_message=STALE_SCORING_INTERRUPTION_MESSAGE,
    )
    return stale_jobs_failed


__all__ = (
    "ACTIVE_JOB_CONFLICT_MESSAGE",
    "ANALYSIS_NOT_AVAILABLE_MESSAGE",
    "ModelJobConflictError",
    "ModelJobServiceError",
    "ModelJobSubmissionError",
    "ModelJobValidationError",
    "STALE_SCORING_INTERRUPTION_MESSAGE",
    "STALE_JOB_INTERRUPTION_MESSAGE",
    "SUBMISSION_FAILURE_MESSAGE",
    "reconcile_stale_model_training_jobs",
    "submit_model_training_job_request",
)