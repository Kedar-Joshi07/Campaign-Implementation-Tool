"""Versioned Phase 9 campaign-context and business-targeting contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.campaigns import CampaignChannel, CampaignDetailResponse


TARGETING_SEGMENT_CONTRACT_VERSION = "1"
CAMPAIGN_TARGETING_CONTEXT_CONTRACT_VERSION = "1"
BUSINESS_MATCH_STRENGTH_CONTRACT_VERSION = "1"
AGE_BUCKET_CONTRACT_VERSION = "1"
INCOME_GROUP_CONTRACT_VERSION = "1"

BusinessMatchStrength = Literal["VERY_STRONG", "STRONG", "GOOD", "BROAD"]
AgeBucketValue = Literal["18-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75+"]
IncomeGroupValue = Literal[
    "<25K",
    "25K-49,999",
    "50K-74,999",
    "75K-99,999",
    "100K-149,999",
    "150K-249,999",
    "250K+",
]
SelectionMode = Literal["ALL_MATCHING", "TOP_N"]
TargetingIntelligenceStatus = Literal[
    "READY",
    "NEEDS_REFRESH",
    "NOT_AVAILABLE",
    "INCOMPATIBLE_CONTEXT",
    "STALE",
]
MatchStrengthRelationship = Literal["NARROWER", "CURRENT", "BROADER"]
MatchStrengthRecommendationStatus = Literal["RECOMMENDED", "REVIEW_REQUIRED"]
MatchStrengthRecommendationReason = Literal[
    "VERY_STRONG_USABLE",
    "STRONG_USABLE",
    "GOOD_USABLE",
    "BROAD_ONLY_USABLE",
    "ALL_TOO_SMALL",
]

DEFAULT_MATCH_STRENGTH: BusinessMatchStrength = "GOOD"

MATCH_STRENGTH_THRESHOLDS: dict[BusinessMatchStrength, float] = {
    "VERY_STRONG": 0.90,
    "STRONG": 0.80,
    "GOOD": 0.70,
    "BROAD": 0.60,
}


@dataclass(frozen=True)
class NumericBand:
    """Ordered server-owned numeric band definition."""

    value: str
    label: str
    minimum: float
    maximum: float | None
    maximum_inclusive: bool = True


MATCH_SCORE_BANDS = (
    NumericBand("VERY_STRONG", "0.90–1.00", 0.90, 1.00),
    NumericBand("STRONG", "0.80–<0.90", 0.80, 0.90, False),
    NumericBand("GOOD", "0.70–<0.80", 0.70, 0.80, False),
    NumericBand("BROAD", "0.60–<0.70", 0.60, 0.70, False),
    NumericBand("BELOW_BROAD", "0.00–<0.60", 0.00, 0.60, False),
)

AGE_BUCKETS = (
    NumericBand("18-24", "18–24", 18, 24),
    NumericBand("25-34", "25–34", 25, 34),
    NumericBand("35-44", "35–44", 35, 44),
    NumericBand("45-54", "45–54", 45, 54),
    NumericBand("55-64", "55–64", 55, 64),
    NumericBand("65-74", "65–74", 65, 74),
    NumericBand("75+", "75+", 75, 100),
)

INCOME_GROUPS = (
    NumericBand("<25K", "<25K", 0, 24_999),
    NumericBand("25K-49,999", "25K–49,999", 25_000, 49_999),
    NumericBand("50K-74,999", "50K–74,999", 50_000, 74_999),
    NumericBand("75K-99,999", "75K–99,999", 75_000, 99_999),
    NumericBand("100K-149,999", "100K–149,999", 100_000, 149_999),
    NumericBand("150K-249,999", "150K–249,999", 150_000, 249_999),
    NumericBand("250K+", "250K+", 250_000, None),
)


def _normalize_string_list(value: Any) -> Any:
    if value is None:
        return []
    if not isinstance(value, (list, tuple, set)):
        raise ValueError("values must be provided as a list")
    normalized: dict[str, str] = {}
    for item in value:
        if not isinstance(item, str):
            raise ValueError("values must be strings")
        text = item.strip()
        if not text:
            raise ValueError("values must not be blank")
        normalized.setdefault(text.casefold(), text)
    return sorted(normalized.values(), key=lambda item: (item.casefold(), item))


def _normalize_ordered_values(value: Any, *, order: tuple[str, ...]) -> Any:
    normalized = _normalize_string_list(value)
    known = set(order)
    unsupported = sorted(item for item in normalized if item not in known)
    if unsupported:
        raise ValueError(f"unsupported values: {', '.join(unsupported)}")
    selected = set(normalized)
    return [item for item in order if item in selected]


class CampaignTargetingContextContract(BaseModel):
    """Canonical business context for one campaign-planning session."""

    model_config = ConfigDict(extra="forbid")

    product_ids: list[str] = Field(min_length=1, max_length=50)
    campaign_types: list[str] = Field(default_factory=list, max_length=50)
    campaign_categories: list[str] = Field(default_factory=list, max_length=50)
    offer_types: list[str] = Field(default_factory=list, max_length=50)
    campaign_channel: CampaignChannel
    historical_campaign_channels: list[str] = Field(default_factory=list, max_length=50)

    @field_validator(
        "product_ids",
        "campaign_types",
        "campaign_categories",
        "offer_types",
        "historical_campaign_channels",
        mode="before",
    )
    @classmethod
    def _normalize_multi_selects(cls, value: Any) -> Any:
        return _normalize_string_list(value)

    @field_validator("campaign_channel", mode="before")
    @classmethod
    def _normalize_campaign_channel(cls, value: Any) -> Any:
        return value.strip().upper() if isinstance(value, str) else value


class CampaignContextProductOption(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    product_id: str
    product_name: str
    product_category: str


class CampaignContextDeliveryChannelOption(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    value: CampaignChannel
    label: str


class CampaignContextOptionsResponse(BaseModel):
    """Current backend-owned choices for the campaign-context form."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    campaign_targeting_context_contract_version: str
    products: list[CampaignContextProductOption] = Field(max_length=250)
    campaign_types: list[str] = Field(max_length=100)
    campaign_categories: list[str] = Field(max_length=100)
    offer_types: list[str] = Field(max_length=100)
    delivery_channels: list[CampaignContextDeliveryChannelOption] = Field(max_length=10)
    historical_campaign_channels: list[str] = Field(max_length=100)


class CampaignContextSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: dict[str, Any]


class CanonicalCampaignTargetingContext(CampaignTargetingContextContract):
    campaign_targeting_context_contract_version: str


class CampaignContextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    targeting_context_id: int = Field(gt=0)
    campaign_id: int | None = Field(default=None, gt=0)
    campaign_targeting_context_contract_version: str
    targeting_segment_contract_version: str
    business_match_strength_contract_version: str
    context: CanonicalCampaignTargetingContext
    campaign_context_sha256: str = Field(min_length=64, max_length=64)
    source_scoring_run_id: int | None = Field(default=None, gt=0)
    created_at: datetime
    updated_at: datetime


class BusinessTargetingCriteriaContract(BaseModel):
    """Business controls with deterministic Audience Filter Contract mapping."""

    model_config = ConfigDict(extra="forbid")

    match_strength: BusinessMatchStrength = DEFAULT_MATCH_STRENGTH
    genders: list[str] = Field(default_factory=list, max_length=100)
    age_groups: list[AgeBucketValue] = Field(default_factory=list, max_length=len(AGE_BUCKETS))
    states: list[str] = Field(default_factory=list, max_length=100)
    income_groups: list[IncomeGroupValue] = Field(
        default_factory=list, max_length=len(INCOME_GROUPS)
    )
    marital_statuses: list[str] = Field(default_factory=list, max_length=100)
    education_levels: list[str] = Field(default_factory=list, max_length=100)
    employment_statuses: list[str] = Field(default_factory=list, max_length=100)
    resident_statuses: list[str] = Field(default_factory=list, max_length=100)
    resident_types: list[str] = Field(default_factory=list, max_length=100)
    employment_types: list[str] = Field(default_factory=list, max_length=100)
    family_member_count_min: int | None = Field(default=None, ge=1)
    family_member_count_max: int | None = Field(default=None, ge=1)
    top_matching_percent: int | None = Field(default=None, ge=1, le=100)
    selection_mode: SelectionMode = "ALL_MATCHING"
    target_count: int | None = Field(default=None, gt=0)

    @field_validator(
        "genders",
        "states",
        "marital_statuses",
        "education_levels",
        "employment_statuses",
        "resident_statuses",
        "resident_types",
        "employment_types",
        mode="before",
    )
    @classmethod
    def _normalize_dynamic_multi_selects(cls, value: Any) -> Any:
        return _normalize_string_list(value)

    @field_validator("age_groups", mode="before")
    @classmethod
    def _normalize_age_groups(cls, value: Any) -> Any:
        return _normalize_ordered_values(
            value,
            order=tuple(band.value for band in AGE_BUCKETS),
        )

    @field_validator("income_groups", mode="before")
    @classmethod
    def _normalize_income_groups(cls, value: Any) -> Any:
        return _normalize_ordered_values(
            value,
            order=tuple(band.value for band in INCOME_GROUPS),
        )

    @field_validator("match_strength", mode="before")
    @classmethod
    def _normalize_match_strength(cls, value: Any) -> Any:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("selection_mode", mode="before")
    @classmethod
    def _normalize_selection_mode(cls, value: Any) -> Any:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _validate_ranges_and_selection(self) -> "BusinessTargetingCriteriaContract":
        if (
            self.family_member_count_min is not None
            and self.family_member_count_max is not None
            and self.family_member_count_min > self.family_member_count_max
        ):
            raise ValueError(
                "family_member_count_min cannot exceed family_member_count_max"
            )
        if self.selection_mode == "TOP_N" and self.target_count is None:
            raise ValueError("target_count is required when selection_mode is TOP_N")
        if self.selection_mode == "ALL_MATCHING" and self.target_count is not None:
            raise ValueError(
                "target_count must be null when selection_mode is ALL_MATCHING"
            )
        return self


class TargetingStrengthOption(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    value: BusinessMatchStrength
    label: str
    minimum_score: float = Field(ge=0, le=1)
    recommended: bool


class TargetingNumericBucketOption(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    value: str
    label: str
    minimum: float = Field(ge=0)
    maximum: float | None = Field(default=None, ge=0)
    maximum_inclusive: bool


class TargetingRegionOption(BaseModel):
    """Backend-owned coarse region that expands to current State values."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    value: str
    label: str
    states: list[str] = Field(min_length=1, max_length=100)


class BusinessTargetingOptionsResponse(BaseModel):
    """Backend-owned business controls and current categorical values."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    targeting_segment_contract_version: str
    business_match_strength_contract_version: str
    age_bucket_contract_version: str
    income_group_contract_version: str
    default_match_strength: BusinessMatchStrength
    match_strengths: list[TargetingStrengthOption] = Field(min_length=4, max_length=4)
    age_groups: list[TargetingNumericBucketOption] = Field(
        min_length=len(AGE_BUCKETS), max_length=len(AGE_BUCKETS)
    )
    income_groups: list[TargetingNumericBucketOption] = Field(
        min_length=len(INCOME_GROUPS), max_length=len(INCOME_GROUPS)
    )
    genders: list[str] = Field(max_length=100)
    states: list[str] = Field(max_length=100)
    regions: list[TargetingRegionOption] = Field(max_length=10)
    marital_statuses: list[str] = Field(max_length=100)
    education_levels: list[str] = Field(max_length=100)
    employment_statuses: list[str] = Field(max_length=100)
    resident_statuses: list[str] = Field(max_length=100)
    resident_types: list[str] = Field(max_length=100)
    employment_types: list[str] = Field(max_length=100)
    family_size_minimum: int | None = Field(default=None, ge=1)
    family_size_maximum: int | None = Field(default=None, ge=1)


class BusinessTargetingCriteriaSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: dict[str, Any]


class CanonicalBusinessTargetingCriteria(BusinessTargetingCriteriaContract):
    targeting_segment_contract_version: str
    business_match_strength_contract_version: str
    age_bucket_contract_version: str
    income_group_contract_version: str
    audience_filter_contract_version: str


class BusinessTargetingCriteriaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    targeting_context_id: int = Field(gt=0)
    targeting_segment_contract_version: str
    business_match_strength_contract_version: str
    criteria: CanonicalBusinessTargetingCriteria
    targeting_criteria_sha256: str = Field(min_length=64, max_length=64)
    audience_filter_branches: list[dict[str, Any]] = Field(min_length=1, max_length=49)
    audience_selection: dict[str, Any]
    source_scoring_run_id: int | None = Field(default=None, gt=0)
    updated_at: datetime


class TargetingIntelligenceLinkRequest(BaseModel):
    """Advanced analyst/admin request; never exposed as a normal-user selector."""

    model_config = ConfigDict(extra="forbid")

    scoring_run_id: int = Field(gt=0)


class TargetingIntelligenceTechnicalDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    analysis_run_id: int | None = Field(default=None, gt=0)
    model_run_id: int | None = Field(default=None, gt=0)
    scoring_run_id: int | None = Field(default=None, gt=0)
    selected_candidate: str | None = None
    model_role_policy_version: str | None = None
    feature_contract_version: str | None = None
    feature_contract_sha256: str | None = None
    artifact_sha256: str | None = None
    customer_source_checksum: str | None = None
    campaign_sales_source_checksum: str | None = None
    demographic_source_checksum: str | None = None


class Phase9TechnicalDetailsResponse(TargetingIntelligenceTechnicalDetails):
    """Audit-only values rendered exclusively inside collapsed technical details."""

    source_status: TargetingIntelligenceStatus
    source_currentness: Literal["UP_TO_DATE", "NEEDS_REFRESH"]
    audience_filter_hash: str = Field(min_length=64, max_length=64)
    saved_audience_id: int | None = Field(default=None, gt=0)
    targeting_intelligence_resolution_contract_version: str
    campaign_targeting_context_contract_version: str
    targeting_segment_contract_version: str
    business_match_strength_contract_version: str
    audience_filter_contract_version: str
    target_group_preview_contract_version: str
    target_group_campaign_contract_version: str | None = None
    saved_target_group_contract_version: str | None = None


class TargetingIntelligenceResolutionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    targeting_intelligence_resolution_contract_version: str
    targeting_context_id: int = Field(gt=0)
    status: TargetingIntelligenceStatus
    message: str
    explanation: str
    explicitly_linked: bool
    can_preview: bool
    context_specific: bool
    context_changed_source: Literal[False]
    compatibility_checked_dimensions: list[str] = Field(max_length=3)
    issues: list[str] = Field(max_length=20)
    technical_details: TargetingIntelligenceTechnicalDetails | None = None


class TargetGroupKpiResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    potential_customers_available: int = Field(ge=0)
    matching_your_preferences: int = Field(ge=0)
    selected_for_target_group: int = Field(ge=0)
    percent_of_available_people: float = Field(ge=0, le=100)
    average_targeting_match_score: float | None = Field(default=None, ge=0, le=1)
    strongest_match: float | None = Field(default=None, ge=0, le=1)
    lowest_selected_match: float | None = Field(default=None, ge=0, le=1)


class TargetGroupDistributionItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    category: str
    count: int = Field(ge=0)
    share: float = Field(ge=0, le=1)


class TargetGroupPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    target_group_preview_contract_version: str
    targeting_context_id: int = Field(gt=0)
    currentness: Literal["UP_TO_DATE"]
    currentness_label: Literal["Up to date"]
    kpis: TargetGroupKpiResponse
    targeting_match_score_distribution: list[TargetGroupDistributionItemResponse] = Field(
        min_length=5, max_length=5
    )
    demographic_mix: dict[str, list[TargetGroupDistributionItemResponse]]
    why_these_people: str
    technical_details: Phase9TechnicalDetailsResponse


class TargetGroupSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_size: int = Field(default=25, ge=1, le=100)
    cursor: str | None = Field(default=None, min_length=1, max_length=1024)


class TargetGroupSearchRowResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    potential_customer_id: str
    targeting_match_score: float = Field(ge=0, le=1)
    top_matching_percent: int = Field(ge=1, le=100)
    match_strength: str
    age: int = Field(ge=0, le=120)
    gender: str
    state: str
    individual_yearly_income: float = Field(ge=0)
    marital_status: str
    education: str
    employment_status: str
    resident_status: str
    resident_type: str
    family_member_count: int = Field(ge=1)
    type_of_employment: str


class TargetGroupSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    target_group_preview_contract_version: str
    targeting_context_id: int = Field(gt=0)
    currentness: Literal["UP_TO_DATE"]
    rows: list[TargetGroupSearchRowResponse] = Field(max_length=100)
    next_cursor: str | None = None
    has_more: bool


class MatchStrengthComparisonItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    match_strength: BusinessMatchStrength
    label: str
    minimum_score: float = Field(ge=0, le=1)
    exact_matching_count: int = Field(ge=0)
    percent_of_available_population: float = Field(ge=0, le=100)
    change_from_current: int
    relationship_to_current: MatchStrengthRelationship
    recommended: bool


class MatchStrengthRecommendationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    match_strength_recommendation_contract_version: str
    recommendation_rule_version: str
    targeting_context_id: int = Field(gt=0)
    currentness: Literal["UP_TO_DATE"]
    current_match_strength: BusinessMatchStrength
    practical_minimum_count: int = Field(gt=0)
    very_strong_minimum_multiplier: float = Field(gt=0)
    very_strong_minimum_count: int = Field(gt=0)
    recommendation_status: MatchStrengthRecommendationStatus
    recommendation_reason: MatchStrengthRecommendationReason
    recommended_match_strength: BusinessMatchStrength | None = None
    recommendation_heading: str
    recommendation_explanation: str
    disclaimer: str
    comparisons: list[MatchStrengthComparisonItemResponse] = Field(
        min_length=4, max_length=4
    )


class SaveTargetGroupCampaignDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_group_name: str = Field(min_length=1, max_length=120)
    target_group_description: str | None = Field(default=None, max_length=500)
    campaign_name: str = Field(min_length=1, max_length=120)
    campaign_description: str | None = Field(default=None, max_length=500)
    planned_launch_date: date | None = None

    @field_validator("target_group_name", "campaign_name", mode="before")
    @classmethod
    def _normalize_required_names(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized

    @field_validator(
        "target_group_description", "campaign_description", mode="before"
    )
    @classmethod
    def _normalize_optional_descriptions(cls, value: Any) -> Any:
        if value is None or not isinstance(value, str):
            return value
        return value.strip() or None


class SavedTargetGroupSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    saved_target_group_id: int = Field(gt=0)
    name: str
    description: str | None = None
    selected_count: int = Field(gt=0)
    filter_hash: str = Field(min_length=64, max_length=64)
    filter_branch_count: int = Field(gt=0, le=49)
    immutable: Literal[True]
    currentness: Literal["UP_TO_DATE", "NEEDS_REFRESH"]
    currentness_label: Literal["Up to date", "Needs refresh"]
    created_at: datetime


class Phase9CampaignDraftResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    target_group_campaign_contract_version: str
    targeting_context_id: int = Field(gt=0)
    campaign_created: bool
    idempotent_replay: bool
    targeting_source_status: TargetingIntelligenceStatus
    campaign_context: CanonicalCampaignTargetingContext
    targeting_criteria: CanonicalBusinessTargetingCriteria
    saved_target_group: SavedTargetGroupSummaryResponse
    campaign: CampaignDetailResponse
    technical_details: Phase9TechnicalDetailsResponse


__all__ = (
    "AGE_BUCKET_CONTRACT_VERSION",
    "AGE_BUCKETS",
    "BUSINESS_MATCH_STRENGTH_CONTRACT_VERSION",
    "BusinessMatchStrength",
    "BusinessTargetingCriteriaResponse",
    "BusinessTargetingCriteriaSaveRequest",
    "BusinessTargetingCriteriaContract",
    "BusinessTargetingOptionsResponse",
    "CampaignContextDeliveryChannelOption",
    "CampaignContextOptionsResponse",
    "CampaignContextProductOption",
    "CampaignContextResponse",
    "CampaignContextSaveRequest",
    "CAMPAIGN_TARGETING_CONTEXT_CONTRACT_VERSION",
    "CanonicalCampaignTargetingContext",
    "CanonicalBusinessTargetingCriteria",
    "CampaignTargetingContextContract",
    "DEFAULT_MATCH_STRENGTH",
    "INCOME_GROUP_CONTRACT_VERSION",
    "INCOME_GROUPS",
    "MATCH_SCORE_BANDS",
    "MATCH_STRENGTH_THRESHOLDS",
    "MatchStrengthComparisonItemResponse",
    "MatchStrengthRecommendationResponse",
    "Phase9CampaignDraftResponse",
    "Phase9TechnicalDetailsResponse",
    "NumericBand",
    "TARGETING_SEGMENT_CONTRACT_VERSION",
    "TargetingNumericBucketOption",
    "TargetingRegionOption",
    "TargetingIntelligenceLinkRequest",
    "TargetingIntelligenceResolutionResponse",
    "TargetingIntelligenceStatus",
    "TargetingIntelligenceTechnicalDetails",
    "TargetingStrengthOption",
    "TargetGroupDistributionItemResponse",
    "TargetGroupKpiResponse",
    "TargetGroupPreviewResponse",
    "TargetGroupSearchRequest",
    "TargetGroupSearchResponse",
    "TargetGroupSearchRowResponse",
    "SaveTargetGroupCampaignDraftRequest",
    "SavedTargetGroupSummaryResponse",
)
