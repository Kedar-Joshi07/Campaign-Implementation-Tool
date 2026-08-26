"""Prospect-scoring job orchestration service for bounded background execution."""

from __future__ import annotations

import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.database.schema import initialize_database
from app.jobs.executor import submit_prospect_scoring_job
from app.repositories.job_repository import (
    ActiveComputeJobConflictError,
    JobRepository,
    JobValidationError,
)
from app.services.model_scoring_compatibility import (
    ModelScoreabilityValidationError,
    validate_scoreable_model,
)
from app.services.prospect_scoring_service import find_current_canonical_run_for_model


MODEL_NOT_SCOREABLE_MESSAGE = "The selected model is not available for prospect scoring."
ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE = "A compute job is already active."
EXISTING_SCORING_RUN_CONFLICT_MESSAGE = (
    "A completed prospect scoring run already exists for this model."
)
SUBMISSION_FAILURE_MESSAGE = "Prospect scoring could not be completed."
MAXIMUM_INTERNAL_ERROR_LENGTH = 4_096


class ScoringJobServiceError(RuntimeError):
    """Base class for scoring-job orchestration errors."""


class ScoringJobValidationError(ScoringJobServiceError):
    """Raised when a scoring request cannot be accepted."""


class ScoringJobConflictError(ScoringJobServiceError):
    """Raised when scoring submission conflicts with active or canonical state."""


class ScoringJobSubmissionError(ScoringJobServiceError):
    """Raised when worker submission fails after queue persistence."""


WorkerSubmitter = Callable[[str | Path, int], Any]


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _bounded_internal_error(exc: Exception) -> str:
    diagnostic = traceback.format_exc()[-MAXIMUM_INTERNAL_ERROR_LENGTH:]
    if diagnostic.strip():
        return diagnostic
    return f"{type(exc).__name__}: {exc}"[:MAXIMUM_INTERNAL_ERROR_LENGTH]


def _model_run_id_from_request(payload: Any) -> int:
    if not isinstance(payload, dict):
        raise ScoringJobValidationError("Scoring request must be a JSON object.")
    model_run_id = payload.get("model_run_id")
    if isinstance(model_run_id, bool) or not isinstance(model_run_id, int) or model_run_id <= 0:
        raise ScoringJobValidationError(MODEL_NOT_SCOREABLE_MESSAGE)
    return model_run_id


def submit_prospect_scoring_job_request(
    database_path: str | Path | None,
    request_payload: dict[str, Any],
    *,
    submitter: WorkerSubmitter | None = None,
) -> dict[str, Any]:
    """Persist a queued scoring job and submit background execution immediately."""
    path = initialize_database(database_path)
    model_run_id = _model_run_id_from_request(request_payload)

    try:
        validate_scoreable_model(path, model_run_id)
    except ModelScoreabilityValidationError as exc:
        raise ScoringJobValidationError(MODEL_NOT_SCOREABLE_MESSAGE) from exc

    current_canonical_run = find_current_canonical_run_for_model(
        path,
        model_run_id=model_run_id,
    )
    if current_canonical_run is not None:
        raise ScoringJobConflictError(EXISTING_SCORING_RUN_CONFLICT_MESSAGE)

    repository = JobRepository(path)
    if repository.find_active_compute_job() is not None:
        raise ScoringJobConflictError(ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE)

    try:
        job_id = repository.create_scoring_job(
            created_at=_utc_timestamp(),
            request_payload={"model_run_id": model_run_id},
        )
    except ActiveComputeJobConflictError as exc:
        raise ScoringJobConflictError(ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE) from exc
    except JobValidationError as exc:
        raise ScoringJobValidationError(str(exc)) from exc

    worker_submitter = submit_prospect_scoring_job if submitter is None else submitter
    try:
        worker_submitter(path, job_id)
    except Exception as exc:
        repository.mark_failed(
            job_id=job_id,
            finished_at=_utc_timestamp(),
            error_message=_bounded_internal_error(exc),
            model_run_id=model_run_id,
            message=SUBMISSION_FAILURE_MESSAGE,
        )
        raise ScoringJobSubmissionError(SUBMISSION_FAILURE_MESSAGE) from exc

    row = repository.fetch_job(job_id)
    if row is None:
        raise ScoringJobServiceError("Queued scoring job could not be reloaded.")
    return row


__all__ = (
    "ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE",
    "EXISTING_SCORING_RUN_CONFLICT_MESSAGE",
    "MODEL_NOT_SCOREABLE_MESSAGE",
    "SUBMISSION_FAILURE_MESSAGE",
    "ScoringJobConflictError",
    "ScoringJobServiceError",
    "ScoringJobSubmissionError",
    "ScoringJobValidationError",
    "submit_prospect_scoring_job_request",
)
