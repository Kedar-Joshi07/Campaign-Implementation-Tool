"""Top-level worker target that runs one persisted prospect-scoring job."""

from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.database.schema import initialize_database
from app.repositories.job_repository import (
    JOB_STAGE_COMPLETED,
    JOB_STAGE_FAILED,
    JOB_STAGE_STARTING,
    JOB_STATUS_QUEUED,
    JOB_TYPE_PROSPECT_SCORING,
    JobRepository,
    JobStateTransitionError,
    JobValidationError,
)
from app.services.model_scoring_compatibility import ModelScoreabilityValidationError
from app.services.prospect_scoring_service import (
    ProspectScoringExecutionError,
    run_chunked_prospect_scoring,
)


logger = logging.getLogger(__name__)

WORKER_STARTING_MESSAGE = "Prospect scoring worker started."
WORKER_COMPLETED_MESSAGE = "Prospect scoring completed."
WORKER_FAILED_MESSAGE = "Prospect scoring could not be completed."
MAXIMUM_INTERNAL_ERROR_LENGTH = 4_096


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _bounded_internal_error(exc: Exception) -> str:
    diagnostic = traceback.format_exc()[-MAXIMUM_INTERNAL_ERROR_LENGTH:]
    if diagnostic.strip():
        return diagnostic
    return f"{type(exc).__name__}: {exc}"[:MAXIMUM_INTERNAL_ERROR_LENGTH]


def _require_positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")
    return value


def _result_payload_from_summary(
    *,
    model_run_id: int,
    scoring_result: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "scoring_run_id": int(scoring_result["scoring_run_id"]),
        "model_run_id": int(model_run_id),
        "scored_person_count": int(scoring_result["scored_person_count"]),
        "score_min": float(scoring_result["score_min"]),
        "score_max": float(scoring_result["score_max"]),
        "score_mean": float(scoring_result["score_mean"]),
        "total_seconds": float(summary["total_seconds"]),
        "rows_per_second": float(summary["rows_per_second"]),
        "chunk_size": int(summary["chunk_size"]),
        "chunk_count": int(summary["chunk_count"]),
        "largest_chunk_rows": int(summary["largest_chunk_rows"]),
        "largest_transformed_matrix_bytes": int(summary["largest_transformed_matrix_bytes"]),
        "selected_candidate": str(summary["selected_candidate"]),
        "model_role_policy_version": str(summary["model_role_policy_version"]),
        "feature_contract_version": str(summary["feature_contract_version"]),
        "feature_contract_sha256": str(summary["feature_contract_sha256"]),
        "artifact_sha256": str(summary["artifact_sha256"]),
    }


def _mark_failed(
    repository: JobRepository,
    *,
    job_id: int,
    model_run_id: int | None,
    exc: Exception,
) -> None:
    try:
        repository.mark_failed(
            job_id=job_id,
            finished_at=_utc_timestamp(),
            error_message=_bounded_internal_error(exc),
            model_run_id=model_run_id,
            message=WORKER_FAILED_MESSAGE,
        )
    except JobStateTransitionError:
        logger.warning(
            "Prospect-scoring worker could not mark failed because job is already terminal | job_id=%s",
            job_id,
        )


def run_prospect_scoring_job(database_path: str | Path, job_id: int) -> None:
    """Execute one queued PROSPECT_SCORING job and persist lifecycle transitions."""
    path = initialize_database(database_path)
    repository = JobRepository(path)
    row = repository.fetch_job(job_id)
    if row is None:
        logger.warning("Prospect-scoring worker received unknown job_id=%s", job_id)
        return
    if row["job_type"] != JOB_TYPE_PROSPECT_SCORING:
        logger.warning(
            "Prospect-scoring worker received non-scoring job | job_id=%s type=%s",
            job_id,
            row["job_type"],
        )
        return
    if row["status"] != JOB_STATUS_QUEUED:
        logger.info(
            "Prospect-scoring worker skipped non-queued job | job_id=%s status=%s",
            job_id,
            row["status"],
        )
        return

    model_run_id: int | None = None
    try:
        request_payload = json.loads(row["request_json"])
        if not isinstance(request_payload, dict):
            raise ValueError("request_json must decode to an object.")
        model_run_id = _require_positive_int(
            request_payload.get("model_run_id"),
            field_name="model_run_id",
        )

        repository.mark_running(
            job_id=job_id,
            started_at=_utc_timestamp(),
            stage=JOB_STAGE_STARTING,
            progress_percent=2,
            message=WORKER_STARTING_MESSAGE,
        )

        def progress_callback(
            stage: str,
            progress_percent: int,
            message: str | None,
            _scoring_run_id: int | None,
        ) -> None:
            if stage in {JOB_STAGE_COMPLETED, JOB_STAGE_FAILED}:
                return
            if progress_percent < 1 or progress_percent > 99:
                return
            repository.update_progress(
                job_id=job_id,
                progress_percent=progress_percent,
                stage=stage,
                message=message,
                model_run_id=model_run_id,
            )

        scoring_result = run_chunked_prospect_scoring(
            path,
            model_run_id=model_run_id,
            job_id=job_id,
            progress_callback=progress_callback,
        )
        summary = scoring_result["summary"]
        repository.mark_completed(
            job_id=job_id,
            finished_at=_utc_timestamp(),
            model_run_id=model_run_id,
            result_payload=_result_payload_from_summary(
                model_run_id=model_run_id,
                scoring_result=scoring_result,
                summary=summary,
            ),
            message=WORKER_COMPLETED_MESSAGE,
        )
    except (
        JobValidationError,
        JobStateTransitionError,
        ModelScoreabilityValidationError,
        ProspectScoringExecutionError,
        TypeError,
        ValueError,
        KeyError,
    ) as exc:
        _mark_failed(repository, job_id=job_id, model_run_id=model_run_id, exc=exc)
    except Exception as exc:
        logger.exception("Unexpected prospect-scoring worker failure | job_id=%s", job_id)
        _mark_failed(repository, job_id=job_id, model_run_id=model_run_id, exc=exc)


__all__ = ("run_prospect_scoring_job",)
