"""Canonical Phase 10 Modeling Context and compatibility fingerprints."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from string import hexdigits
from typing import Any

from pydantic import ValidationError

from app.services.historical_analysis_service import (
    resolve_current_canonical_contact_date_range,
)

from app.schemas.phase10_intelligence import (
    HistoricalCompatibilityContract,
    ModelCompatibilityContract,
    ModelingContextContract,
    PHASE10_AUTOMATED_TRAINING_POLICY_VERSION,
    PHASE10_AUTOMATED_TRAINING_RANDOM_SEED,
    PHASE10_AUTOMATED_TRAINING_RUN_ELKAN_CHALLENGER,
    PHASE10_AUTOMATED_TRAINING_VALIDATION_FRACTION,
    PHASE10_COMPATIBILITY_CONTRACT_VERSION,
    PHASE10_CONTACTED_ONLY,
    PHASE10_CONVERSION_DEFINITION,
    PHASE10_HISTORICAL_WINDOW_POLICY_VERSION,
    PHASE10_MODELING_CONTEXT_CONTRACT_VERSION,
    PHASE10_MULTI_PRODUCT_POSITIVE_POLICY_VERSION,
    PHASE10_TRAINING_ELIGIBILITY_POLICY_VERSION,
    ResolvedHistoricalFiltersContract,
    ScoreSemanticsContract,
    ScoringCompatibilityContract,
)


_MODELING_CONTEXT_DIMENSIONS = (
    "product_ids",
    "campaign_types",
    "campaign_categories",
    "offer_types",
    "historical_campaign_channels",
)


class Phase10ContextIdentityError(ValueError):
    """Raised when a context or compatibility identity is invalid."""


@dataclass(frozen=True)
class ModelingContextIdentity:
    """Normalized Modeling Context plus its canonical serialized identity."""

    context: ModelingContextContract
    canonical_json: str
    modeling_context_sha256: str

    @property
    def payload(self) -> dict[str, Any]:
        return self.context.model_dump(mode="json")


@dataclass(frozen=True)
class CompatibilityFingerprint:
    """One typed compatibility layer serialized and hashed canonically."""

    kind: str
    payload: dict[str, Any]
    canonical_json: str
    fingerprint_sha256: str


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(canonical_json: str) -> str:
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _identity(
    *,
    kind: str,
    payload: Mapping[str, Any],
) -> CompatibilityFingerprint:
    canonical_json = _canonical_json(payload)
    return CompatibilityFingerprint(
        kind=kind,
        payload=dict(payload),
        canonical_json=canonical_json,
        fingerprint_sha256=_sha256(canonical_json),
    )


def _normalized_sha256(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise Phase10ContextIdentityError(f"{field_name} must be a SHA-256 string.")
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(character not in hexdigits for character in normalized):
        raise Phase10ContextIdentityError(f"{field_name} must be a valid SHA-256 value.")
    return normalized


def _normalized_version(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise Phase10ContextIdentityError(f"{field_name} must be text.")
    normalized = value.strip()
    if not normalized or len(normalized) > 24:
        raise Phase10ContextIdentityError(
            f"{field_name} must contain between 1 and 24 characters."
        )
    return normalized


def normalize_modeling_context(
    value: ModelingContextContract | Mapping[str, Any],
) -> ModelingContextIdentity:
    """Validate, normalize, compact-serialize, and hash a Modeling Context."""

    try:
        context = (
            value
            if isinstance(value, ModelingContextContract)
            else ModelingContextContract.model_validate(value)
        )
    except ValidationError as exc:
        raise Phase10ContextIdentityError("Modeling Context is invalid.") from exc
    payload = context.model_dump(mode="json")
    canonical_json = _canonical_json(payload)
    return ModelingContextIdentity(
        context=context,
        canonical_json=canonical_json,
        modeling_context_sha256=_sha256(canonical_json),
    )


def derive_modeling_context_from_campaign_context(
    campaign_context: Mapping[str, Any],
) -> ModelingContextIdentity:
    """Project only analytical dimensions from the broader Phase 9 business object."""

    if not isinstance(campaign_context, Mapping):
        raise Phase10ContextIdentityError("Campaign Context must be an object.")
    projected = {
        field: campaign_context.get(field, []) for field in _MODELING_CONTEXT_DIMENSIONS
    }
    projected.update(
        {
            "conversion_definition": PHASE10_CONVERSION_DEFINITION,
            "contacted_only": PHASE10_CONTACTED_ONLY,
            "historical_window_policy_version": (
                PHASE10_HISTORICAL_WINDOW_POLICY_VERSION
            ),
            "multi_product_positive_policy_version": (
                PHASE10_MULTI_PRODUCT_POSITIVE_POLICY_VERSION
            ),
            "modeling_context_contract_version": (
                PHASE10_MODELING_CONTEXT_CONTRACT_VERSION
            ),
        }
    )
    return normalize_modeling_context(projected)


def validate_current_modeling_context_policy(
    identity: ModelingContextIdentity,
) -> None:
    """Reject a stored context that is not governed by the current Phase 10 policy."""

    expected = {
        "conversion_definition": PHASE10_CONVERSION_DEFINITION,
        "contacted_only": PHASE10_CONTACTED_ONLY,
        "historical_window_policy_version": PHASE10_HISTORICAL_WINDOW_POLICY_VERSION,
        "multi_product_positive_policy_version": (
            PHASE10_MULTI_PRODUCT_POSITIVE_POLICY_VERSION
        ),
        "modeling_context_contract_version": PHASE10_MODELING_CONTEXT_CONTRACT_VERSION,
    }
    payload = identity.payload
    mismatches = [field for field, value in expected.items() if payload.get(field) != value]
    if mismatches:
        raise Phase10ContextIdentityError(
            "Modeling Context policy is not current for: " + ", ".join(mismatches) + "."
        )


def normalize_resolved_historical_filters(
    value: ResolvedHistoricalFiltersContract | Mapping[str, Any],
) -> ResolvedHistoricalFiltersContract:
    """Normalize the exact persisted historical filter identity."""

    try:
        return (
            value
            if isinstance(value, ResolvedHistoricalFiltersContract)
            else ResolvedHistoricalFiltersContract.model_validate(value)
        )
    except ValidationError as exc:
        raise Phase10ContextIdentityError("Resolved historical filters are invalid.") from exc


def resolve_phase10_historical_filters(
    database_path: str | Path,
    modeling_context: ModelingContextIdentity | ModelingContextContract | Mapping[str, Any],
) -> ResolvedHistoricalFiltersContract:
    """Resolve one Phase 10 context to exact full-window Historical filters."""

    identity = (
        modeling_context
        if isinstance(modeling_context, ModelingContextIdentity)
        else normalize_modeling_context(modeling_context)
    )
    validate_current_modeling_context_policy(identity)
    contact_date_from, contact_date_to = resolve_current_canonical_contact_date_range(
        database_path
    )
    context = identity.context
    return ResolvedHistoricalFiltersContract(
        campaign_ids=[],
        product_ids=context.product_ids,
        product_categories=[],
        campaign_categories=context.campaign_categories,
        offer_types=context.offer_types,
        campaign_channels=context.historical_campaign_channels,
        campaign_types=context.campaign_types,
        contact_date_from=contact_date_from,
        contact_date_to=contact_date_to,
        contacted_only=context.contacted_only,
        conversion_definition=context.conversion_definition,
    )


def _validate_context_filter_alignment(
    modeling_context: ModelingContextContract,
    resolved_filters: ResolvedHistoricalFiltersContract,
) -> None:
    pairs = (
        ("product_ids", modeling_context.product_ids, resolved_filters.product_ids),
        ("campaign_types", modeling_context.campaign_types, resolved_filters.campaign_types),
        (
            "campaign_categories",
            modeling_context.campaign_categories,
            resolved_filters.campaign_categories,
        ),
        ("offer_types", modeling_context.offer_types, resolved_filters.offer_types),
        (
            "historical_campaign_channels",
            modeling_context.historical_campaign_channels,
            resolved_filters.campaign_channels,
        ),
        (
            "conversion_definition",
            modeling_context.conversion_definition,
            resolved_filters.conversion_definition,
        ),
        ("contacted_only", modeling_context.contacted_only, resolved_filters.contacted_only),
    )
    mismatches = [name for name, context_value, filter_value in pairs if context_value != filter_value]
    if mismatches:
        raise Phase10ContextIdentityError(
            "Resolved historical filters do not match Modeling Context for: "
            + ", ".join(mismatches)
            + "."
        )


def build_historical_compatibility_fingerprint(
    *,
    modeling_context: ModelingContextIdentity | ModelingContextContract | Mapping[str, Any],
    resolved_historical_filters: ResolvedHistoricalFiltersContract | Mapping[str, Any],
    customer_source_checksum: str,
    campaign_sales_source_checksum: str,
) -> CompatibilityFingerprint:
    """Fingerprint exact context, resolved filters, policies, and historical sources."""

    context_identity = (
        modeling_context
        if isinstance(modeling_context, ModelingContextIdentity)
        else normalize_modeling_context(modeling_context)
    )
    filters = normalize_resolved_historical_filters(resolved_historical_filters)
    _validate_context_filter_alignment(context_identity.context, filters)
    contract = HistoricalCompatibilityContract(
        compatibility_contract_version=PHASE10_COMPATIBILITY_CONTRACT_VERSION,
        modeling_context=context_identity.context,
        modeling_context_sha256=context_identity.modeling_context_sha256,
        resolved_historical_filters=filters,
        customer_source_checksum=_normalized_sha256(
            customer_source_checksum,
            field_name="customer_source_checksum",
        ),
        campaign_sales_source_checksum=_normalized_sha256(
            campaign_sales_source_checksum,
            field_name="campaign_sales_source_checksum",
        ),
    )
    return _identity(
        kind="HISTORICAL_COMPATIBILITY",
        payload=contract.model_dump(mode="json"),
    )


def build_model_compatibility_fingerprint(
    *,
    historical_fingerprint: CompatibilityFingerprint,
    analysis_run_id: int,
    feature_contract_version: str,
    feature_contract_sha256: str,
    model_role_policy_version: str,
    evaluation_contract_version: str,
    training_eligibility_policy_version: str = (
        PHASE10_TRAINING_ELIGIBILITY_POLICY_VERSION
    ),
    automated_training_policy_version: str = PHASE10_AUTOMATED_TRAINING_POLICY_VERSION,
    random_seed: int = PHASE10_AUTOMATED_TRAINING_RANDOM_SEED,
    validation_fraction: float = PHASE10_AUTOMATED_TRAINING_VALIDATION_FRACTION,
    run_elkan_challenger: bool = PHASE10_AUTOMATED_TRAINING_RUN_ELKAN_CHALLENGER,
) -> CompatibilityFingerprint:
    """Fingerprint exact historical lineage and governed model/training policies."""

    if historical_fingerprint.kind != "HISTORICAL_COMPATIBILITY":
        raise Phase10ContextIdentityError(
            "Model compatibility requires a historical compatibility fingerprint."
        )
    try:
        contract = ModelCompatibilityContract(
            compatibility_contract_version=PHASE10_COMPATIBILITY_CONTRACT_VERSION,
            historical_compatibility_sha256=_normalized_sha256(
                historical_fingerprint.fingerprint_sha256,
                field_name="historical_compatibility_sha256",
            ),
            analysis_run_id=analysis_run_id,
            feature_contract_version=_normalized_version(
                feature_contract_version,
                field_name="feature_contract_version",
            ),
            feature_contract_sha256=_normalized_sha256(
                feature_contract_sha256,
                field_name="feature_contract_sha256",
            ),
            model_role_policy_version=_normalized_version(
                model_role_policy_version,
                field_name="model_role_policy_version",
            ),
            evaluation_contract_version=_normalized_version(
                evaluation_contract_version,
                field_name="evaluation_contract_version",
            ),
            training_eligibility_policy_version=_normalized_version(
                training_eligibility_policy_version,
                field_name="training_eligibility_policy_version",
            ),
            automated_training_policy_version=_normalized_version(
                automated_training_policy_version,
                field_name="automated_training_policy_version",
            ),
            random_seed=random_seed,
            validation_fraction=validation_fraction,
            run_elkan_challenger=run_elkan_challenger,
        )
    except ValidationError as exc:
        raise Phase10ContextIdentityError("Model compatibility identity is invalid.") from exc
    return _identity(
        kind="MODEL_COMPATIBILITY",
        payload=contract.model_dump(mode="json"),
    )


def build_scoring_compatibility_fingerprint(
    *,
    model_fingerprint: CompatibilityFingerprint,
    model_run_id: int,
    artifact_sha256: str,
    demographic_source_checksum: str,
    demographic_count: int,
    score_semantics: ScoreSemanticsContract | Mapping[str, Any] | None = None,
) -> CompatibilityFingerprint:
    """Fingerprint exact model/artifact, demographics, and score semantics."""

    if model_fingerprint.kind != "MODEL_COMPATIBILITY":
        raise Phase10ContextIdentityError(
            "Scoring compatibility requires a model compatibility fingerprint."
        )
    try:
        semantics = (
            ScoreSemanticsContract()
            if score_semantics is None
            else (
                score_semantics
                if isinstance(score_semantics, ScoreSemanticsContract)
                else ScoreSemanticsContract.model_validate(score_semantics)
            )
        )
        contract = ScoringCompatibilityContract(
            compatibility_contract_version=PHASE10_COMPATIBILITY_CONTRACT_VERSION,
            model_compatibility_sha256=_normalized_sha256(
                model_fingerprint.fingerprint_sha256,
                field_name="model_compatibility_sha256",
            ),
            model_run_id=model_run_id,
            artifact_sha256=_normalized_sha256(
                artifact_sha256,
                field_name="artifact_sha256",
            ),
            demographic_source_checksum=_normalized_sha256(
                demographic_source_checksum,
                field_name="demographic_source_checksum",
            ),
            demographic_count=demographic_count,
            score_semantics=semantics,
        )
    except ValidationError as exc:
        raise Phase10ContextIdentityError("Scoring compatibility identity is invalid.") from exc
    return _identity(
        kind="SCORING_COMPATIBILITY",
        payload=contract.model_dump(mode="json"),
    )


__all__ = (
    "CompatibilityFingerprint",
    "ModelingContextIdentity",
    "Phase10ContextIdentityError",
    "build_historical_compatibility_fingerprint",
    "build_model_compatibility_fingerprint",
    "build_scoring_compatibility_fingerprint",
    "derive_modeling_context_from_campaign_context",
    "normalize_modeling_context",
    "normalize_resolved_historical_filters",
    "resolve_phase10_historical_filters",
    "validate_current_modeling_context_policy",
)
