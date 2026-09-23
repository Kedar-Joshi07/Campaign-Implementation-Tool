"""Bounded Phase 11 single-form submission and safe status projections."""
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PotentialCustomerSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    campaign_name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    planned_launch_date: date | None = None
    context: dict[str, Any]
    criteria: dict[str, Any]
    export_profile: str


class Phase11SavedCampaignContext(BaseModel):
    """Exact additive Phase 11 context; legacy CampaignChannel remains frozen."""

    model_config = ConfigDict(extra="forbid")
    product_ids: list[str] = Field(min_length=1, max_length=50)
    campaign_types: list[str] = Field(max_length=50)
    campaign_categories: list[str] = Field(max_length=50)
    offer_types: list[str] = Field(max_length=50)
    campaign_channel: str = Field(min_length=1, max_length=40)
    historical_campaign_channels: list[str] = Field(max_length=50)
    campaign_targeting_context_contract_version: str


class SearchSubmissionStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search_run_id: int = Field(gt=0)
    campaign_name: str
    status: Literal["QUEUED", "PROCESSING", "COMPLETED", "BLOCKED", "FAILED"]
    created_at: str
    completed_at: str | None
    selected_count: int | None
    delivery_channel: str
    export_profile: str
    safe_message: str


class SearchRunProgress(BaseModel):
    """Durable lifecycle facts and a bounded, qualified completion estimate."""

    model_config = ConfigDict(extra="forbid")
    contract_version: Literal["1"]
    lifecycle_status: Literal[
        "QUEUED", "PROCESSING", "PAUSE_REQUESTED", "PAUSED",
        "STOP_REQUESTED", "STOPPED", "RESTART_REQUESTED",
        "COMPLETED", "BLOCKED", "FAILED",
    ]
    stage_code: str = Field(min_length=1, max_length=80)
    stage_label: str = Field(min_length=1, max_length=200)
    progress_percent: int = Field(ge=0, le=100)
    processed_count: int = Field(ge=0)
    total_count: int | None = Field(default=None, ge=0)
    progress_unit: str = Field(min_length=1, max_length=40)
    status_message: str = Field(min_length=1, max_length=1000)
    updated_at: str
    heartbeat_at: str | None
    state_version: int = Field(ge=1)
    estimated_seconds_remaining_low: int | None = Field(default=None, ge=0)
    estimated_seconds_remaining_high: int | None = Field(default=None, ge=0)
    estimated_completion_at: str | None
    estimate_confidence: Literal["UNAVAILABLE", "LOW", "MEDIUM", "HIGH"]
    estimate_basis: str = Field(min_length=1, max_length=80)


class SearchRunIssue(BaseModel):
    """Safe reason and recovery guidance for a blocked or failed search."""

    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=1000)
    resolution_steps: list[str] = Field(min_length=1, max_length=8)
    retryable: bool


class SearchResultProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: str
    product_name: str
    product_category: str


class SearchResultHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    search_run_id: int = Field(gt=0)
    campaign_name: str
    created_at: str
    completed_at: str | None
    status: Literal["QUEUED", "PROCESSING", "COMPLETED", "BLOCKED", "FAILED"]
    selected_products: list[SearchResultProduct] = Field(max_length=50)
    campaign_types: list[str] = Field(max_length=50)
    campaign_categories: list[str] = Field(max_length=50)
    offer_types: list[str] = Field(max_length=50)
    delivery_channel: str
    export_profile: str
    delivery_profile_label: str
    match_strength: str
    targeting_summary: list[str] = Field(max_length=20)
    selected_count: int | None = Field(default=None, ge=0)
    result_source: str | None
    result_source_label: str
    processing_seconds: float | None = Field(default=None, ge=0)
    currentness: Literal["CURRENT", "STALE", "UNVERIFIED", "NOT_AVAILABLE"]
    download_eligible: bool
    safe_message: str
    progress: SearchRunProgress
    issue: SearchRunIssue | None = None


class SearchResultDetail(SearchResultHistoryItem):
    description: str | None
    planned_launch_date: str | None
    campaign_context: dict[str, Any]
    targeting_criteria: dict[str, Any]
    filter_branches: list[dict[str, Any]] = Field(min_length=1, max_length=49)
    selection: dict[str, Any]
    result_source_explanation: str
    score_summary: dict[str, Any] | None
    demographic_summary: dict[str, Any]
    snapshot_provenance: dict[str, Any] | None
    technical_details: dict[str, Any]
