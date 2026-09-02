"""Typed request/response contracts for Phase 4 model and job APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ModelRunStatus = Literal["RUNNING", "COMPLETED", "FAILED"]
JobStatus = Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"]
ScoringRunStatus = Literal["RUNNING", "COMPLETED", "FAILED"]


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


class CompletedScoringRunReferenceResponse(ModelApiResponseModel):
    scoring_run_id: int = Field(gt=0)
    status: ScoringRunStatus
    completed_at: datetime
    scored_person_count: int = Field(ge=0)
    score_min: float = Field(ge=0, le=1)
    score_max: float = Field(ge=0, le=1)
    score_mean: float = Field(ge=0, le=1)
    demographic_source_verified: bool | None = None


class ScoringStatusResponse(ModelApiResponseModel):
    model_run_id: int = Field(gt=0)
    eligible: bool
    reason: str | None = None
    demographic_source_verified: bool = False
    historical_source_verified: bool = False
    demographic_count: int = Field(ge=0)
    selected_candidate: str | None = None
    artifact_feature_compatible: bool
    feature_contract_version: str | None = None
    feature_contract_sha256: str | None = None
    artifact_sha256: str | None = None
    active_job: JobSummaryResponse | None = None
    completed_scoring_run: CompletedScoringRunReferenceResponse | None = None


class ScoringRunSummaryResponse(ModelApiResponseModel):
    scoring_run_id: int = Field(gt=0)
    job_id: int = Field(gt=0)
    model_run_id: int = Field(gt=0)
    status: ScoringRunStatus
    created_at: datetime
    completed_at: datetime | None = None
    demographic_snapshot_count: int = Field(ge=0)
    scored_person_count: int = Field(ge=0)
    chunk_size: int = Field(ge=1000, le=100000)
    selected_candidate: str
    score_min: float | None = Field(default=None, ge=0, le=1)
    score_max: float | None = Field(default=None, ge=0, le=1)
    score_mean: float | None = Field(default=None, ge=0, le=1)


class ScoringRunIdentityResponse(ModelApiResponseModel):
    scoring_run_id: int = Field(gt=0)
    job_id: int = Field(gt=0)
    model_run_id: int = Field(gt=0)
    status: ScoringRunStatus
    created_at: datetime
    completed_at: datetime | None = None
    failure_message: str | None = None


class ScoringRunPopulationResponse(ModelApiResponseModel):
    demographic_snapshot_count: int = Field(ge=0)
    scored_person_count: int = Field(ge=0)
    chunk_size: int = Field(ge=1000, le=100000)


class ScoringRunModelContractResponse(ModelApiResponseModel):
    selected_candidate: str
    model_role_policy_version: str
    feature_contract_version: str
    feature_contract_sha256: str
    artifact_sha256: str


class ScoringRunScoreSummaryResponse(ModelApiResponseModel):
    score_min: float | None = Field(default=None, ge=0, le=1)
    score_max: float | None = Field(default=None, ge=0, le=1)
    score_mean: float | None = Field(default=None, ge=0, le=1)
    summary_payload: dict[str, Any] | None = None
    demographic_source_verified: bool = False


class ScoringRunDetailResponse(ModelApiResponseModel):
    identity: ScoringRunIdentityResponse
    population: ScoringRunPopulationResponse
    model_contract: ScoringRunModelContractResponse
    score_summary: ScoringRunScoreSummaryResponse
    job: JobSummaryResponse | None = None


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
    is_current: bool = False
    trainability_status: Literal["CURRENT", "STALE"] = "STALE"
    trainability_reason: str | None = None


class ModelTrainingOptionsResponse(ModelApiResponseModel):
    completed_analyses: list[TrainingOptionAnalysisResponse] = Field(max_length=100)
    defaults: dict[str, Any]
    governance: dict[str, Any]
    active_job: JobSummaryResponse | None = None
