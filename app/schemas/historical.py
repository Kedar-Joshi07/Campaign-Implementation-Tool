"""Typed request and response contracts for Phase 2 historical analysis."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ConversionDefinition = Literal["ATTRIBUTED_PURCHASE", "ANY_PURCHASE", "RESPONSE"]
AnalysisRunStatus = Literal["RUNNING", "COMPLETED", "FAILED"]


class HistoricalResponseModel(BaseModel):
    """Strict public model that also rejects NaN and Infinity."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class HistoricalAnalysisFilters(BaseModel):
    """Request-compatible filters normalized before SQL or persistence."""

    model_config = ConfigDict(extra="forbid")

    analysis_name: str | None = Field(default=None, max_length=120)
    campaign_ids: list[str] = Field(default_factory=list, max_length=25)
    product_ids: list[str] = Field(default_factory=list, max_length=50)
    product_categories: list[str] = Field(default_factory=list, max_length=25)
    campaign_channels: list[str] = Field(default_factory=list, max_length=20)
    campaign_types: list[str] = Field(default_factory=list, max_length=20)
    contact_date_from: date | None = None
    contact_date_to: date | None = None
    contacted_only: bool = True
    conversion_definition: ConversionDefinition = "ATTRIBUTED_PURCHASE"

    @field_validator("analysis_name", mode="before")
    @classmethod
    def normalize_analysis_name(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("analysis_name must not be blank")
        return normalized

    @field_validator(
        "campaign_ids",
        "product_ids",
        "product_categories",
        "campaign_channels",
        "campaign_types",
        mode="before",
    )
    @classmethod
    def normalize_list_values(cls, value: Any) -> Any:
        if value is None:
            return []
        if not isinstance(value, (list, tuple, set)):
            raise ValueError("filter values must be provided as a list")

        normalized: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise ValueError("filter values must be strings")
            trimmed = item.strip()
            if not trimmed:
                raise ValueError("filter values must not be blank")
            normalized.add(trimmed)
        return sorted(normalized, key=lambda item: (item.casefold(), item))

    @model_validator(mode="after")
    def validate_date_order(self) -> HistoricalAnalysisFilters:
        if (
            self.contact_date_from is not None
            and self.contact_date_to is not None
            and self.contact_date_from > self.contact_date_to
        ):
            raise ValueError("contact_date_from must be on or before contact_date_to")
        return self

    def filter_payload(self) -> dict[str, Any]:
        """Return the frozen persisted/API filter shape without the display name."""
        return {
            "campaign_ids": list(self.campaign_ids),
            "product_ids": list(self.product_ids),
            "product_categories": list(self.product_categories),
            "campaign_channels": list(self.campaign_channels),
            "campaign_types": list(self.campaign_types),
            "contact_date_from": (
                self.contact_date_from.isoformat() if self.contact_date_from else None
            ),
            "contact_date_to": (
                self.contact_date_to.isoformat() if self.contact_date_to else None
            ),
            "contacted_only": self.contacted_only,
            "conversion_definition": self.conversion_definition,
        }


class CampaignOptionResponse(HistoricalResponseModel):
    campaign_id: str
    campaign_name: str


class ProductOptionResponse(HistoricalResponseModel):
    product_id: str
    product_name: str
    product_category: str


class ConversionDefinitionResponse(HistoricalResponseModel):
    value: ConversionDefinition
    label: str
    description: str


class HistoricalFilterResponse(HistoricalResponseModel):
    campaign_ids: list[str] = Field(max_length=25)
    product_ids: list[str] = Field(max_length=50)
    product_categories: list[str] = Field(max_length=25)
    campaign_channels: list[str] = Field(max_length=20)
    campaign_types: list[str] = Field(max_length=20)
    contact_date_from: date
    contact_date_to: date
    contacted_only: bool
    conversion_definition: ConversionDefinition


class HistoricalDefaultsResponse(HistoricalResponseModel):
    campaign_ids: list[str] = Field(max_length=25)
    product_ids: list[str] = Field(max_length=50)
    product_categories: list[str] = Field(max_length=25)
    campaign_channels: list[str] = Field(max_length=20)
    campaign_types: list[str] = Field(max_length=20)
    contact_date_from: date | None
    contact_date_to: date | None
    contacted_only: bool
    conversion_definition: ConversionDefinition


class HistoricalOptionsResponse(HistoricalResponseModel):
    available_date_from: date | None
    available_date_to: date | None
    campaigns: list[CampaignOptionResponse] = Field(max_length=250)
    product_categories: list[str] = Field(max_length=100)
    products: list[ProductOptionResponse] = Field(max_length=250)
    campaign_channels: list[str] = Field(max_length=100)
    campaign_types: list[str] = Field(max_length=100)
    conversion_definitions: list[ConversionDefinitionResponse] = Field(max_length=3)
    defaults: HistoricalDefaultsResponse


class HistoricalMetricsResponse(HistoricalResponseModel):
    observation_count: int = Field(ge=0)
    contacted_count: int = Field(ge=0)
    engaged_count: int = Field(ge=0)
    response_count: int = Field(ge=0)
    purchase_count: int = Field(ge=0)
    attributed_purchase_count: int = Field(ge=0)
    net_sales_amount: float
    gross_margin_amount: float
    engagement_rate: float = Field(ge=0, le=1)
    response_rate: float = Field(ge=0, le=1)
    purchase_rate: float = Field(ge=0, le=1)
    attributed_purchase_rate: float = Field(ge=0, le=1)


class HistoricalOverviewSummaryResponse(HistoricalMetricsResponse):
    distinct_customer_count: int = Field(ge=0)
    distinct_campaign_count: int = Field(ge=0)
    distinct_product_count: int = Field(ge=0)
    contact_date_from: date | None
    contact_date_to: date | None


class MonthlyPerformanceResponse(HistoricalMetricsResponse):
    month: str


class LabeledPerformanceResponse(HistoricalMetricsResponse):
    label: str


class CampaignPerformanceResponse(HistoricalMetricsResponse):
    campaign_id: str
    campaign_name: str


class ProductPerformanceResponse(HistoricalMetricsResponse):
    product_id: str
    product_name: str
    product_category: str


class LabelDistributionResponse(HistoricalResponseModel):
    pu_label: Literal[0, 1]
    label: str
    observation_count: int = Field(ge=0)


class HistoricalOverviewResponse(HistoricalResponseModel):
    summary: HistoricalOverviewSummaryResponse
    monthly_trend: list[MonthlyPerformanceResponse] = Field(max_length=120)
    channel_performance: list[LabeledPerformanceResponse] = Field(max_length=10)
    product_category_performance: list[LabeledPerformanceResponse] = Field(max_length=10)
    top_campaigns: list[CampaignPerformanceResponse] = Field(max_length=10)
    top_products: list[ProductPerformanceResponse] = Field(max_length=10)
    label_distribution: list[LabelDistributionResponse] = Field(max_length=2)


class HistoricalAnalysisSummaryResponse(HistoricalResponseModel):
    observation_count: int = Field(ge=0)
    selected_customer_count: int = Field(ge=0)
    positive_customer_count: int = Field(ge=0)
    unlabeled_customer_count: int = Field(ge=0)
    positive_customer_rate: float = Field(ge=0, le=1)
    response_count: int = Field(ge=0)
    purchase_count: int = Field(ge=0)
    attributed_purchase_count: int = Field(ge=0)
    net_sales_amount: float
    gross_margin_amount: float


class ProfileCategoryResponse(HistoricalResponseModel):
    label: str
    count: int = Field(ge=0)
    share: float = Field(ge=0, le=1)


class ProfileDimensionResponse(HistoricalResponseModel):
    group_count: int = Field(ge=0)
    categories: list[ProfileCategoryResponse] = Field(max_length=20)


class ProfileGroupResponse(HistoricalResponseModel):
    age_band: ProfileDimensionResponse
    gender: ProfileDimensionResponse
    state: ProfileDimensionResponse
    individual_income_band: ProfileDimensionResponse
    marital_status: ProfileDimensionResponse
    education: ProfileDimensionResponse
    employment_status: ProfileDimensionResponse
    resident_status: ProfileDimensionResponse
    resident_type: ProfileDimensionResponse
    family_member_count_band: ProfileDimensionResponse
    type_of_employment: ProfileDimensionResponse


class HistoricalProfilesResponse(HistoricalResponseModel):
    selected: ProfileGroupResponse
    positive: ProfileGroupResponse
    unlabeled: ProfileGroupResponse
    historical_baseline: ProfileGroupResponse


class HistoricalAnalysisRunResponse(HistoricalResponseModel):
    analysis_run_id: int = Field(gt=0)
    analysis_name: str = Field(min_length=1, max_length=120)
    created_at: datetime
    completed_at: datetime | None
    status: AnalysisRunStatus
    conversion_definition: ConversionDefinition
    filters: HistoricalFilterResponse
    summary: HistoricalAnalysisSummaryResponse | None = None
    monthly_trend: list[MonthlyPerformanceResponse] | None = Field(
        default=None, max_length=120
    )
    channel_performance: list[LabeledPerformanceResponse] | None = Field(
        default=None, max_length=10
    )
    product_category_performance: list[LabeledPerformanceResponse] | None = Field(
        default=None, max_length=10
    )
    top_campaigns: list[CampaignPerformanceResponse] | None = Field(
        default=None, max_length=10
    )
    top_products: list[ProductPerformanceResponse] | None = Field(
        default=None, max_length=10
    )
    profiles: HistoricalProfilesResponse | None = None
    failure_message: str | None = None


class HistoricalAnalysisListItemResponse(HistoricalResponseModel):
    analysis_run_id: int = Field(gt=0)
    analysis_name: str = Field(min_length=1, max_length=120)
    created_at: datetime
    completed_at: datetime | None
    status: AnalysisRunStatus
    conversion_definition: ConversionDefinition
    filters: HistoricalFilterResponse
    observation_count: int = Field(ge=0)
    selected_customer_count: int = Field(ge=0)
    positive_customer_count: int = Field(ge=0)
    unlabeled_customer_count: int = Field(ge=0)
    positive_customer_rate: float | None = Field(default=None, ge=0, le=1)
    is_current: bool = False
    trainability_status: Literal["CURRENT", "STALE"] = "STALE"
    trainability_reason: str | None = None
    failure_message: str | None = None
