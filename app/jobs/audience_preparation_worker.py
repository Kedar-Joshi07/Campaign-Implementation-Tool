"""Top-level worker target that runs one persisted audience preparation job."""

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
    JOB_STAGE_PREPARING_RANK_BOUNDARIES,
    JOB_STAGE_STARTING,
    JOB_STAGE_VALIDATING_SCORING_RUN,
    JOB_STAGE_VERIFYING_RANK_BOUNDARIES,
    JOB_STATUS_QUEUED,
    JOB_TYPE_AUDIENCE_PREPARATION,
    JobRepository,
    JobStateTransitionError,
    JobValidationError,
)
from app.services.audience_preparation_service import (
    AudiencePreparationConflictError,
    AudiencePreparationValidationError,
    run_audience_rank_preparation,
)


logger = logging.getLogger(__name__)

WORKER_STARTING_MESSAGE = "Audience preparation worker started."
WORKER_COMPLETED_MESSAGE = "Audience preparation completed."
WORKER_FAILED_MESSAGE = "Audience preparation could not be completed."
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


def _result_payload_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "scoring_run_id": int(summary["scoring_run_id"]),
        "total_population": int(summary["total_population"]),
        "rank_contract_version": str(summary["rank_contract_version"]),
        "boundary_count": int(summary["boundary_count"]),
    }
    if "analytics_contract_version" in summary:
        payload["analytics_contract_version"] = str(summary["analytics_contract_version"])
    if "analytics_prepared" in summary:
        payload["analytics_prepared"] = bool(summary["analytics_prepared"])
    metric_fields = (
        "scanned_rows",
        "chunk_size",
        "chunk_count",
        "largest_chunk_rows",
        "runtime_seconds",
        "rows_per_second",
    )
    if all(field in summary for field in metric_fields):
        payload.update(
            {
                "scanned_rows": int(summary["scanned_rows"]),
                "chunk_size": int(summary["chunk_size"]),
                "chunk_count": int(summary["chunk_count"]),
                "largest_chunk_rows": int(summary["largest_chunk_rows"]),
                "runtime_seconds": float(summary["runtime_seconds"]),
                "rows_per_second": float(summary["rows_per_second"]),
                "metrics_available": True,
            }
        )
    return payload


def _mark_failed(
    repository: JobRepository,
    *,
    job_id: int,
    exc: Exception,
) -> None:
    try:
        repository.mark_failed(
            job_id=job_id,
            finished_at=_utc_timestamp(),
            error_message=_bounded_internal_error(exc),
            model_run_id=None,
            message=WORKER_FAILED_MESSAGE,
        )
    except JobStateTransitionError:
        logger.warning(
            "Audience preparation worker could not mark failed because job is already terminal | job_id=%s",
            job_id,
        )


def run_audience_preparation_job(database_path: str | Path, job_id: int) -> None:
    """Execute one queued AUDIENCE_PREPARATION job and persist lifecycle transitions."""
    path = initialize_database(database_path)
    repository = JobRepository(path)
    row = repository.fetch_job(job_id)
    if row is None:
        logger.warning("Audience preparation worker received unknown job_id=%s", job_id)
        return
    if row["job_type"] != JOB_TYPE_AUDIENCE_PREPARATION:
        logger.warning(
            "Audience preparation worker received non-audience job | job_id=%s type=%s",
            job_id,
            row["job_type"],
        )
        return
    if row["status"] != JOB_STATUS_QUEUED:
        logger.info(
            "Audience preparation worker skipped non-queued job | job_id=%s status=%s",
            job_id,
            row["status"],
        )
        return

    try:
        request_payload = json.loads(row["request_json"])
        if not isinstance(request_payload, dict):
            raise ValueError("request_json must decode to an object.")

        scoring_run_id = _require_positive_int(
            request_payload.get("scoring_run_id"),
            field_name="scoring_run_id",
        )
        rank_contract_version = request_payload.get("rank_contract_version")
        if not isinstance(rank_contract_version, str) or not rank_contract_version.strip():
            raise ValueError("rank_contract_version must be a non-empty string.")

        repository.mark_running(
            job_id=job_id,
            started_at=_utc_timestamp(),
            stage=JOB_STAGE_STARTING,
            progress_percent=2,
            message=WORKER_STARTING_MESSAGE,
        )
        repository.update_progress(
            job_id=job_id,
            progress_percent=10,
            stage=JOB_STAGE_VALIDATING_SCORING_RUN,
            message="Validating scoring run currentness and provenance.",
            model_run_id=None,
        )
        repository.update_progress(
            job_id=job_id,
            progress_percent=70,
            stage=JOB_STAGE_PREPARING_RANK_BOUNDARIES,
            message="Preparing deterministic percentile boundaries.",
            model_run_id=None,
        )

        summary = run_audience_rank_preparation(
            path,
            scoring_run_id=scoring_run_id,
            rank_contract_version=rank_contract_version,
        )

        repository.update_progress(
            job_id=job_id,
            progress_percent=95,
            stage=JOB_STAGE_VERIFYING_RANK_BOUNDARIES,
            message="Verifying persisted boundary completeness.",
            model_run_id=None,
        )

        repository.mark_completed(
            job_id=job_id,
            finished_at=_utc_timestamp(),
            model_run_id=None,
            result_payload=_result_payload_from_summary(summary),
            message=WORKER_COMPLETED_MESSAGE,
        )
    except (
        JobValidationError,
        JobStateTransitionError,
        AudiencePreparationValidationError,
        AudiencePreparationConflictError,
        TypeError,
        ValueError,
        KeyError,
    ) as exc:
        _mark_failed(repository, job_id=job_id, exc=exc)
    except Exception as exc:
        logger.exception("Unexpected audience preparation worker failure | job_id=%s", job_id)
        _mark_failed(repository, job_id=job_id, exc=exc)


__all__ = ("run_audience_preparation_job",)
