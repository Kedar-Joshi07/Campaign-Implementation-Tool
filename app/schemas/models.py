"""Typed request/response contracts for Phase 4 model and job APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ModelRunStatus = Literal["RUNNING", "COMPLETED", "FAILED"]
JobStatus = Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"]


class ModelApiResponseModel(BaseModel):
    """Strict model API response model that rejects NaN/Infinity and extras."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ModelTrainingRequest(BaseModel):
    """Validated Phase 4 model-training request payload."""

    model_config = ConfigDict(extra="forbid")

    analysis_run_id: int = Field(gt=0)
    model_name: str | None = Field(default=None, max_length=160)
    random_seed: int = 42
    validation_fraction: float = Field(default=0.2, gt=0, lt=1)
    run_elkan_challenger: bool = True

    @field_validator("model_name", mode="before")
    @classmethod
    def normalize_model_name(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("model_name must not be blank")
        return normalized


class JobSummaryResponse(ModelApiResponseModel):
    job_id: int = Field(gt=0)
    job_type: str
    status: JobStatus
    progress_percent: int = Field(ge=0, le=100)
    stage: str
    message: str | None = None
    analysis_run_id: int | None = Field(default=None, gt=0)
    model_run_id: int | None = Field(default=None, gt=0)
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobDetailResponse(JobSummaryResponse):
    result: dict[str, Any] | None = None
    failure_message: str | None = None


class ModelRunSummaryResponse(ModelApiResponseModel):
    model_run_id: int = Field(gt=0)
    analysis_run_id: int = Field(gt=0)
    model_name: str
    created_at: datetime
    completed_at: datetime | None = None
    status: ModelRunStatus
    selected_candidate: str | None = None
    selection_policy: str | None = None
    model_role_policy_version: str | None = None
    validation_lift_at_10_percent: float | None = None


class ModelRunDetailResponse(ModelApiResponseModel):
    identity: dict[str, Any]
    cohort: dict[str, Any]
    governance: dict[str, Any]
    candidates: dict[str, Any]
    challenger_comparison: dict[str, Any]
    quality_flags: list[str]
    artifact: dict[str, Any]
    feature_contract: dict[str, Any]
    runtime: dict[str, Any]


class TrainingOptionAnalysisResponse(ModelApiResponseModel):
    analysis_run_id: int = Field(gt=0)
    analysis_name: str
    completed_at: datetime
    conversion_definition: str
    selected_customer_count: int = Field(ge=0)
    positive_customer_count: int = Field(ge=0)
    unlabeled_customer_count: int = Field(ge=0)


class ModelTrainingOptionsResponse(ModelApiResponseModel):
    completed_analyses: list[TrainingOptionAnalysisResponse] = Field(max_length=100)
    defaults: dict[str, Any]
    governance: dict[str, Any]
    active_job: JobSummaryResponse | None = None
