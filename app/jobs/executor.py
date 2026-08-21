"""Bounded lazy executor for Phase 4 model-training background jobs."""

from __future__ import annotations

from concurrent.futures import Future, ProcessPoolExecutor
from pathlib import Path
from threading import Lock

from app.jobs.model_training_worker import run_model_training_job


EXECUTOR_MAX_WORKERS = 1

_EXECUTOR_LOCK = Lock()
_MODEL_TRAINING_EXECUTOR: ProcessPoolExecutor | None = None


def is_model_training_executor_initialized() -> bool:
    """Return whether the bounded process executor has been created."""
    return _MODEL_TRAINING_EXECUTOR is not None


def get_model_training_executor() -> ProcessPoolExecutor:
    """Create and return the bounded process executor lazily."""
    global _MODEL_TRAINING_EXECUTOR
    with _EXECUTOR_LOCK:
        if _MODEL_TRAINING_EXECUTOR is None:
            _MODEL_TRAINING_EXECUTOR = ProcessPoolExecutor(
                max_workers=EXECUTOR_MAX_WORKERS
            )
        return _MODEL_TRAINING_EXECUTOR


def submit_model_training_job(
    database_path: str | Path,
    job_id: int,
) -> Future[None]:
    """Submit one top-level worker target for PROCESS-bound execution."""
    if isinstance(job_id, bool) or not isinstance(job_id, int) or job_id <= 0:
        raise ValueError("job_id must be a positive integer.")
    path = str(Path(database_path))
    executor = get_model_training_executor()
    return executor.submit(run_model_training_job, path, job_id)


def shutdown_model_training_executor(*, wait: bool = False) -> None:
    """Shut down the process executor if it was created."""
    global _MODEL_TRAINING_EXECUTOR
    with _EXECUTOR_LOCK:
        executor = _MODEL_TRAINING_EXECUTOR
        _MODEL_TRAINING_EXECUTOR = None
    if executor is not None:
        executor.shutdown(wait=wait, cancel_futures=True)


__all__ = (
    "EXECUTOR_MAX_WORKERS",
    "get_model_training_executor",
    "is_model_training_executor_initialized",
    "shutdown_model_training_executor",
    "submit_model_training_job",
)