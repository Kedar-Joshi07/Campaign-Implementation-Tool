"""Phase 9 orchestration for immutable Target Groups and Campaign drafts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories.campaign_targeting_context_repository import (
    CampaignTargetingContextRepository,
)
from app.services.audience_query_service import (
    _categorical_vocabularies_from_snapshot,
    normalize_audience_filters,
)
from app.services.campaign_service import (
    CampaignServiceConflictError,
    CampaignServiceError,
    CampaignServiceValidationError,
    create_campaign,
    get_campaign,
    update_campaign,
)
from app.services.campaign_targeting_context_service import (
    CampaignContextNotFoundError,
    CampaignContextServiceError,
    CampaignContextValidationError,
)
from app.services.saved_audience_service import (
    SavedAudienceServiceConflictError,
    SavedAudienceServiceError,
    SavedAudienceServiceValidationError,
    get_saved_audience_detail,
    save_resolved_audience_definition,
)
from app.services.target_group_preview_service import (
    TARGET_GROUP_PREVIEW_CONTRACT_VERSION,
    _materialize_business_selection,
    _preview_inputs,
)
from app.services.targeting_intelligence_service import resolve_targeting_intelligence


TARGET_GROUP_CAMPAIGN_CONTRACT_VERSION = "1"
SAVED_TARGET_GROUP_CONTRACT_VERSION = "1"


class TargetGroupCampaignConflictError(CampaignContextServiceError):
    pass


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalized_branches(criteria_response: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = [
        normalize_audience_filters(branch).payload
        for branch in criteria_response["audience_filter_branches"]
    ]
    if not normalized:
        raise CampaignContextValidationError(
            "Targeting preferences do not contain a usable target-group definition."
        )
    return normalized


def _decode_and_verify(raw: Any, digest: Any, *, label: str) -> Any:
    try:
        decoded = json.loads(str(raw))
    except (TypeError, ValueError) as exc:
        raise TargetGroupCampaignConflictError(
            f"Saved {label} is not readable."
        ) from exc
    if _sha256(decoded) != str(digest).strip().lower():
        raise TargetGroupCampaignConflictError(
            f"Saved {label} failed integrity validation."
        )
    return decoded


def _build_response(
    path: Path,
    *,
    targeting_context_id: int,
    campaign: dict[str, Any],
    metadata: dict[str, Any],
    campaign_created: bool,
    idempotent_replay: bool,
) -> dict[str, Any]:
    if str(metadata["target_group_contract_version"]) != (
        SAVED_TARGET_GROUP_CONTRACT_VERSION
    ):
        raise TargetGroupCampaignConflictError(
            "Saved Target Group contract version is not supported."
        )
    if int(metadata["targeting_context_id"]) != targeting_context_id:
        raise TargetGroupCampaignConflictError(
            "Saved Target Group is linked to a different campaign context."
        )
    audience_id = int(metadata["audience_id"])
    audience = get_saved_audience_detail(path, audience_id=audience_id)
    context = _decode_and_verify(
        metadata["campaign_context_json"],
        metadata["campaign_context_sha256"],
        label="campaign context",
    )
    criteria = _decode_and_verify(
        metadata["targeting_criteria_json"],
        metadata["targeting_criteria_sha256"],
        label="targeting criteria",
    )
    branches = _decode_and_verify(
        metadata["filter_branches_json"],
        metadata["filter_branches_sha256"],
        label="Target Group filter definition",
    )
    if not isinstance(branches, list) or not branches:
        raise TargetGroupCampaignConflictError(
            "Saved Target Group filter definition is not readable."
        )
    selected_count = int(metadata["resolved_count"])
    source_id = int(metadata["source_scoring_run_id"])
    if (
        selected_count != int(audience["definition"]["resolved_count"])
        or selected_count != int(campaign["saved_audience_resolved_count"])
        or audience_id != int(campaign["saved_audience_id"])
        or source_id != int(audience["definition"]["scoring_run_id"])
        or source_id != int(campaign["scoring_run_id"])
    ):
        raise TargetGroupCampaignConflictError(
            "Saved Target Group count, source, or campaign linkage failed integrity "
            "validation."
        )
    resolution = resolve_targeting_intelligence(
        path, targeting_context_id=targeting_context_id
    )
    is_current = bool(audience["currentness"]["is_current"]) and bool(
        campaign["currentness"]["is_current"]
    )
    is_current = (
        is_current
        and resolution.status == "READY"
        and resolution.technical_details is not None
        and int(resolution.technical_details.get("scoring_run_id") or 0) == source_id
    )
    return {
        "target_group_campaign_contract_version": (
            TARGET_GROUP_CAMPAIGN_CONTRACT_VERSION
        ),
        "targeting_context_id": targeting_context_id,
        "campaign_created": campaign_created,
        "idempotent_replay": idempotent_replay,
        "targeting_source_status": resolution.status,
        "campaign_context": context,
        "targeting_criteria": criteria,
        "saved_target_group": {
            "saved_target_group_id": audience_id,
            "name": audience["audience_name"],
            "description": audience["description"],
            "selected_count": selected_count,
            "filter_hash": str(metadata["filter_branches_sha256"]),
            "filter_branch_count": len(branches),
            "immutable": True,
            "currentness": "UP_TO_DATE" if is_current else "NEEDS_REFRESH",
            "currentness_label": "Up to date" if is_current else "Needs refresh",
            "created_at": audience["created_at"],
        },
        "campaign": campaign,
        "technical_details": {
            **(resolution.technical_details or {}),
            "source_status": resolution.status,
            "source_currentness": (
                "UP_TO_DATE" if resolution.status == "READY" else "NEEDS_REFRESH"
            ),
            "audience_filter_hash": str(metadata["filter_branches_sha256"]),
            "saved_audience_id": audience_id,
            "targeting_intelligence_resolution_contract_version": (
                resolution.targeting_intelligence_resolution_contract_version
            ),
            "campaign_targeting_context_contract_version": str(
                metadata["campaign_context_contract_version"]
            ),
            "targeting_segment_contract_version": str(
                metadata["targeting_segment_contract_version"]
            ),
            "business_match_strength_contract_version": str(
                metadata["business_match_strength_contract_version"]
            ),
            "audience_filter_contract_version": str(
                criteria["audience_filter_contract_version"]
            ),
            "target_group_preview_contract_version": (
                TARGET_GROUP_PREVIEW_CONTRACT_VERSION
            ),
            "target_group_campaign_contract_version": (
                TARGET_GROUP_CAMPAIGN_CONTRACT_VERSION
            ),
            "saved_target_group_contract_version": (
                SAVED_TARGET_GROUP_CONTRACT_VERSION
            ),
        },
    }


def _saved_target_group_matches(
    path: Path,
    *,
    metadata: dict[str, Any],
    context_row: dict[str, Any],
    source_id: int,
    branches_hash: str,
    request_payload: dict[str, Any],
) -> bool:
    """Return whether a saved group is the same immutable save request."""

    if (
        str(metadata.get("target_group_contract_version"))
        != SAVED_TARGET_GROUP_CONTRACT_VERSION
        or int(metadata.get("targeting_context_id") or 0)
        != int(context_row["targeting_context_id"])
        or str(metadata.get("campaign_context_sha256"))
        != str(context_row["campaign_context_sha256"])
        or str(metadata.get("targeting_criteria_sha256"))
        != str(context_row["targeting_criteria_sha256"])
        or str(metadata.get("filter_branches_sha256")) != branches_hash
        or int(metadata.get("source_scoring_run_id") or 0) != source_id
    ):
        return False
    try:
        audience = get_saved_audience_detail(
            path, audience_id=int(metadata["audience_id"])
        )
    except SavedAudienceServiceError:
        return False
    return (
        audience["audience_name"] == request_payload["target_group_name"]
        and audience.get("description")
        == request_payload.get("target_group_description")
    )


def _campaign_matches_request(
    campaign: dict[str, Any], *, request_payload: dict[str, Any], channel: str
) -> bool:
    return (
        campaign["campaign_name"] == request_payload["campaign_name"]
        and campaign.get("description") == request_payload.get("campaign_description")
        and campaign["channel"] == channel
        and campaign.get("planned_launch_date")
        == request_payload.get("planned_launch_date")
    )


def save_target_group_and_create_campaign_draft(
    database_path: str | Path,
    *,
    targeting_context_id: int,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    path, _resolution, criteria_response, audience_context = _preview_inputs(
        database_path, targeting_context_id=targeting_context_id
    )
    repository = CampaignTargetingContextRepository(path)
    context_row = repository.fetch_context(targeting_context_id)
    if context_row is None:
        raise CampaignContextNotFoundError(
            "The requested campaign context was not found."
        )
    if (
        str(context_row["targeting_criteria_sha256"])
        != str(criteria_response["targeting_criteria_sha256"])
    ):
        raise TargetGroupCampaignConflictError(
            "Targeting preferences changed while the Target Group was being prepared."
        )

    branches = _normalized_branches(criteria_response)
    branches_hash = _sha256(branches)
    source_id = int(audience_context.scoring_row["scoring_run_id"])
    context = json.loads(str(context_row["campaign_context_json"]))
    channel = str(context["campaign_channel"])
    existing_campaign_id = context_row.get("campaign_id")
    existing_campaign: dict[str, Any] | None = None
    if existing_campaign_id is not None:
        try:
            existing_campaign = get_campaign(
                path, campaign_id=int(existing_campaign_id)
            )
        except CampaignServiceError as exc:
            raise TargetGroupCampaignConflictError(
                "The existing Campaign draft could not be reopened. Try again."
            ) from exc
        if existing_campaign["status"] != "DRAFT":
            raise TargetGroupCampaignConflictError(
                "Only a Draft Campaign can be updated with a new Saved Target Group."
            )

        existing_metadata = repository.fetch_saved_target_group(
            int(existing_campaign["saved_audience_id"])
        )
        if existing_metadata is not None and _saved_target_group_matches(
            path,
            metadata=existing_metadata,
            context_row=context_row,
            source_id=source_id,
            branches_hash=branches_hash,
            request_payload=request_payload,
        ):
            if _campaign_matches_request(
                existing_campaign,
                request_payload=request_payload,
                channel=channel,
            ):
                return _build_response(
                    path,
                    targeting_context_id=targeting_context_id,
                    campaign=existing_campaign,
                    metadata=existing_metadata,
                    campaign_created=False,
                    idempotent_replay=True,
                )
            campaign_payload = {
                "campaign_name": request_payload["campaign_name"],
                "description": request_payload.get("campaign_description"),
                "channel": channel,
                "planned_launch_date": request_payload.get("planned_launch_date"),
                "saved_audience_id": int(existing_metadata["audience_id"]),
            }
            try:
                updated_campaign = update_campaign(
                    path,
                    campaign_id=int(existing_campaign_id),
                    request_payload=campaign_payload,
                )
            except CampaignServiceError as exc:
                raise TargetGroupCampaignConflictError(
                    "The Target Group is saved, but the Campaign draft could not "
                    "be updated. Your inputs are preserved; try again."
                ) from exc
            return _build_response(
                path,
                targeting_context_id=targeting_context_id,
                campaign=updated_campaign,
                metadata=existing_metadata,
                campaign_created=False,
                idempotent_replay=False,
            )

    reusable_metadata: dict[str, Any] | None = None
    if existing_campaign_id is None:
        candidate = repository.fetch_latest_saved_target_group_for_context(
            targeting_context_id
        )
        if candidate is not None and _saved_target_group_matches(
            path,
            metadata=candidate,
            context_row=context_row,
            source_id=source_id,
            branches_hash=branches_hash,
            request_payload=request_payload,
        ):
            reusable_metadata = candidate

    audience: dict[str, Any]
    resolved_count: int
    if reusable_metadata is not None:
        audience = get_saved_audience_detail(
            path, audience_id=int(reusable_metadata["audience_id"])
        )
        resolved_count = int(reusable_metadata["resolved_count"])
    else:
        with get_connection(path) as connection:
            selected_table = _materialize_business_selection(
                connection,
                scoring_run_id=source_id,
                filter_branches=branches,
                selection=criteria_response["audience_selection"],
                boundaries=audience_context.boundaries,
                categorical_vocabularies=_categorical_vocabularies_from_snapshot(
                    audience_context.analytics_snapshot
                ),
                universe_count=int(audience_context.scoring_row["scored_person_count"]),
            )
            resolved_count = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM {selected_table}"
                ).fetchone()[0]
            )
        if resolved_count < 1:
            raise CampaignContextValidationError(
                "This Target Group contains exactly 0 people and cannot be saved. "
                "Broaden the targeting preferences and refresh the preview."
            )
        try:
            audience = save_resolved_audience_definition(
                path,
                audience_name=request_payload["target_group_name"],
                description=request_payload.get("target_group_description"),
                scoring_run_id=source_id,
                filters=branches[0],
                selection=criteria_response["audience_selection"],
                resolved_count=resolved_count,
            )
        except SavedAudienceServiceValidationError as exc:
            raise CampaignContextValidationError(
                "The Target Group could not be saved. Review its name and "
                "description, then try again."
            ) from exc
        except SavedAudienceServiceConflictError as exc:
            raise TargetGroupCampaignConflictError(
                "Targeting intelligence needs to be refreshed before this Target "
                "Group can be saved."
            ) from exc

    audience_id = int(audience["audience_id"])
    branches_json = _canonical_json(branches)
    created_at = str(audience["created_at"])
    if reusable_metadata is None:
        repository.create_saved_target_group(
            audience_id=audience_id,
            targeting_context_id=targeting_context_id,
            target_group_contract_version=SAVED_TARGET_GROUP_CONTRACT_VERSION,
            filter_branches_json=branches_json,
            filter_branches_sha256=branches_hash,
            campaign_context_contract_version=str(
                context_row["campaign_targeting_context_contract_version"]
            ),
            campaign_context_json=str(context_row["campaign_context_json"]),
            campaign_context_sha256=str(context_row["campaign_context_sha256"]),
            targeting_segment_contract_version=str(
                context_row["targeting_segment_contract_version"]
            ),
            business_match_strength_contract_version=str(
                context_row["business_match_strength_contract_version"]
            ),
            targeting_criteria_json=str(context_row["targeting_criteria_json"]),
            targeting_criteria_sha256=str(context_row["targeting_criteria_sha256"]),
            source_scoring_run_id=source_id,
            resolved_count=resolved_count,
            created_at=created_at,
        )

    campaign_payload = {
        "campaign_name": request_payload["campaign_name"],
        "description": request_payload.get("campaign_description"),
        "channel": channel,
        "planned_launch_date": request_payload.get("planned_launch_date"),
        "saved_audience_id": audience_id,
    }
    try:
        if existing_campaign_id is None:
            campaign = create_campaign(path, campaign_payload)
            campaign_created = True
            attached = repository.attach_campaign(
                targeting_context_id=targeting_context_id,
                campaign_id=int(campaign["campaign_id"]),
                timestamp=_timestamp(),
            )
            if not attached:
                raise TargetGroupCampaignConflictError(
                    "Campaign context could not be linked to the new draft."
                )
        else:
            campaign = update_campaign(
                path,
                campaign_id=int(existing_campaign_id),
                request_payload=campaign_payload,
            )
            campaign_created = False
    except (CampaignServiceValidationError, CampaignServiceConflictError) as exc:
        raise TargetGroupCampaignConflictError(
            "The Target Group is saved, but the Campaign draft could not be "
            "created or updated. Your inputs are preserved; try again."
        ) from exc
    except CampaignServiceError as exc:
        raise TargetGroupCampaignConflictError(
            "The Target Group is saved, but the Campaign draft could not be "
            "created or updated. Your inputs are preserved; try again."
        ) from exc

    metadata = repository.fetch_saved_target_group(audience_id)
    if metadata is None:
        raise TargetGroupCampaignConflictError(
            "Saved Target Group metadata could not be reopened."
        )
    return _build_response(
        path,
        targeting_context_id=targeting_context_id,
        campaign=campaign,
        metadata=metadata,
        campaign_created=campaign_created,
        idempotent_replay=reusable_metadata is not None,
    )


def reopen_phase9_campaign_draft(
    database_path: str | Path, *, targeting_context_id: int
) -> dict[str, Any]:
    path = initialize_database(database_path)
    repository = CampaignTargetingContextRepository(path)
    context_row = repository.fetch_context(targeting_context_id)
    if context_row is None:
        raise CampaignContextNotFoundError(
            "The requested campaign context was not found."
        )
    if context_row.get("campaign_id") is None:
        raise CampaignContextNotFoundError(
            "No Campaign draft has been created for this planning context."
        )
    try:
        campaign = get_campaign(path, campaign_id=int(context_row["campaign_id"]))
    except CampaignServiceError as exc:
        raise TargetGroupCampaignConflictError(str(exc)) from exc
    metadata = repository.fetch_saved_target_group(int(campaign["saved_audience_id"]))
    if metadata is None:
        raise TargetGroupCampaignConflictError(
            "Campaign draft is not linked to a Saved Target Group."
        )
    try:
        return _build_response(
            path,
            targeting_context_id=targeting_context_id,
            campaign=campaign,
            metadata=metadata,
            campaign_created=False,
            idempotent_replay=False,
        )
    except SavedAudienceServiceError as exc:
        raise TargetGroupCampaignConflictError(str(exc)) from exc


__all__ = (
    "SAVED_TARGET_GROUP_CONTRACT_VERSION",
    "TARGET_GROUP_CAMPAIGN_CONTRACT_VERSION",
    "TargetGroupCampaignConflictError",
    "reopen_phase9_campaign_draft",
    "save_target_group_and_create_campaign_draft",
)
