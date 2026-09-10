"""Normalization and mapping for versioned Phase 9 targeting contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from itertools import product
from typing import Any

from pydantic import ValidationError

from app.schemas.campaign_targeting import (
    AGE_BUCKET_CONTRACT_VERSION,
    AGE_BUCKETS,
    BUSINESS_MATCH_STRENGTH_CONTRACT_VERSION,
    CAMPAIGN_TARGETING_CONTEXT_CONTRACT_VERSION,
    INCOME_GROUP_CONTRACT_VERSION,
    INCOME_GROUPS,
    MATCH_STRENGTH_THRESHOLDS,
    TARGETING_SEGMENT_CONTRACT_VERSION,
    BusinessTargetingCriteriaContract,
    CampaignTargetingContextContract,
    NumericBand,
)
from app.services.audience_query_service import (
    AUDIENCE_FILTER_CONTRACT_VERSION,
    AudienceQueryValidationError,
    normalize_audience_filters,
    normalize_selection,
)


class CampaignTargetingContractValidationError(ValueError):
    """Raised when a Phase 9 business contract is invalid or non-canonical."""


@dataclass(frozen=True)
class NormalizedCampaignTargetingContext:
    payload: dict[str, Any]
    canonical_json: str
    sha256: str


@dataclass(frozen=True)
class NormalizedBusinessTargetingCriteria:
    payload: dict[str, Any]
    canonical_json: str
    sha256: str
    audience_filter_branches: tuple[dict[str, Any], ...]
    audience_selection: dict[str, Any]


_CONTEXT_REFERENCE_FIELDS = {
    "product_ids": "product_ids",
    "campaign_types": "campaign_types",
    "campaign_categories": "campaign_categories",
    "offer_types": "offer_types",
    "historical_campaign_channels": "campaign_channels",
}

_TARGETING_REFERENCE_FIELDS = {
    "genders": "gender",
    "states": "state",
    "marital_statuses": "marital_status",
    "education_levels": "education",
    "employment_statuses": "employment_status",
    "resident_statuses": "resident_status",
    "resident_types": "resident_type",
    "employment_types": "type_of_employment",
}

_BUSINESS_FIELD_LABELS = {
    "product_ids": "product",
    "campaign_types": "campaign type",
    "campaign_categories": "campaign category",
    "offer_types": "offer",
    "historical_campaign_channels": "historical campaign channel",
    "genders": "gender",
    "states": "location",
    "marital_statuses": "marital status",
    "education_levels": "education",
    "employment_statuses": "employment status",
    "resident_statuses": "resident status",
    "resident_types": "resident type",
    "employment_types": "employment type",
}


def _canonicalize(payload: dict[str, Any]) -> tuple[str, str]:
    canonical_json = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return canonical_json, hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _validate_selected_reference_values(
    *,
    payload: Mapping[str, Any],
    field_mapping: Mapping[str, str],
    allowed_values: Mapping[str, Collection[str]],
) -> None:
    for contract_field, reference_field in field_mapping.items():
        selected = payload.get(contract_field, [])
        if not selected:
            continue
        allowed = {
            item.strip()
            for item in allowed_values.get(reference_field, ())
            if isinstance(item, str) and item.strip()
        }
        unsupported = sorted(
            (item for item in selected if item not in allowed),
            key=lambda item: (item.casefold(), item),
        )
        if unsupported:
            label = _BUSINESS_FIELD_LABELS.get(contract_field, "choice")
            raise CampaignTargetingContractValidationError(
                f"The selected {label} option is no longer available. Refresh the "
                f"choices and select an available option. Removed selection: "
                f"{', '.join(unsupported)}."
            )


def _context_validation_message(exc: ValidationError) -> str:
    fields = {str(error["loc"][-1]) for error in exc.errors() if error.get("loc")}
    if "product_ids" in fields:
        return "Choose at least one currently available product."
    if "campaign_channel" in fields:
        return "Choose an available campaign delivery channel."
    return "Review the campaign context choices and try again."


def _targeting_validation_message(exc: ValidationError) -> str:
    errors = exc.errors()
    fields = {str(error["loc"][-1]) for error in errors if error.get("loc")}
    messages = " ".join(str(error.get("msg", "")) for error in errors)
    if "match_strength" in fields:
        return "Choose one of the available Targeting Match options."
    if "family_member_count_min" in messages or "family_member_count_max" in messages:
        return "Choose a minimum family size that is not higher than the maximum."
    if "family_member_count_min" in fields or "family_member_count_max" in fields:
        return "Family size must be a whole number greater than zero."
    if "selection_mode" in fields:
        return "Choose all matching people or choose a specific number of people."
    if "target_count" in fields or "target_count" in messages:
        return (
            "Enter a whole number greater than zero when choosing a specific number "
            "of people."
        )
    if "age_groups" in fields:
        return "Choose only the available age groups."
    if "income_groups" in fields:
        return "Choose only the available income groups."
    return "Review the targeting preferences and try again."


def normalize_campaign_targeting_context(
    raw_context: Any,
    *,
    allowed_values: Mapping[str, Collection[str]],
) -> NormalizedCampaignTargetingContext:
    """Normalize context and reject selections absent from current reference data."""

    try:
        context = CampaignTargetingContextContract.model_validate(raw_context)
    except ValidationError as exc:
        raise CampaignTargetingContractValidationError(
            _context_validation_message(exc)
        ) from exc

    values = context.model_dump(mode="json")
    _validate_selected_reference_values(
        payload=values,
        field_mapping=_CONTEXT_REFERENCE_FIELDS,
        allowed_values=allowed_values,
    )
    payload = {
        "campaign_targeting_context_contract_version": (
            CAMPAIGN_TARGETING_CONTEXT_CONTRACT_VERSION
        ),
        **values,
    }
    canonical_json, digest = _canonicalize(payload)
    return NormalizedCampaignTargetingContext(
        payload=payload,
        canonical_json=canonical_json,
        sha256=digest,
    )


def _selected_merged_ranges(
    selected: Collection[str],
    *,
    definitions: tuple[NumericBand, ...],
) -> tuple[tuple[float | int | None, float | int | None], ...]:
    if not selected:
        return ((None, None),)

    selected_values = set(selected)
    ranges = [
        (definition.minimum, definition.maximum)
        for definition in definitions
        if definition.value in selected_values
    ]
    merged: list[list[float | int | None]] = []
    for minimum, maximum in ranges:
        if not merged:
            merged.append([minimum, maximum])
            continue
        previous_maximum = merged[-1][1]
        if previous_maximum is not None and minimum <= previous_maximum + 1:
            merged[-1][1] = maximum
        else:
            merged.append([minimum, maximum])
    return tuple((minimum, maximum) for minimum, maximum in merged)


def _audience_filter_branches(
    criteria: BusinessTargetingCriteriaContract,
) -> tuple[dict[str, Any], ...]:
    base: dict[str, Any] = {
        "score_min": MATCH_STRENGTH_THRESHOLDS[criteria.match_strength],
    }
    direct_fields = {
        "gender": criteria.genders,
        "state": criteria.states,
        "marital_status": criteria.marital_statuses,
        "education": criteria.education_levels,
        "employment_status": criteria.employment_statuses,
        "resident_status": criteria.resident_statuses,
        "resident_type": criteria.resident_types,
        "type_of_employment": criteria.employment_types,
    }
    for field_name, values in direct_fields.items():
        if values:
            base[field_name] = list(values)
    if criteria.family_member_count_min is not None:
        base["family_member_count_min"] = criteria.family_member_count_min
    if criteria.family_member_count_max is not None:
        base["family_member_count_max"] = criteria.family_member_count_max
    if criteria.top_matching_percent is not None:
        base["top_percentile_max"] = criteria.top_matching_percent

    age_ranges = _selected_merged_ranges(criteria.age_groups, definitions=AGE_BUCKETS)
    income_ranges = _selected_merged_ranges(criteria.income_groups, definitions=INCOME_GROUPS)
    normalized_branches: dict[str, dict[str, Any]] = {}
    for (age_min, age_max), (income_min, income_max) in product(age_ranges, income_ranges):
        branch = dict(base)
        if age_min is not None:
            branch["age_min"] = age_min
        if age_max is not None:
            branch["age_max"] = age_max
        if income_min is not None:
            branch["individual_yearly_income_min"] = income_min
        if income_max is not None:
            branch["individual_yearly_income_max"] = income_max
        normalized = normalize_audience_filters(branch)
        normalized_branches[normalized.canonical_json] = normalized.payload

    return tuple(normalized_branches[key] for key in sorted(normalized_branches))


def normalize_business_targeting_criteria(
    raw_criteria: Any,
    *,
    allowed_values: Mapping[str, Collection[str]],
) -> NormalizedBusinessTargetingCriteria:
    """Normalize business criteria and map them to exact Audience Filter branches.

    Disjoint age or income selections remain separate OR branches. They are never
    collapsed into a broader min/max interval that would select an unchosen bucket.
    """

    try:
        criteria = BusinessTargetingCriteriaContract.model_validate(raw_criteria)
    except ValidationError as exc:
        raise CampaignTargetingContractValidationError(
            _targeting_validation_message(exc)
        ) from exc

    values = criteria.model_dump(mode="json")
    _validate_selected_reference_values(
        payload=values,
        field_mapping=_TARGETING_REFERENCE_FIELDS,
        allowed_values=allowed_values,
    )
    try:
        branches = _audience_filter_branches(criteria)
        selection = normalize_selection(
            {
                "mode": criteria.selection_mode,
                "target_count": criteria.target_count,
            }
        ).payload
    except AudienceQueryValidationError as exc:
        raise CampaignTargetingContractValidationError(str(exc)) from exc

    payload = {
        "targeting_segment_contract_version": TARGETING_SEGMENT_CONTRACT_VERSION,
        "business_match_strength_contract_version": (
            BUSINESS_MATCH_STRENGTH_CONTRACT_VERSION
        ),
        "age_bucket_contract_version": AGE_BUCKET_CONTRACT_VERSION,
        "income_group_contract_version": INCOME_GROUP_CONTRACT_VERSION,
        "audience_filter_contract_version": AUDIENCE_FILTER_CONTRACT_VERSION,
        **values,
    }
    canonical_json, digest = _canonicalize(payload)
    return NormalizedBusinessTargetingCriteria(
        payload=payload,
        canonical_json=canonical_json,
        sha256=digest,
        audience_filter_branches=branches,
        audience_selection=selection,
    )


__all__ = (
    "CampaignTargetingContractValidationError",
    "NormalizedBusinessTargetingCriteria",
    "NormalizedCampaignTargetingContext",
    "normalize_business_targeting_criteria",
    "normalize_campaign_targeting_context",
)
