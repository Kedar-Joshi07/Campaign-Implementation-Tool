"""Versioned Phase 10 intelligence identity and policy contracts."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PHASE10_MODELING_CONTEXT_CONTRACT_VERSION = "1"
PHASE10_COMPATIBILITY_CONTRACT_VERSION = "1"
PHASE10_HISTORICAL_WINDOW_POLICY_VERSION = "1"
PHASE10_MULTI_PRODUCT_POSITIVE_POLICY_VERSION = "1"
PHASE10_TRAINING_ELIGIBILITY_POLICY_VERSION = "1"
PHASE10_AUTOMATED_TRAINING_POLICY_VERSION = "1"
PHASE10_ORCHESTRATION_CONTRACT_VERSION = "1"
PHASE10_INTELLIGENCE_GENERATION_CONTRACT_VERSION = "1"
PHASE10_LIFECYCLE_POLICY_VERSION = "1"

PHASE10_CONVERSION_DEFINITION = "ATTRIBUTED_PURCHASE"
PHASE10_CONTACTED_ONLY = True
PHASE10_AUTOMATED_TRAINING_RANDOM_SEED = 42
PHASE10_AUTOMATED_TRAINING_VALIDATION_FRACTION = 0.20
PHASE10_AUTOMATED_TRAINING_RUN_ELKAN_CHALLENGER = True
PHASE10_MINIMUM_SELECTED_CUSTOMERS = 14
PHASE10_MINIMUM_POSITIVE_CUSTOMERS = 7
PHASE10_MINIMUM_UNLABELED_CUSTOMERS = 7

PHASE10_INSUFFICIENT_HISTORY_MESSAGE = (
    "There is not enough verified past campaign history for this combination yet."
)

ConversionDefinition = Literal["ATTRIBUTED_PURCHASE", "ANY_PURCHASE", "RESPONSE"]


def _normalize_identity_list(value: Any) -> Any:
    if value is None:
        return []
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError("identity values must be provided as a collection")

    normalized: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError("identity values must be strings")
        text = item.strip()
        if not text:
            raise ValueError("identity values must not be blank")
        normalized.add(text)
    return sorted(normalized, key=lambda item: (item.casefold(), item))


def _normalize_version(value: Any) -> Any:
    if not isinstance(value, str):
        raise ValueError("policy and contract versions must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError("policy and contract versions must not be blank")
    return normalized


class Phase10StrictModel(BaseModel):
    """Strict finite Phase 10 contract base."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ModelingContextContract(Phase10StrictModel):
    """Canonical analytical identity projected from the Phase 9 campaign context."""

    product_ids: list[str] = Field(min_length=1, max_length=50)
    campaign_types: list[str] = Field(default_factory=list, max_length=50)
    campaign_categories: list[str] = Field(default_factory=list, max_length=50)
    offer_types: list[str] = Field(default_factory=list, max_length=50)
    historical_campaign_channels: list[str] = Field(default_factory=list, max_length=50)
    conversion_definition: ConversionDefinition = PHASE10_CONVERSION_DEFINITION
    contacted_only: bool = PHASE10_CONTACTED_ONLY
    historical_window_policy_version: str = Field(
        default=PHASE10_HISTORICAL_WINDOW_POLICY_VERSION,
        max_length=24,
    )
    multi_product_positive_policy_version: str = Field(
        default=PHASE10_MULTI_PRODUCT_POSITIVE_POLICY_VERSION,
        max_length=24,
    )
    modeling_context_contract_version: str = Field(
        default=PHASE10_MODELING_CONTEXT_CONTRACT_VERSION,
        max_length=24,
    )

    @field_validator(
        "product_ids",
        "campaign_types",
        "campaign_categories",
        "offer_types",
        "historical_campaign_channels",
        mode="before",
    )
    @classmethod
    def normalize_identity_lists(cls, value: Any) -> Any:
        return _normalize_identity_list(value)

    @field_validator(
        "historical_window_policy_version",
        "multi_product_positive_policy_version",
        "modeling_context_contract_version",
        mode="before",
    )
    @classmethod
    def normalize_versions(cls, value: Any) -> Any:
        return _normalize_version(value)


class ResolvedHistoricalFiltersContract(Phase10StrictModel):
    """Exact, date-resolved filter identity used for historical compatibility."""

    campaign_ids: list[str] = Field(default_factory=list, max_length=25)
    product_ids: list[str] = Field(min_length=1, max_length=50)
    product_categories: list[str] = Field(default_factory=list, max_length=25)
    campaign_categories: list[str] = Field(default_factory=list, max_length=50)
    offer_types: list[str] = Field(default_factory=list, max_length=50)
    campaign_channels: list[str] = Field(default_factory=list, max_length=50)
    campaign_types: list[str] = Field(default_factory=list, max_length=50)
    contact_date_from: date
    contact_date_to: date
    contacted_only: bool
    conversion_definition: ConversionDefinition

    @field_validator(
        "campaign_ids",
        "product_ids",
        "product_categories",
        "campaign_categories",
        "offer_types",
        "campaign_channels",
        "campaign_types",
        mode="before",
    )
    @classmethod
    def normalize_filter_lists(cls, value: Any) -> Any:
        return _normalize_identity_list(value)

    @model_validator(mode="after")
    def validate_historical_window(self) -> ResolvedHistoricalFiltersContract:
        if self.contact_date_from > self.contact_date_to:
            raise ValueError("contact_date_from must be on or before contact_date_to")
        return self


class ScoreSemanticsContract(Phase10StrictModel):
    """Exact semantics that determine whether persisted scores are reusable."""

    minimum_score: float = 0.0
    maximum_score: float = 1.0
    higher_is_better: bool = True
    ordering: str = Field(
        default="propensity_score DESC, person_id ASC",
        min_length=1,
        max_length=120,
    )
    full_canonical_universe_required: bool = True

    @field_validator("ordering", mode="before")
    @classmethod
    def normalize_ordering(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        return " ".join(value.split())

    @model_validator(mode="after")
    def validate_score_range(self) -> ScoreSemanticsContract:
        if self.minimum_score >= self.maximum_score:
            raise ValueError("minimum_score must be less than maximum_score")
        return self


class HistoricalCompatibilityContract(Phase10StrictModel):
    compatibility_contract_version: str = Field(
        default=PHASE10_COMPATIBILITY_CONTRACT_VERSION,
        max_length=24,
    )
    modeling_context: ModelingContextContract
    modeling_context_sha256: str = Field(min_length=64, max_length=64)
    resolved_historical_filters: ResolvedHistoricalFiltersContract
    customer_source_checksum: str = Field(min_length=64, max_length=64)
    campaign_sales_source_checksum: str = Field(min_length=64, max_length=64)


class ModelCompatibilityContract(Phase10StrictModel):
    compatibility_contract_version: str = Field(
        default=PHASE10_COMPATIBILITY_CONTRACT_VERSION,
        max_length=24,
    )
    historical_compatibility_sha256: str = Field(min_length=64, max_length=64)
    analysis_run_id: int = Field(gt=0)
    feature_contract_version: str = Field(min_length=1, max_length=24)
    feature_contract_sha256: str = Field(min_length=64, max_length=64)
    model_role_policy_version: str = Field(min_length=1, max_length=24)
    evaluation_contract_version: str = Field(min_length=1, max_length=24)
    training_eligibility_policy_version: str = Field(min_length=1, max_length=24)
    automated_training_policy_version: str = Field(min_length=1, max_length=24)
    random_seed: int
    validation_fraction: float = Field(gt=0.0, lt=1.0)
    run_elkan_challenger: bool


class ScoringCompatibilityContract(Phase10StrictModel):
    compatibility_contract_version: str = Field(
        default=PHASE10_COMPATIBILITY_CONTRACT_VERSION,
        max_length=24,
    )
    model_compatibility_sha256: str = Field(min_length=64, max_length=64)
    model_run_id: int = Field(gt=0)
    artifact_sha256: str = Field(min_length=64, max_length=64)
    demographic_source_checksum: str = Field(min_length=64, max_length=64)
    demographic_count: int = Field(gt=0)
    score_semantics: ScoreSemanticsContract


class TrainingEligibilityContract(Phase10StrictModel):
    """Frozen Phase 10 v1 count and deterministic-split eligibility decision."""

    training_eligibility_policy_version: str = Field(
        default=PHASE10_TRAINING_ELIGIBILITY_POLICY_VERSION,
        min_length=1,
        max_length=24,
    )
    status: Literal["ELIGIBLE", "BLOCKED"]
    selected_customer_count: int = Field(ge=0)
    positive_customer_count: int = Field(ge=0)
    unlabeled_customer_count: int = Field(ge=0)
    minimum_selected_customer_count: int = PHASE10_MINIMUM_SELECTED_CUSTOMERS
    minimum_positive_customer_count: int = PHASE10_MINIMUM_POSITIVE_CUSTOMERS
    minimum_unlabeled_customer_count: int = PHASE10_MINIMUM_UNLABELED_CUSTOMERS
    deterministic_split_viable: bool
    reason_codes: list[str] = Field(default_factory=list, max_length=8)
    business_message: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_decision(self) -> TrainingEligibilityContract:
        if (
            self.training_eligibility_policy_version
            != PHASE10_TRAINING_ELIGIBILITY_POLICY_VERSION
            or self.minimum_selected_customer_count
            != PHASE10_MINIMUM_SELECTED_CUSTOMERS
            or self.minimum_positive_customer_count
            != PHASE10_MINIMUM_POSITIVE_CUSTOMERS
            or self.minimum_unlabeled_customer_count
            != PHASE10_MINIMUM_UNLABELED_CUSTOMERS
        ):
            raise ValueError("eligibility decision does not use the current frozen policy")
        if self.positive_customer_count + self.unlabeled_customer_count != (
            self.selected_customer_count
        ):
            raise ValueError("positive and unlabeled counts must reconcile to selected")
        if self.status == "ELIGIBLE":
            if self.reason_codes or self.business_message is not None:
                raise ValueError("eligible decisions must not contain blocking details")
            if not self.deterministic_split_viable:
                raise ValueError("eligible decisions require a viable deterministic split")
        elif not self.reason_codes or self.business_message != (
            PHASE10_INSUFFICIENT_HISTORY_MESSAGE
        ):
            raise ValueError("blocked decisions require reasons and the governed message")
        return self


Phase10ReuseDecision = Literal["REUSE", "BUILD"]
Phase10Readiness = Literal[
    "READY",
    "PREPARING",
    "NEEDS_PREPARATION",
    "BLOCKED",
    "FAILED",
    "STALE",
]
Phase10PreparationStatus = Literal[
    "NOT_STARTED",
    "QUEUED",
    "RUNNING",
    "READY",
    "BLOCKED",
    "FAILED",
    "STALE",
]
Phase10LifecycleState = Literal[
    "CURRENT",
    "REUSABLE",
    "SUPERSEDED",
    "STALE",
    "RETIREMENT_ELIGIBLE",
    "PROTECTED",
]
Phase10ProtectionReason = Literal[
    "SAVED_AUDIENCE",
    "PHASE9_SAVED_TARGET_GROUP",
    "CAMPAIGN",
    "FINALIZED_CAMPAIGN",
    "EXPORT_AUDIT_HISTORY",
    "ACTIVE_ORCHESTRATION",
]


class Phase10ReuseSummary(Phase10StrictModel):
    """Business-safe reuse/build decisions for each governed analytical layer."""

    analysis: Phase10ReuseDecision
    model: Phase10ReuseDecision
    scoring: Phase10ReuseDecision
    rank: Phase10ReuseDecision


class Phase10ModelingContextIdentityResponse(Phase10StrictModel):
    """No-PII analytical identity derived from a Campaign Context."""

    modeling_context_sha256: str = Field(min_length=64, max_length=64)
    context: ModelingContextContract


class Phase10IntelligencePlanResponse(Phase10StrictModel):
    targeting_context_id: int = Field(gt=0)
    readiness: Phase10Readiness
    is_ready: bool
    business_message: str = Field(min_length=1, max_length=1000)
    modeling_context: Phase10ModelingContextIdentityResponse
    reuse_summary: Phase10ReuseSummary


class Phase10PreparationTechnicalDetails(Phase10StrictModel):
    """Audit identifiers deliberately nested away from the business status surface."""

    orchestration_id: int | None = Field(default=None, gt=0)
    modeling_context_sha256: str = Field(min_length=64, max_length=64)
    intelligence_key_sha256: str = Field(min_length=64, max_length=64)
    generation_id: int | None = Field(default=None, gt=0)
    analysis_run_id: int | None = Field(default=None, gt=0)
    model_run_id: int | None = Field(default=None, gt=0)
    scoring_run_id: int | None = Field(default=None, gt=0)
    training_job_id: int | None = Field(default=None, gt=0)
    scoring_job_id: int | None = Field(default=None, gt=0)
    technical_message: str | None = Field(default=None, max_length=200)


class Phase10PreparationResponse(Phase10StrictModel):
    targeting_context_id: int = Field(gt=0)
    status: Phase10PreparationStatus
    stage: str = Field(min_length=1, max_length=80)
    progress_percent: int = Field(ge=0, le=100)
    business_message: str = Field(min_length=1, max_length=1000)
    can_retry: bool
    is_ready: bool
    reuse_summary: Phase10ReuseSummary
    technical_details: Phase10PreparationTechnicalDetails


class Phase10LifecycleGenerationReport(Phase10StrictModel):
    generation_id: int = Field(gt=0)
    lifecycle_state: Phase10LifecycleState
    classification_before_protection: Phase10LifecycleState
    source_current: bool
    score_row_count: int = Field(ge=0)
    protection_reasons: list[Phase10ProtectionReason] = Field(max_length=6)
    reusable_targeting_context_ids: list[int] = Field(max_length=10000)
    last_verified_at: str = Field(min_length=1, max_length=64)
    last_used_at: str = Field(min_length=1, max_length=64)


class Phase10LifecycleReport(Phase10StrictModel):
    lifecycle_policy_version: str = Field(min_length=1, max_length=24)
    generated_at: str = Field(min_length=1, max_length=64)
    total_generation_count: int = Field(ge=0)
    counts_by_state: dict[Phase10LifecycleState, int]
    score_row_footprint_count: int = Field(ge=0)
    reusable_contexts: dict[int, list[int]]
    retirement_eligible_generation_ids: list[int] = Field(max_length=10000)
    generations: list[Phase10LifecycleGenerationReport] = Field(max_length=10000)


__all__ = (
    "ConversionDefinition",
    "HistoricalCompatibilityContract",
    "ModelCompatibilityContract",
    "ModelingContextContract",
    "PHASE10_AUTOMATED_TRAINING_POLICY_VERSION",
    "PHASE10_AUTOMATED_TRAINING_RANDOM_SEED",
    "PHASE10_AUTOMATED_TRAINING_RUN_ELKAN_CHALLENGER",
    "PHASE10_AUTOMATED_TRAINING_VALIDATION_FRACTION",
    "PHASE10_COMPATIBILITY_CONTRACT_VERSION",
    "PHASE10_CONTACTED_ONLY",
    "PHASE10_CONVERSION_DEFINITION",
    "PHASE10_HISTORICAL_WINDOW_POLICY_VERSION",
    "PHASE10_INTELLIGENCE_GENERATION_CONTRACT_VERSION",
    "PHASE10_INSUFFICIENT_HISTORY_MESSAGE",
    "PHASE10_LIFECYCLE_POLICY_VERSION",
    "PHASE10_MINIMUM_POSITIVE_CUSTOMERS",
    "PHASE10_MINIMUM_SELECTED_CUSTOMERS",
    "PHASE10_MINIMUM_UNLABELED_CUSTOMERS",
    "PHASE10_MODELING_CONTEXT_CONTRACT_VERSION",
    "PHASE10_MULTI_PRODUCT_POSITIVE_POLICY_VERSION",
    "PHASE10_ORCHESTRATION_CONTRACT_VERSION",
    "PHASE10_TRAINING_ELIGIBILITY_POLICY_VERSION",
    "Phase10StrictModel",
    "Phase10IntelligencePlanResponse",
    "Phase10LifecycleGenerationReport",
    "Phase10LifecycleReport",
    "Phase10LifecycleState",
    "Phase10ModelingContextIdentityResponse",
    "Phase10PreparationResponse",
    "Phase10PreparationStatus",
    "Phase10PreparationTechnicalDetails",
    "Phase10ProtectionReason",
    "Phase10Readiness",
    "Phase10ReuseDecision",
    "Phase10ReuseSummary",
    "ResolvedHistoricalFiltersContract",
    "ScoreSemanticsContract",
    "ScoringCompatibilityContract",
    "TrainingEligibilityContract",
)
