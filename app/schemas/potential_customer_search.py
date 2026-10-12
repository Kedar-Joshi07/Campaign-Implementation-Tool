"""Bounded Phase 11 single-form submission and safe status projections."""
from datetime import date
from typing import Any, Literal

import math

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.selection_contracts import PropensityBucket


# Documentation-only example from Prompt 17's disposable canonical context.
# Operators must fetch the current catalog_version and export profile from
# /api/potential-customer-search/options?include_similarity=true.
_V3_OPENAPI_PREFLIGHT_EXAMPLE = {
    "selection_contract_version": "3",
    "score_semantics": "PRODUCT_BUYER_SIMILARITY",
    "similarity_minimum": 0.90,
    "context": {
        "campaign_channel": "EMAIL",
        "product_ids": ["PRD001", "PRD003", "PRD004"],
        "campaign_types": [], "campaign_categories": [],
        "offer_types": [], "historical_campaign_channels": [],
    },
    "criteria": {
        "age_groups": ["25-34", "35-44", "45-54", "55-64"],
        "income_groups": ["25K-49,999", "50K-74,999", "75K-99,999", "100K-149,999"],
        "genders": [], "states": [], "marital_statuses": [],
        "education_levels": [], "employment_statuses": [],
        "resident_statuses": [], "resident_types": [],
        "employment_types": [], "family_member_count_min": None,
        "family_member_count_max": None,
    },
    "selection_mode": "ALL_MATCHING",
    "top_n": None,
    "catalog_version": "0e40a88ad6a43c9d808dcc21533bc5466eeafe804cb3f0d4a1378b1d2420f26d",
}


def _validate_similarity_minimum(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, float) or not math.isfinite(value):
        raise ValueError("similarity_minimum must be a finite JSON decimal.")
    if value not in {0.50, 0.60, 0.70, 0.80, 0.90}:
        raise ValueError("Choose a supported buyer similarity minimum.")
    return value


class PotentialCustomerSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    campaign_name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    planned_launch_date: date | None = None
    context: dict[str, Any]
    criteria: dict[str, Any]
    export_profile: str
    propensity_bucket: PropensityBucket | None = None
    catalog_version: str | None = Field(default=None, min_length=64, max_length=64)


class PotentialCustomerSearchV3Request(BaseModel):
    """Explicit product-buyer-similarity request; never inferred from legacy fields."""

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, allow_inf_nan=False,
        json_schema_extra={"examples": [{
            **_V3_OPENAPI_PREFLIGHT_EXAMPLE,
            "campaign_name": "Illustrative buyer-similarity search",
            "export_profile": "EMAIL_CONTACT_V2",
        }]},
    )
    selection_contract_version: Literal["3"]
    score_semantics: Literal["PRODUCT_BUYER_SIMILARITY"]
    similarity_minimum: float
    campaign_name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    planned_launch_date: date | None = None
    context: dict[str, Any]
    criteria: dict[str, Any]
    selection_mode: Literal["ALL_MATCHING", "TOP_N"]
    top_n: int | None = Field(default=None, gt=0)
    export_profile: str
    catalog_version: str = Field(min_length=64, max_length=64)

    _minimum = field_validator("similarity_minimum", mode="before")(
        _validate_similarity_minimum
    )

    @field_validator("top_n", mode="before")
    @classmethod
    def _strict_top_n(cls, value: Any) -> Any:
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise ValueError("top_n must be a JSON integer.")
        return value

    @model_validator(mode="after")
    def _selection_consistency(self) -> "PotentialCustomerSearchV3Request":
        if self.selection_mode == "TOP_N" and self.top_n is None:
            raise ValueError("top_n is required for TOP_N selection.")
        if self.selection_mode == "ALL_MATCHING" and self.top_n is not None:
            raise ValueError("top_n must be null for ALL_MATCHING selection.")
        if "propensity_bucket" in self.criteria or "match_strength" in self.criteria:
            raise ValueError("V3 criteria cannot contain probability selection fields.")
        return self


class PotentialCustomerPreflightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    context: dict[str, Any]
    criteria: dict[str, Any]
    propensity_bucket: PropensityBucket
    catalog_version: str | None = Field(default=None, min_length=64, max_length=64)


class PotentialCustomerPreflightV3Request(BaseModel):
    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False,
        json_schema_extra={"examples": [_V3_OPENAPI_PREFLIGHT_EXAMPLE]},
    )
    selection_contract_version: Literal["3"]
    score_semantics: Literal["PRODUCT_BUYER_SIMILARITY"]
    similarity_minimum: float
    context: dict[str, Any]
    criteria: dict[str, Any]
    selection_mode: Literal["ALL_MATCHING", "TOP_N"]
    top_n: int | None = Field(default=None, gt=0)
    catalog_version: str = Field(min_length=64, max_length=64)

    _minimum = field_validator("similarity_minimum", mode="before")(
        _validate_similarity_minimum
    )

    @field_validator("top_n", mode="before")
    @classmethod
    def _strict_top_n(cls, value: Any) -> Any:
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise ValueError("top_n must be a JSON integer.")
        return value

    @model_validator(mode="after")
    def _selection_consistency(self) -> "PotentialCustomerPreflightV3Request":
        if self.selection_mode == "TOP_N" and self.top_n is None:
            raise ValueError("top_n is required for TOP_N selection.")
        if self.selection_mode == "ALL_MATCHING" and self.top_n is not None:
            raise ValueError("top_n must be null for ALL_MATCHING selection.")
        if "propensity_bucket" in self.criteria or "match_strength" in self.criteria:
            raise ValueError("V3 criteria cannot contain probability selection fields.")
        return self


class PotentialCustomerPreflightResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    demographic_count: int = Field(ge=0)
    bucket_count: int = Field(ge=0)
    intersection_count: int = Field(ge=0)
    qualifying_count: int = Field(ge=0)
    selected_count: int = Field(ge=0)
    demo_ready: bool
    generation_id: int | None = Field(default=None, gt=0)
    scoring_run_id: int | None = Field(default=None, gt=0)
    calibration_artifact_id: int | None = Field(default=None, gt=0)
    calibration_currentness: Literal["CURRENT", "NOT_AVAILABLE", "STALE", "UNVERIFIED"]
    calibration_eligibility: Literal["ELIGIBLE", "NOT_ELIGIBLE"]
    calibration_reason_code: Literal[
        "ELIGIBLE",
        "GOVERNED_CALIBRATION_NOT_AVAILABLE",
        "AUTHORITATIVE_SOURCES_STALE",
        "CURRENT_ATTESTATION_REQUIRED",
        "CALIBRATION_NOT_PROMOTED",
        "CALIBRATION_GOVERNANCE_INCOMPATIBLE",
        "CALIBRATION_LINEAGE_INVALID",
    ]
    safe_message: str
    criteria_sha256: str = Field(min_length=64, max_length=64)
    filter_branches_sha256: str = Field(min_length=64, max_length=64)
    catalog_version: str = Field(min_length=64, max_length=64)
    source_identity_sha256: str = Field(min_length=64, max_length=64)
    selection_contract_version: Literal["2"]
    selection_mode: Literal["ALL_MATCHING", "TOP_N"]
    target_count: int | None = Field(default=None, gt=0)


class PotentialCustomerSimilarityPreflightResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    selection_contract_version: Literal["3"]
    score_semantics: Literal["PRODUCT_BUYER_SIMILARITY"]
    score_method_version: Literal["BUYER_PROFILE_DISTANCE_V1"]
    similarity_minimum: float
    threshold_predicate: Literal["GREATER_THAN_OR_EQUAL"]
    product_match_policy: Literal["ANY_SELECTED_PRODUCT_MAX_V1"]
    demographic_eligible_count: int = Field(ge=0)
    valid_similarity_count: int | None = Field(default=None, ge=0)
    invalid_similarity_count: int | None = Field(default=None, ge=0)
    similarity_qualifying_count: int | None = Field(default=None, ge=0)
    selected_count: int | None = Field(default=None, ge=0)
    similarity_currentness: Literal[
        "CURRENT", "STALE", "UNVERIFIED", "NOT_AVAILABLE", "BUILDING"
    ]
    similarity_eligibility: Literal["ELIGIBLE", "NOT_ELIGIBLE"]
    reason_code: Literal[
        "ELIGIBLE", "SIMILARITY_NOT_PREPARED", "SIMILARITY_BUILDING",
        "SIMILARITY_STALE", "SIMILARITY_SOURCE_STALE", "PROFILE_NOT_ELIGIBLE", "SOURCE_NOT_CURRENT",
        "SPLIT_SOLVER_UNRESOLVED",
    ]
    safe_message: str
    build_available: bool
    profile_ids: list[int] = Field(max_length=50)
    profile_set_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    composite_context_sha256: str = Field(min_length=64, max_length=64)
    similarity_generation_id: int | None = Field(default=None, gt=0)
    similarity_generation_ids: list[int] = Field(default_factory=list, max_length=50)
    source_identity_sha256: str = Field(min_length=64, max_length=64)
    source_snapshot_version: str
    publication_cutoff: str | None
    catalog_version: str = Field(min_length=64, max_length=64)
    criteria_sha256: str = Field(min_length=64, max_length=64)
    filter_branches_sha256: str = Field(min_length=64, max_length=64)
    selection_mode: Literal["ALL_MATCHING", "TOP_N"]
    top_n: int | None = Field(default=None, gt=0)
    probability_currentness: Literal[
        "CURRENT", "STALE", "UNVERIFIED", "NOT_AVAILABLE"
    ] | None = None
    probability_eligibility: Literal["ELIGIBLE", "NOT_ELIGIBLE"] | None = None
    work_estimate: dict[str, Any] | None = None
    cache_hit: bool = False


class FeedbackBatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feedback_batch_id: int = Field(gt=0)
    search_run_id: int = Field(gt=0)
    attempt_number: int = Field(gt=0)
    status: Literal["ACCEPTED", "REJECTED"]
    row_count: int = Field(gt=0)
    positive_count: int = Field(ge=0)
    negative_count: int = Field(ge=0)
    created_at: str
    recalibration_status: str
    recalibration_reason: str
    # Deprecated compatibility aliases retained for existing API clients.
    retraining_status: str
    retraining_reason: str


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
    workload_class: Literal[
        "PENDING_CLASSIFICATION",
        "DIRECT_INTELLIGENCE_REUSE",
        "PHASE10_REUSE_WITH_VALIDATION",
        "NEW_INTELLIGENCE_BUILD",
        "EXACT_RESULT_REUSE",
        "NEW_RESULT_MATERIALIZATION",
        "TOP_N_MATERIALIZATION",
    ]
    heartbeat_age_seconds: float | None = Field(default=None, ge=0)
    heartbeat_state: Literal["CURRENT", "STALE", "NOT_AVAILABLE"]
    queued_at: str | None
    processing_started_at: str | None
    completed_at: str | None
    queue_seconds: float | None = Field(default=None, ge=0)
    processing_seconds: float | None = Field(default=None, ge=0)
    total_elapsed_seconds: float | None = Field(default=None, ge=0)
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
    affected_stage: str
    technical_reference: str
    user_action_required: bool


class SearchSubmissionStatus(BaseModel):
    """Stable legacy/v1 run-status projection.

    Lifecycle recovery metadata is deliberately not added to this model. Older
    clients rely on this exact safe allowlist; calibrated searches use the
    explicitly versioned ``SearchSubmissionV2Status`` contract below.
    """

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


class SearchSubmissionV2Status(SearchSubmissionStatus):
    """Calibrated-selection status with additive lifecycle recovery fields."""

    selection_contract_version: Literal["2"]
    propensity_bucket: PropensityBucket
    attempt_number: int = Field(gt=0)
    queue_position: int | None = Field(default=None, gt=0)
    progress: SearchRunProgress
    issue: SearchRunIssue | None = None
    retry_eligible: bool


class SearchSubmissionV3Status(SearchSubmissionStatus):
    selection_contract_version: Literal["3"]
    score_semantics: Literal["PRODUCT_BUYER_SIMILARITY"]
    similarity_minimum: float
    score_method_version: Literal["BUYER_PROFILE_DISTANCE_V1"]
    attempt_number: int = Field(gt=0)
    queue_position: int | None = Field(default=None, gt=0)
    progress: SearchRunProgress
    issue: SearchRunIssue | None = None
    retry_eligible: bool


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
    selection_label: Literal["Match Strength", "Purchase Propensity"]
    selection_value: str
    selection_semantics: Literal[
        "LEGACY_RAW_SCORE", "CALIBRATED_PURCHASE_PROBABILITY"
    ]
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
    retry_eligible: bool
    attempt_number: int = Field(default=1, gt=0)
    queue_position: int | None = Field(default=None, gt=0)
    propensity_bucket: PropensityBucket | None = None
    selection_contract_version: Literal["1", "2"] = "1"


class SearchResultHistoryV3Item(SearchResultHistoryItem):
    match_strength: str = "Not applicable"
    selection_label: Literal["Buyer Similarity"]
    selection_semantics: Literal["PRODUCT_BUYER_SIMILARITY"]
    propensity_bucket: None = None
    selection_contract_version: Literal["3"]
    similarity_minimum: float
    score_method_version: Literal["BUYER_PROFILE_DISTANCE_V1"]


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


class SearchResultV3Detail(SearchResultHistoryV3Item):
    description: str | None
    planned_launch_date: str | None
    campaign_context: dict[str, Any]
    targeting_criteria: dict[str, Any]
    filter_branches: list[dict[str, Any]] = Field(min_length=1, max_length=49)
    selection: dict[str, Any]
    result_source_explanation: str
    score_summary: dict[str, Any] | None
    similarity_explanation: dict[str, Any] | None = None
    demographic_summary: dict[str, Any]
    snapshot_provenance: dict[str, Any] | None
    technical_details: dict[str, Any]
    export_summary: dict[str, Any] | None = None
