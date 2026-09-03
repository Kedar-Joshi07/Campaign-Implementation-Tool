"""Request and response contracts for Phase 7 campaign APIs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.audience import SavedAudienceListItemResponse


CampaignStatus = Literal["DRAFT", "FINALIZED"]
CampaignChannel = Literal["EMAIL", "DIRECT_MAIL"]
CampaignExportStatus = Literal["STARTED", "COMPLETED", "FAILED", "ABORTED"]
CampaignExportCompletionCurrentnessState = Literal["CURRENT", "STALE", "UNKNOWN"]


class CampaignApiResponseModel(BaseModel):
    """Strict campaign response model that rejects extras and non-finite values."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class CampaignOptionsResponse(CampaignApiResponseModel):
    campaign_contract_version: str
    export_contract_version: str
    member_resolution_contract_version: str
    supported_channels: list[CampaignChannel]
    profiles_by_channel: dict[str, str]
    eligible_saved_audiences: list[SavedAudienceListItemResponse] = Field(max_length=100)


class CampaignCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    channel: CampaignChannel
    planned_launch_date: date | None = None
    saved_audience_id: int = Field(gt=0)

    @field_validator("campaign_name", mode="before")
    @classmethod
    def _normalize_name(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("campaign_name must not be blank")
        return normalized

    @field_validator("description", mode="before")
    @classmethod
    def _normalize_description(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None


class CampaignUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    channel: CampaignChannel | None = None
    planned_launch_date: date | None = None
    saved_audience_id: int | None = Field(default=None, gt=0)

    @field_validator("campaign_name", mode="before")
    @classmethod
    def _normalize_name(cls, value: Any) -> Any:
        if value is None or not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("campaign_name must not be blank")
        return normalized

    @field_validator("description", mode="before")
    @classmethod
    def _normalize_description(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def _require_any_field(self) -> "CampaignUpdateRequest":
        if (
            self.campaign_name is None
            and self.description is None
            and self.channel is None
            and self.planned_launch_date is None
            and self.saved_audience_id is None
        ):
            raise ValueError("At least one field must be provided.")
        return self


class CampaignCurrentnessResponse(CampaignApiResponseModel):
    campaign_id: int = Field(gt=0)
    status: CampaignStatus
    is_current: bool
    ready_for_finalize: bool
    ready_for_export: bool
    saved_audience_current: bool
    scoring_current: bool
    historical_source_verified: bool
    demographic_source_verified: bool
    model_verified: bool
    rank_ready: bool
    analytics_ready: bool
    issues: list[str] = Field(default_factory=list, max_length=12)


class CampaignSummaryResponse(CampaignApiResponseModel):
    campaign_id: int = Field(gt=0)
    campaign_name: str
    description: str | None = None
    channel: CampaignChannel
    planned_launch_date: date | None = None
    status: CampaignStatus
    saved_audience_id: int = Field(gt=0)
    saved_audience_resolved_count: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    finalized_at: datetime | None = None
    currentness: CampaignCurrentnessResponse


class CampaignDetailResponse(CampaignApiResponseModel):
    campaign_id: int = Field(gt=0)
    campaign_contract_version: str
    campaign_name: str
    description: str | None = None
    channel: CampaignChannel
    planned_launch_date: date | None = None
    status: CampaignStatus
    saved_audience_id: int = Field(gt=0)
    scoring_run_id: int = Field(gt=0)
    model_run_id: int = Field(gt=0)
    analysis_run_id: int = Field(gt=0)
    saved_audience_filter_hash: str = Field(min_length=64, max_length=64)
    saved_audience_selection: dict[str, Any]
    saved_audience_resolved_count: int = Field(ge=1)
    filter_contract_version: str
    rank_contract_version: str
    selection_contract_version: str
    analytics_contract_version: str
    member_resolution_contract_version: str
    export_contract_version: str
    export_profile: str
    created_at: datetime
    updated_at: datetime
    finalized_at: datetime | None = None
    immutable: bool
    currentness: CampaignCurrentnessResponse


class CampaignFinalizeResponse(CampaignApiResponseModel):
    campaign_id: int = Field(gt=0)
    status: CampaignStatus
    finalized_at: datetime
    currentness: CampaignCurrentnessResponse


class CampaignExportEventResponse(CampaignApiResponseModel):
    export_event_id: int = Field(gt=0)
    campaign_id: int = Field(gt=0)
    export_contract_version: str
    export_snapshot_contract_version: str
    export_profile: str
    status: CampaignExportStatus
    selected_count: int = Field(ge=0)
    deliverable_count: int = Field(ge=0)
    undeliverable_count: int = Field(ge=0)
    row_count: int = Field(ge=0)
    csv_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    start_provenance_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    source_changed_during_export: bool = False
    completion_currentness_state: CampaignExportCompletionCurrentnessState | None = None
    started_at: datetime
    completed_at: datetime | None = None
    safe_error_message: str | None = None


__all__ = (
    "CampaignApiResponseModel",
    "CampaignChannel",
    "CampaignCreateRequest",
    "CampaignCurrentnessResponse",
    "CampaignDetailResponse",
    "CampaignExportEventResponse",
    "CampaignExportCompletionCurrentnessState",
    "CampaignFinalizeResponse",
    "CampaignOptionsResponse",
    "CampaignStatus",
    "CampaignSummaryResponse",
    "CampaignUpdateRequest",
)
