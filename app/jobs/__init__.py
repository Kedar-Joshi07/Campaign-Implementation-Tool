"""Background job orchestration package for Phase 4."""

from app.jobs.executor import (
    EXECUTOR_MAX_WORKERS,
    get_model_training_executor,
    is_model_training_executor_initialized,
    shutdown_model_training_executor,
    submit_prospect_scoring_job,
    submit_model_training_job,
)
from app.jobs.model_training_worker import run_model_training_job
from app.jobs.prospect_scoring_worker import run_prospect_scoring_job

__all__ = (
    "EXECUTOR_MAX_WORKERS",
    "get_model_training_executor",
    "is_model_training_executor_initialized",
    "run_model_training_job",
    "run_prospect_scoring_job",
    "shutdown_model_training_executor",
    "submit_prospect_scoring_job",
    "submit_model_training_job",
)