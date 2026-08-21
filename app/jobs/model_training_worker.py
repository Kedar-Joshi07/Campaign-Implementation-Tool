"""Top-level worker target that runs one persisted model-training job."""

from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.database.schema import initialize_database
from app.repositories.job_repository import (
    JOB_STAGE_STARTING,
    JOB_STATUS_QUEUED,
    JobRepository,
)
from app.services.model_training_service import (
    TRAINING_PROGRESS_STAGES,
    ModelTrainingExecutionError,
    ModelTrainingServiceError,
    train_and_persist_model,
)


logger = logging.getLogger(__name__)

WORKER_STARTING_MESSAGE = "Model training worker started."
WORKER_COMPLETED_MESSAGE = "Model training completed."
WORKER_FAILED_MESSAGE = "Model training could not be completed."
MAXIMUM_INTERNAL_ERROR_LENGTH = 4_096


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _bounded_internal_error(exc: Exception) -> str:
    diagnostic = traceback.format_exc()[-MAXIMUM_INTERNAL_ERROR_LENGTH:]
    if diagnostic.strip():
        return diagnostic
    return f"{type(exc).__name__}: {exc}"[:MAXIMUM_INTERNAL_ERROR_LENGTH]


def _result_payload_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_run_id": int(summary["model_run_id"]),
        "selected_candidate": str(summary["selected_candidate"]),
        "selection_policy": str(summary["selection_policy"]),
        "quality_flags": list(summary.get("quality_flags", [])),
        "challenger_advisory_flags": list(
            summary.get("challenger_advisory_flags", [])
        ),
        "artifact_sha256": str(summary["artifact_sha256"]),
        "model_role_policy_version": str(summary.get("model_role_policy_version", "")),
        "evaluation_contract_version": str(summary.get("evaluation_contract_version", "")),
    }


def run_model_training_job(database_path: str | Path, job_id: int) -> None:
    """Execute one queued MODEL_TRAINING job and persist state transitions."""
    path = initialize_database(database_path)
    repository = JobRepository(path)
    row = repository.fetch_job(job_id)
    if row is None:
        logger.warning("Model-training worker received unknown job_id=%s", job_id)
        return
    if row["status"] != JOB_STATUS_QUEUED:
        logger.info(
            "Model-training worker skipped non-queued job | job_id=%s status=%s",
            job_id,
            row["status"],
        )
        return

    try:
        request_payload = json.loads(row["request_json"])
    except (TypeError, ValueError) as exc:
        repository.mark_failed(
            job_id=job_id,
            finished_at=_utc_timestamp(),
            error_message=_bounded_internal_error(exc),
            message=WORKER_FAILED_MESSAGE,
        )
        return

    repository.mark_running(
        job_id=job_id,
        started_at=_utc_timestamp(),
        stage=JOB_STAGE_STARTING,
        progress_percent=TRAINING_PROGRESS_STAGES[JOB_STAGE_STARTING],
        message=WORKER_STARTING_MESSAGE,
    )

    def progress_callback(
        stage: str,
        progress_percent: int,
        message: str | None,
        model_run_id: int | None,
    ) -> None:
        repository.update_progress(
            job_id=job_id,
            progress_percent=progress_percent,
            stage=stage,
            message=message,
            model_run_id=model_run_id,
        )

    try:
        summary = train_and_persist_model(
            path,
            int(request_payload["analysis_run_id"]),
            model_name=request_payload.get("model_name"),
            random_seed=int(request_payload["random_seed"]),
            validation_fraction=float(request_payload["validation_fraction"]),
            run_elkan_challenger=bool(request_payload["run_elkan_challenger"]),
            progress_callback=progress_callback,
        )
        model_run_id = int(summary["model_run_id"])
        repository.mark_completed(
            job_id=job_id,
            finished_at=_utc_timestamp(),
            model_run_id=model_run_id,
            result_payload=_result_payload_from_summary(summary),
            message=WORKER_COMPLETED_MESSAGE,
        )
    except ModelTrainingExecutionError as exc:
        repository.mark_failed(
            job_id=job_id,
            finished_at=_utc_timestamp(),
            error_message=WORKER_FAILED_MESSAGE,
            model_run_id=exc.model_run_id,
            message=WORKER_FAILED_MESSAGE,
        )
    except ModelTrainingServiceError as exc:
        repository.mark_failed(
            job_id=job_id,
            finished_at=_utc_timestamp(),
            error_message=_bounded_internal_error(exc),
            message=WORKER_FAILED_MESSAGE,
        )
    except Exception as exc:
        logger.exception("Unexpected model-training worker failure | job_id=%s", job_id)
        repository.mark_failed(
            job_id=job_id,
            finished_at=_utc_timestamp(),
            error_message=_bounded_internal_error(exc),
            message=WORKER_FAILED_MESSAGE,
        )


__all__ = ("run_model_training_job",)