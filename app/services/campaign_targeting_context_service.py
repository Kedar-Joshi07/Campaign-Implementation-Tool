"""Application service for Phase 9 campaign-context capture."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.database.schema import initialize_database
from app.repositories.campaign_targeting_context_repository import (
    CampaignTargetingContextRepository,
)
from app.schemas.campaign_targeting import (
    AGE_BUCKET_CONTRACT_VERSION,
    AGE_BUCKETS,
    BUSINESS_MATCH_STRENGTH_CONTRACT_VERSION,
    CAMPAIGN_TARGETING_CONTEXT_CONTRACT_VERSION,
    DEFAULT_MATCH_STRENGTH,
    INCOME_GROUP_CONTRACT_VERSION,
    INCOME_GROUPS,
    MATCH_STRENGTH_THRESHOLDS,
    TARGETING_SEGMENT_CONTRACT_VERSION,
)
from app.services.campaign_contracts import CAMPAIGN_CHANNELS
from app.services.campaign_targeting_contract_service import (
    CampaignTargetingContractValidationError,
    normalize_business_targeting_criteria,
    normalize_campaign_targeting_context,
)


class CampaignContextServiceError(RuntimeError):
    pass


class CampaignContextValidationError(CampaignContextServiceError):
    pass


class CampaignContextNotFoundError(CampaignContextServiceError):
    pass


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_options(repository: CampaignTargetingContextRepository) -> dict[str, Any]:
    values = repository.fetch_context_options()
    values.update(
        {
            "campaign_targeting_context_contract_version": (
                CAMPAIGN_TARGETING_CONTEXT_CONTRACT_VERSION
            ),
            "delivery_channels": [
                {
                    "value": channel,
                    "label": channel.replace("_", " ").title(),
                }
                for channel in CAMPAIGN_CHANNELS
            ],
        }
    )
    return values


def _allowed_values(options: dict[str, Any]) -> dict[str, set[str]]:
    return {
        "product_ids": {item["product_id"] for item in options["products"]},
        "campaign_types": set(options["campaign_types"]),
        "campaign_categories": set(options["campaign_categories"]),
        "offer_types": set(options["offer_types"]),
        "campaign_channels": set(options["historical_campaign_channels"]),
    }


def get_campaign_context_options(database_path: str | Path) -> dict[str, Any]:
    path = initialize_database(database_path)
    return _load_options(CampaignTargetingContextRepository(path))


_MATCH_STRENGTH_LABELS = {
    "VERY_STRONG": "Very Strong Match — 0.90+",
    "STRONG": "Strong Match — 0.80+",
    "GOOD": "Good Match — 0.70+",
    "BROAD": "Broad Match — 0.60+",
}


def _band_payload(band) -> dict[str, Any]:
    return {
        "value": band.value,
        "label": band.label,
        "minimum": band.minimum,
        "maximum": band.maximum,
        "maximum_inclusive": band.maximum_inclusive,
    }


def _load_targeting_options(
    repository: CampaignTargetingContextRepository,
) -> dict[str, Any]:
    values = repository.fetch_targeting_options()
    values.update(
        {
            "targeting_segment_contract_version": TARGETING_SEGMENT_CONTRACT_VERSION,
            "business_match_strength_contract_version": (
                BUSINESS_MATCH_STRENGTH_CONTRACT_VERSION
            ),
            "age_bucket_contract_version": AGE_BUCKET_CONTRACT_VERSION,
            "income_group_contract_version": INCOME_GROUP_CONTRACT_VERSION,
            "default_match_strength": DEFAULT_MATCH_STRENGTH,
            "match_strengths": [
                {
                    "value": value,
                    "label": _MATCH_STRENGTH_LABELS[value],
                    "minimum_score": minimum,
                    "recommended": value == DEFAULT_MATCH_STRENGTH,
                }
                for value, minimum in MATCH_STRENGTH_THRESHOLDS.items()
            ],
            "age_groups": [_band_payload(band) for band in AGE_BUCKETS],
            "income_groups": [_band_payload(band) for band in INCOME_GROUPS],
        }
    )
    return values


def _targeting_allowed_values(options: dict[str, Any]) -> dict[str, set[str]]:
    return {
        "gender": set(options["genders"]),
        "state": set(options["states"]),
        "marital_status": set(options["marital_statuses"]),
        "education": set(options["education_levels"]),
        "employment_status": set(options["employment_statuses"]),
        "resident_status": set(options["resident_statuses"]),
        "resident_type": set(options["resident_types"]),
        "type_of_employment": set(options["employment_types"]),
    }


def get_business_targeting_options(database_path: str | Path) -> dict[str, Any]:
    path = initialize_database(database_path)
    return _load_targeting_options(CampaignTargetingContextRepository(path))


_TARGETING_VERSION_FIELDS = {
    "targeting_segment_contract_version",
    "business_match_strength_contract_version",
    "age_bucket_contract_version",
    "income_group_contract_version",
    "audience_filter_contract_version",
}


def _serialize_targeting_row(row: dict[str, Any]) -> dict[str, Any]:
    try:
        stored = json.loads(str(row["targeting_criteria_json"]))
    except (TypeError, ValueError) as exc:
        raise CampaignContextServiceError(
            "The saved targeting criteria are not readable."
        ) from exc
    if not isinstance(stored, dict):
        raise CampaignContextServiceError("The saved targeting criteria are not readable.")

    raw_criteria = {
        key: value for key, value in stored.items() if key not in _TARGETING_VERSION_FIELDS
    }
    selected_as_allowed = {
        reference_field: set(raw_criteria.get(contract_field, []))
        for contract_field, reference_field in {
            "genders": "gender",
            "states": "state",
            "marital_statuses": "marital_status",
            "education_levels": "education",
            "employment_statuses": "employment_status",
            "resident_statuses": "resident_status",
            "resident_types": "resident_type",
            "employment_types": "type_of_employment",
        }.items()
    }
    try:
        normalized = normalize_business_targeting_criteria(
            raw_criteria,
            allowed_values=selected_as_allowed,
        )
    except CampaignTargetingContractValidationError as exc:
        raise CampaignContextServiceError(
            "The saved targeting criteria failed contract validation."
        ) from exc
    if (
        normalized.canonical_json != row["targeting_criteria_json"]
        or normalized.sha256 != row["targeting_criteria_sha256"]
    ):
        raise CampaignContextServiceError(
            "The saved targeting criteria failed integrity validation."
        )
    return {
        "targeting_context_id": row["targeting_context_id"],
        "targeting_segment_contract_version": row[
            "targeting_segment_contract_version"
        ],
        "business_match_strength_contract_version": row[
            "business_match_strength_contract_version"
        ],
        "criteria": normalized.payload,
        "targeting_criteria_sha256": normalized.sha256,
        "audience_filter_branches": list(normalized.audience_filter_branches),
        "audience_selection": normalized.audience_selection,
        "source_scoring_run_id": row["source_scoring_run_id"],
        "updated_at": row["updated_at"],
    }


def get_business_targeting_criteria(
    database_path: str | Path, *, targeting_context_id: int
) -> dict[str, Any]:
    path = initialize_database(database_path)
    repository = CampaignTargetingContextRepository(path)
    row = repository.fetch_targeting_criteria(targeting_context_id)
    if row is None:
        raise CampaignContextNotFoundError("The requested campaign context was not found.")
    return _serialize_targeting_row(row)


def save_business_targeting_criteria(
    database_path: str | Path,
    raw_criteria: Any,
    *,
    targeting_context_id: int,
) -> dict[str, Any]:
    path = initialize_database(database_path)
    repository = CampaignTargetingContextRepository(path)
    options = _load_targeting_options(repository)
    try:
        normalized = normalize_business_targeting_criteria(
            raw_criteria,
            allowed_values=_targeting_allowed_values(options),
        )
    except CampaignTargetingContractValidationError as exc:
        raise CampaignContextValidationError(str(exc)) from exc

    updated = repository.update_targeting_criteria(
        targeting_context_id=targeting_context_id,
        targeting_segment_contract_version=TARGETING_SEGMENT_CONTRACT_VERSION,
        business_match_strength_contract_version=(
            BUSINESS_MATCH_STRENGTH_CONTRACT_VERSION
        ),
        targeting_criteria_json=normalized.canonical_json,
        targeting_criteria_sha256=normalized.sha256,
        timestamp=_timestamp(),
    )
    if not updated:
        raise CampaignContextNotFoundError("The requested campaign context was not found.")
    row = repository.fetch_targeting_criteria(targeting_context_id)
    if row is None:  # pragma: no cover
        raise CampaignContextServiceError("The saved targeting criteria could not be reopened.")
    return _serialize_targeting_row(row)


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    try:
        context = json.loads(str(row["campaign_context_json"]))
    except (TypeError, ValueError) as exc:
        raise CampaignContextServiceError(
            "The saved campaign context is not readable."
        ) from exc
    if not isinstance(context, dict):
        raise CampaignContextServiceError("The saved campaign context is not readable.")
    canonical_json = json.dumps(
        context,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    if digest != row["campaign_context_sha256"]:
        raise CampaignContextServiceError("The saved campaign context failed integrity validation.")
    return {
        "targeting_context_id": row["targeting_context_id"],
        "campaign_id": row["campaign_id"],
        "campaign_targeting_context_contract_version": row[
            "campaign_targeting_context_contract_version"
        ],
        "targeting_segment_contract_version": row["targeting_segment_contract_version"],
        "business_match_strength_contract_version": row[
            "business_match_strength_contract_version"
        ],
        "context": context,
        "campaign_context_sha256": row["campaign_context_sha256"],
        "source_scoring_run_id": row["source_scoring_run_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_campaign_targeting_context(
    database_path: str | Path, *, targeting_context_id: int
) -> dict[str, Any]:
    path = initialize_database(database_path)
    row = CampaignTargetingContextRepository(path).fetch_context(targeting_context_id)
    if row is None:
        raise CampaignContextNotFoundError("The requested campaign context was not found.")
    return _serialize_row(row)


def save_campaign_targeting_context(
    database_path: str | Path,
    raw_context: Any,
    *,
    targeting_context_id: int | None = None,
) -> dict[str, Any]:
    path = initialize_database(database_path)
    repository = CampaignTargetingContextRepository(path)
    options = _load_options(repository)
    try:
        normalized = normalize_campaign_targeting_context(
            raw_context,
            allowed_values=_allowed_values(options),
        )
    except CampaignTargetingContractValidationError as exc:
        raise CampaignContextValidationError(str(exc)) from exc

    timestamp = _timestamp()
    if targeting_context_id is None:
        default_criteria = normalize_business_targeting_criteria({}, allowed_values={})
        targeting_context_id = repository.create_context(
            campaign_context_contract_version=CAMPAIGN_TARGETING_CONTEXT_CONTRACT_VERSION,
            targeting_segment_contract_version=TARGETING_SEGMENT_CONTRACT_VERSION,
            business_match_strength_contract_version=(
                BUSINESS_MATCH_STRENGTH_CONTRACT_VERSION
            ),
            campaign_context_json=normalized.canonical_json,
            campaign_context_sha256=normalized.sha256,
            targeting_criteria_json=default_criteria.canonical_json,
            targeting_criteria_sha256=default_criteria.sha256,
            timestamp=timestamp,
        )
    else:
        updated = repository.update_context(
            targeting_context_id=targeting_context_id,
            campaign_context_contract_version=CAMPAIGN_TARGETING_CONTEXT_CONTRACT_VERSION,
            campaign_context_json=normalized.canonical_json,
            campaign_context_sha256=normalized.sha256,
            timestamp=timestamp,
        )
        if not updated:
            raise CampaignContextNotFoundError("The requested campaign context was not found.")

    row = repository.fetch_context(targeting_context_id)
    if row is None:  # pragma: no cover - defensive against external database mutation
        raise CampaignContextServiceError("The saved campaign context could not be reopened.")
    return _serialize_row(row)


__all__ = (
    "CampaignContextNotFoundError",
    "CampaignContextServiceError",
    "CampaignContextValidationError",
    "get_campaign_context_options",
    "get_campaign_targeting_context",
    "get_business_targeting_criteria",
    "get_business_targeting_options",
    "save_campaign_targeting_context",
    "save_business_targeting_criteria",
)
