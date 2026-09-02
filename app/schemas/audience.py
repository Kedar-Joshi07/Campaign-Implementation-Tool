"""Typed request/response contracts for Phase 6 audience preparation APIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.models import JobSummaryResponse


class AudienceApiResponseModel(BaseModel):
    """Strict response model that forbids extras and non-finite numbers."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class AudiencePreparationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank_contract_version: str = Field(default="1", min_length=1, max_length=24)


class AudiencePreparationSubmitResponse(JobSummaryResponse):
    """Queued/running/completed job envelope for preparation submission."""


class AudiencePreparationStatusResponse(AudienceApiResponseModel):
    scoring_run_id: int = Field(gt=0)
    model_run_id: int = Field(gt=0)
    status: str
    rank_contract_version: str
    prepared: bool
    is_canonical: bool
    source_verified: bool
    ready_for_current_audience_actions: bool
    currentness_issues: list[str] = Field(default_factory=list, max_length=5)
    boundary_count: int = Field(ge=0, le=100)
    total_population: int = Field(ge=0)
    active_job: JobSummaryResponse | None = None


class AudiencePreparationRunSummaryResponse(AudienceApiResponseModel):
    scoring_run_id: int = Field(gt=0)
    model_run_id: int = Field(gt=0)
    completed_at: datetime | None = None
    scored_person_count: int = Field(ge=0)
    prepared: bool
    is_canonical: bool
    source_verified: bool
    ready_for_current_audience_actions: bool
    currentness_issues: list[str] = Field(default_factory=list, max_length=5)
    rank_contract_version: str | None = None
    boundary_count: int = Field(ge=0, le=100)
    analytics_prepared: bool | None = None
    analytics_contract_version: str | None = None
    analytics_snapshot_created_at: datetime | None = None


class AudienceFilterOptionsCategoryValueResponse(AudienceApiResponseModel):
    value: str
    count: int = Field(ge=0)


class AudienceFilterOptionsRangeValueResponse(AudienceApiResponseModel):
    min: float | int | None = None
    max: float | int | None = None


class AudienceFilterOptionsResponse(AudienceApiResponseModel):
    scoring_run_id: int = Field(gt=0)
    filter_contract_version: str
    rank_contract_version: str
    selection_contract_version: str
    source_verified: bool
    population_count: int = Field(ge=0)
    score_summary: dict[str, float]
    numeric_ranges: dict[str, AudienceFilterOptionsRangeValueResponse]
    categorical_options: dict[str, list[AudienceFilterOptionsCategoryValueResponse]]
    rank_definitions: dict[str, object]
    pii_policy: dict[str, object]
    score_semantics: dict[str, object]


class AudienceSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = Field(default="ALL_MATCHING", min_length=1, max_length=24)
    target_count: int | None = Field(default=None, gt=0)


class AudienceEstimateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scoring_run_id: int = Field(gt=0)
    filters: dict[str, object] = Field(default_factory=dict)
    selection: AudienceSelectionRequest = Field(default_factory=AudienceSelectionRequest)


class AudienceEstimateResponse(AudienceApiResponseModel):
    scoring_run_id: int = Field(gt=0)
    filter_contract_version: str
    selection_contract_version: str
    filter_hash: str = Field(min_length=64, max_length=64)
    normalized_filters: dict[str, object]
    selection: dict[str, object]
    matching_count: int = Field(ge=0)
    selected_count: int = Field(ge=0)
    score_min: float | None = Field(default=None, ge=0, le=1)
    score_mean: float | None = Field(default=None, ge=0, le=1)
    score_max: float | None = Field(default=None, ge=0, le=1)
    source_verified: bool


class AudienceSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scoring_run_id: int = Field(gt=0)
    filters: dict[str, object] = Field(default_factory=dict)
    page_size: int = Field(default=50, ge=1, le=100)
    cursor: str | None = Field(default=None, min_length=1, max_length=512)


class AudienceSearchRowResponse(AudienceApiResponseModel):
    person_id: str
    propensity_score: float = Field(ge=0, le=1)
    age: int = Field(ge=0)
    gender: str | None = None
    state: str
    individual_yearly_income: float = Field(ge=0)
    marital_status: str | None = None
    education: str | None = None
    employment_status: str | None = None
    resident_status: str | None = None
    resident_type: str | None = None
    family_member_count: int = Field(ge=1)
    type_of_employment: str | None = None
    percentile_bucket: int = Field(ge=1, le=100)
    decile: int = Field(ge=1, le=10)
    rank_band: str


class AudienceSearchResponse(AudienceApiResponseModel):
    scoring_run_id: int = Field(gt=0)
    rank_contract_version: str
    filter_hash: str = Field(min_length=64, max_length=64)
    rows: list[AudienceSearchRowResponse]
    next_cursor: str | None = None
    has_more: bool
    score_semantics: dict[str, object]


class AudienceProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scoring_run_id: int = Field(gt=0)
    filters: dict[str, object] = Field(default_factory=dict)
    selection: AudienceSelectionRequest = Field(default_factory=AudienceSelectionRequest)


class AudienceProfileSummaryGroupResponse(AudienceApiResponseModel):
    count: int = Field(ge=0)
    age_mean: float | None = None
    individual_yearly_income_mean: float | None = None
    family_member_count_mean: float | None = None
    score_min: float | None = Field(default=None, ge=0, le=1)
    score_mean: float | None = Field(default=None, ge=0, le=1)
    score_max: float | None = Field(default=None, ge=0, le=1)


class AudienceProfileDistributionCategoryResponse(AudienceApiResponseModel):
    category: str
    count: int = Field(ge=0)
    share: float = Field(ge=0, le=1)


class AudienceProfileComparisonCategoryResponse(AudienceApiResponseModel):
    category: str
    selected_share: float = Field(ge=0, le=1)
    reference_share: float = Field(ge=0, le=1)
    share_point_difference: float
    index: float | None = None


class AudienceProfileTraitResponse(AudienceApiResponseModel):
    comparison: str
    dimension: str
    category: str
    selected_share: float = Field(ge=0, le=1)
    reference_share: float = Field(ge=0, le=1)
    share_point_difference: float
    index: float = Field(gt=1)


class AudienceProfileResponse(AudienceApiResponseModel):
    scoring_run_id: int = Field(gt=0)
    filter_contract_version: str
    selection_contract_version: str
    rank_contract_version: str
    filter_hash: str = Field(min_length=64, max_length=64)
    selection: dict[str, object]
    source_verified: bool
    historical_reference_date: str
    summary: dict[str, AudienceProfileSummaryGroupResponse]
    distributions: dict[str, dict[str, list[AudienceProfileDistributionCategoryResponse]]]
    comparisons: dict[str, dict[str, list[AudienceProfileComparisonCategoryResponse]]]
    top_overindexed_traits: list[AudienceProfileTraitResponse]


class SavedAudienceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audience_name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    scoring_run_id: int = Field(gt=0)
    filters: dict[str, object] = Field(default_factory=dict)
    selection: AudienceSelectionRequest = Field(default_factory=AudienceSelectionRequest)
    include_profile_snapshot: bool = True


class SavedAudienceCurrentnessResponse(AudienceApiResponseModel):
    audience_id: int = Field(gt=0)
    is_current: bool
    issues: list[str]


class SavedAudienceListItemResponse(AudienceApiResponseModel):
    audience_id: int = Field(gt=0)
    audience_name: str
    description: str | None = None
    created_at: datetime
    selection_mode: str
    target_count: int | None = Field(default=None, ge=1)
    resolved_count: int = Field(ge=1)
    scoring_run_id: int = Field(gt=0)
    model_run_id: int = Field(gt=0)
    is_current: bool
    stale_reason: str | None = None


class SavedAudienceDefinitionResponse(AudienceApiResponseModel):
    scoring_run_id: int = Field(gt=0)
    filters: dict[str, object]
    selection: dict[str, object]
    selection_mode: str
    target_count: int | None = Field(default=None, ge=1)
    resolved_count: int = Field(ge=1)
    filters_json: str
    selection_json: str


class SavedAudienceProvenanceResponse(AudienceApiResponseModel):
    scoring_run_id: int = Field(gt=0)
    model_run_id: int = Field(gt=0)
    analysis_run_id: int = Field(gt=0)
    customer_import_id: int = Field(gt=0)
    customer_source_checksum: str = Field(min_length=64, max_length=64)
    campaign_sales_import_id: int = Field(gt=0)
    campaign_sales_source_checksum: str = Field(min_length=64, max_length=64)
    demographic_import_id: int = Field(gt=0)
    demographic_source_checksum: str = Field(min_length=64, max_length=64)
    feature_contract_version: str
    feature_contract_sha256: str = Field(min_length=64, max_length=64)
    artifact_sha256: str = Field(min_length=64, max_length=64)


class SavedAudienceDetailResponse(AudienceApiResponseModel):
    audience_id: int = Field(gt=0)
    audience_name: str
    description: str | None = None
    created_at: datetime
    definition: SavedAudienceDefinitionResponse
    contracts: dict[str, str]
    provenance: SavedAudienceProvenanceResponse
    profile_snapshot: dict[str, object] | None = None
    currentness: SavedAudienceCurrentnessResponse
    score_semantics: dict[str, object]
    pii_policy: dict[str, object]
    export_policy: dict[str, object]
    replay_request: dict[str, object]
