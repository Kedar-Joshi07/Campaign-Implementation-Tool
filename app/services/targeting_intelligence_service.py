"""Explicit Phase 9 targeting-intelligence linkage and resolution boundary."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.database.schema import initialize_database
from app.repositories.campaign_targeting_context_repository import (
    CampaignTargetingContextRepository,
)
from app.services.campaign_targeting_context_service import (
    CampaignContextNotFoundError,
    CampaignContextServiceError,
    CampaignContextValidationError,
)
from app.services.audience_preparation_service import (
    AudiencePreparationServiceError,
    get_audience_preparation_status,
)
from app.services.prospect_scoring_service import (
    ProspectScoringVerificationError,
    resolve_current_scoring_context_lightweight,
)


TARGETING_INTELLIGENCE_RESOLUTION_CONTRACT_VERSION = "1"
TargetingStatus = Literal[
    "READY",
    "NEEDS_REFRESH",
    "NOT_AVAILABLE",
    "INCOMPATIBLE_CONTEXT",
    "STALE",
]


@dataclass(frozen=True)
class TargetingIntelligenceResolution:
    targeting_intelligence_resolution_contract_version: str
    targeting_context_id: int
    status: TargetingStatus
    message: str
    explanation: str
    explicitly_linked: bool
    can_preview: bool
    context_specific: bool
    context_changed_source: bool
    compatibility_checked_dimensions: list[str]
    issues: list[str]
    technical_details: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _resolution(
    *,
    targeting_context_id: int,
    status: TargetingStatus,
    explanation: str,
    explicitly_linked: bool,
    context_specific: bool = False,
    checked_dimensions: list[str] | None = None,
    issues: list[str] | None = None,
    technical_details: dict[str, Any] | None = None,
) -> TargetingIntelligenceResolution:
    messages = {
        "READY": "Targeting intelligence is ready",
        "NEEDS_REFRESH": "Targeting intelligence needs refresh",
        "NOT_AVAILABLE": "Targeting is not yet available for this campaign",
        "INCOMPATIBLE_CONTEXT": "Targeting is not yet available for this campaign",
        "STALE": "Targeting intelligence needs refresh",
    }
    return TargetingIntelligenceResolution(
        targeting_intelligence_resolution_contract_version=(
            TARGETING_INTELLIGENCE_RESOLUTION_CONTRACT_VERSION
        ),
        targeting_context_id=targeting_context_id,
        status=status,
        message=messages[status],
        explanation=explanation,
        explicitly_linked=explicitly_linked,
        can_preview=status == "READY",
        context_specific=context_specific,
        context_changed_source=False,
        compatibility_checked_dimensions=checked_dimensions or [],
        issues=list(dict.fromkeys((issues or [])[:20])),
        technical_details=technical_details,
    )


def _decode_object(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return None
    return decoded if isinstance(decoded, dict) else None


def _technical_details(source: dict[str, Any]) -> dict[str, Any]:
    summary = _decode_object(source.get("score_summary_json")) or {}
    return {
        "analysis_run_id": source.get("analysis_run_id"),
        "model_run_id": source.get("model_run_id"),
        "scoring_run_id": source.get("scoring_run_id"),
        "selected_candidate": source.get("selected_candidate"),
        "model_role_policy_version": source.get("model_role_policy_version"),
        "feature_contract_version": source.get("feature_contract_version"),
        "feature_contract_sha256": source.get("feature_contract_sha256"),
        "artifact_sha256": source.get("artifact_sha256"),
        "customer_source_checksum": summary.get("customer_source_checksum"),
        "campaign_sales_source_checksum": summary.get(
            "campaign_sales_source_checksum"
        ),
        "demographic_source_checksum": summary.get("demographic_source_checksum"),
    }


def _context_compatibility(
    context: dict[str, Any], source: dict[str, Any]
) -> tuple[bool, bool, list[str], list[str]]:
    """Conservatively compare only exact Phase 9/analysis dimensions.

    Phase 10 may replace this evaluator with automatic source discovery and a richer
    compatibility contract. Delivery channel is deliberately not compared with an
    analysis campaign-channel filter.
    """

    filters = _decode_object(source.get("analysis_filters_json"))
    if filters is None:
        return False, False, [], ["source analysis filters are unavailable"]

    mappings = (
        ("product_ids", "product_ids", "products"),
        ("campaign_types", "campaign_types", "campaign types"),
        (
            "historical_campaign_channels",
            "campaign_channels",
            "historical campaign channels",
        ),
    )
    compatible = True
    context_specific = False
    checked: list[str] = []
    issues: list[str] = []
    for context_field, source_field, label in mappings:
        source_values = filters.get(source_field) or []
        if not isinstance(source_values, list):
            compatible = False
            issues.append(f"source {label} filter is invalid")
            continue
        if not source_values:
            continue
        context_specific = True
        checked.append(label)
        context_values = context.get(context_field) or []
        if not isinstance(context_values, list) or not context_values:
            compatible = False
            issues.append(f"campaign context does not specify source-filtered {label}")
            continue
        unsupported = sorted(set(context_values) - set(source_values))
        if unsupported:
            compatible = False
            issues.append(
                f"campaign {label} are outside the linked source scope: "
                + ", ".join(unsupported)
            )

    for source_field, label in (
        ("campaign_ids", "campaign IDs"),
        ("product_categories", "product categories"),
    ):
        source_values = filters.get(source_field) or []
        if source_values:
            context_specific = True
            compatible = False
            issues.append(
                f"linked source is restricted by {label}, which Phase 9 cannot "
                "verify against this campaign context"
            )
    return compatible, context_specific, checked, issues


def _resolve_for_source(
    database_path: Path,
    repository: CampaignTargetingContextRepository,
    *,
    targeting_context_id: int,
    context_row: dict[str, Any],
    scoring_run_id: int | None,
) -> TargetingIntelligenceResolution:
    if scoring_run_id is None:
        return _resolution(
            targeting_context_id=targeting_context_id,
            status="NOT_AVAILABLE",
            explanation=(
                "Campaign context and targeting preferences can be saved, but exact "
                "preview remains unavailable until an analyst links a verified source."
            ),
            explicitly_linked=False,
        )

    source = repository.fetch_targeting_source_details(scoring_run_id)
    if source is None:
        return _resolution(
            targeting_context_id=targeting_context_id,
            status="NOT_AVAILABLE",
            explanation="The explicitly linked targeting source is no longer available.",
            explicitly_linked=True,
            issues=["linked scoring run was not found"],
        )
    technical = _technical_details(source)
    if source.get("scoring_status") != "COMPLETED":
        return _resolution(
            targeting_context_id=targeting_context_id,
            status="NEEDS_REFRESH",
            explanation=(
                "The explicitly linked targeting source has not completed successfully. "
                "Prepare and verify targeting intelligence before previewing exact results."
            ),
            explicitly_linked=True,
            issues=[f"linked scoring status is {source.get('scoring_status')}"],
            technical_details=technical,
        )

    try:
        currentness = resolve_current_scoring_context_lightweight(
            database_path,
            scoring_run_id=scoring_run_id,
            verify_current_source_match=True,
        )
    except ProspectScoringVerificationError as exc:
        return _resolution(
            targeting_context_id=targeting_context_id,
            status="STALE",
            explanation=(
                "The explicitly linked source could not be verified against current data "
                "and model provenance. Refresh targeting intelligence before preview."
            ),
            explicitly_linked=True,
            issues=[str(exc)],
            technical_details=technical,
        )
    if not currentness.get("is_canonical"):
        return _resolution(
            targeting_context_id=targeting_context_id,
            status="STALE",
            explanation=(
                "The explicitly linked source no longer matches current verified data and "
                "model provenance. Refresh targeting intelligence before preview."
            ),
            explicitly_linked=True,
            issues=[str(item) for item in currentness.get("issues", [])],
            technical_details=technical,
        )

    try:
        preparation = get_audience_preparation_status(
            database_path,
            scoring_run_id=scoring_run_id,
        )
    except AudiencePreparationServiceError as exc:
        return _resolution(
            targeting_context_id=targeting_context_id,
            status="NEEDS_REFRESH",
            explanation=(
                "The linked source is verified, but target-group rankings and profiles "
                "must be prepared before exact preview."
            ),
            explicitly_linked=True,
            issues=[str(exc)],
            technical_details=technical,
        )
    if not preparation.get("ready_for_current_audience_actions"):
        issues = [str(item) for item in preparation.get("currentness_issues", [])]
        if not preparation.get("prepared"):
            issues.append("targeting rank boundaries are not prepared")
        if not preparation.get("analytics_prepared"):
            issues.append("targeting profile analytics are not prepared")
        return _resolution(
            targeting_context_id=targeting_context_id,
            status="NEEDS_REFRESH",
            explanation=(
                "The linked source is verified, but target-group rankings and profiles "
                "need refresh before exact preview."
            ),
            explicitly_linked=True,
            issues=issues,
            technical_details=technical,
        )

    context = _decode_object(context_row.get("campaign_context_json"))
    if context is None:
        raise CampaignContextServiceError("The saved campaign context is not readable.")
    compatible, context_specific, checked, compatibility_issues = _context_compatibility(
        context, source
    )
    if not compatible:
        return _resolution(
            targeting_context_id=targeting_context_id,
            status="INCOMPATIBLE_CONTEXT",
            explanation=(
                "The linked source is current and verified, but its recorded analysis scope "
                "is not compatible with this campaign context. No exact preview is allowed."
            ),
            explicitly_linked=True,
            context_specific=context_specific,
            checked_dimensions=checked,
            issues=compatibility_issues,
            technical_details=technical,
        )

    specificity = (
        "Its recorded source filters are compatible with the campaign context."
        if context_specific
        else "It is general targeting intelligence and is not product-specific."
    )
    return _resolution(
        targeting_context_id=targeting_context_id,
        status="READY",
        explanation=(
            "A current, verified scoring source is explicitly linked. "
            f"{specificity} Campaign context did not change or retrain this source."
        ),
        explicitly_linked=True,
        context_specific=context_specific,
        checked_dimensions=checked,
        technical_details=technical,
    )


def resolve_targeting_intelligence(
    database_path: str | Path, *, targeting_context_id: int
) -> TargetingIntelligenceResolution:
    """Resolve only the source attached to this context; never choose latest/first."""

    path = initialize_database(database_path)
    repository = CampaignTargetingContextRepository(path)
    context_row = repository.fetch_context(targeting_context_id)
    if context_row is None:
        raise CampaignContextNotFoundError("The requested campaign context was not found.")
    source_id = context_row.get("source_scoring_run_id")
    return _resolve_for_source(
        path,
        repository,
        targeting_context_id=targeting_context_id,
        context_row=context_row,
        scoring_run_id=int(source_id) if source_id is not None else None,
    )


def link_targeting_intelligence(
    database_path: str | Path,
    *,
    targeting_context_id: int,
    scoring_run_id: int,
) -> TargetingIntelligenceResolution:
    """Advanced analyst/admin linkage; normal business UI never accepts raw IDs."""

    path = initialize_database(database_path)
    repository = CampaignTargetingContextRepository(path)
    context_row = repository.fetch_context(targeting_context_id)
    if context_row is None:
        raise CampaignContextNotFoundError("The requested campaign context was not found.")
    candidate = _resolve_for_source(
        path,
        repository,
        targeting_context_id=targeting_context_id,
        context_row=context_row,
        scoring_run_id=scoring_run_id,
    )
    if candidate.status not in {"READY", "INCOMPATIBLE_CONTEXT"}:
        raise CampaignContextValidationError(
            "Only a current, verified scoring source can be explicitly linked."
        )
    if not repository.set_source_scoring_run_id(
        targeting_context_id=targeting_context_id,
        scoring_run_id=scoring_run_id,
        timestamp=_timestamp(),
    ):
        raise CampaignContextNotFoundError("The requested campaign context was not found.")
    return candidate


def unlink_targeting_intelligence(
    database_path: str | Path,
    *,
    targeting_context_id: int,
) -> TargetingIntelligenceResolution:
    path = initialize_database(database_path)
    repository = CampaignTargetingContextRepository(path)
    if not repository.set_source_scoring_run_id(
        targeting_context_id=targeting_context_id,
        scoring_run_id=None,
        timestamp=_timestamp(),
    ):
        raise CampaignContextNotFoundError("The requested campaign context was not found.")
    return resolve_targeting_intelligence(path, targeting_context_id=targeting_context_id)


__all__ = (
    "TARGETING_INTELLIGENCE_RESOLUTION_CONTRACT_VERSION",
    "TargetingIntelligenceResolution",
    "link_targeting_intelligence",
    "resolve_targeting_intelligence",
    "unlink_targeting_intelligence",
)
