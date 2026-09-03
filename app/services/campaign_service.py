"""Phase 7 campaign service with deterministic member resolution and streaming export."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Iterator

from fastapi import Request
from fastapi.responses import StreamingResponse

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories.audience_rank_repository import AudienceRankRepository
from app.repositories.campaign_export_repository import (
    CampaignExportNotFoundError,
    CampaignExportRepository,
    CampaignExportValidationError,
    EXPORT_CURRENTNESS_STATE_CURRENT,
    EXPORT_CURRENTNESS_STATE_STALE,
    EXPORT_CURRENTNESS_STATE_UNKNOWN,
    EXPORT_RECOVERY_INTERRUPTED_MESSAGE,
)
from app.repositories.campaign_repository import (
    CampaignNotFoundError,
    CampaignRepository,
    CampaignValidationError,
)
from app.services.audience_preparation_service import (
    AUDIENCE_ANALYTICS_CONTRACT_VERSION,
    classify_decile,
    validate_audience_analytics_snapshot_currentness,
)
from app.services.audience_query_service import (
    AUDIENCE_FILTER_CONTRACT_VERSION,
    AUDIENCE_RANK_CONTRACT_VERSION,
    AUDIENCE_SELECTION_CONTRACT_VERSION,
    normalize_audience_filters,
    normalize_selection,
)
from app.services.audience_query_service import (
    _build_filter_predicates_split,
    _categorical_vocabularies_from_snapshot,
)
from app.services.campaign_contracts import (
    CAMPAIGN_CHANNEL_DIRECT_MAIL,
    CAMPAIGN_CHANNEL_EMAIL,
    CAMPAIGN_CHANNELS,
    CAMPAIGN_CONTRACT_VERSION,
    CAMPAIGN_EXPORT_CONTRACT_VERSION,
    CAMPAIGN_MEMBER_RESOLUTION_CONTRACT_VERSION,
    CAMPAIGN_STATUS_DRAFT,
    CAMPAIGN_STATUS_FINALIZED,
    CHANNEL_EXPORT_PROFILE,
    PROFILE_EXPORT_COLUMNS,
    EXPORT_PROFILE_DIRECT_MAIL_CONTACT_V1,
    EXPORT_PROFILE_EMAIL_CONTACT_V1,
)
from app.services.prospect_scoring_service import (
    ProspectScoringVerificationError,
    resolve_current_scoring_context_lightweight,
)
from app.services.saved_audience_service import (
    SavedAudienceServiceNotFoundError,
    SavedAudienceServiceValidationError,
    get_saved_audience_detail,
    list_saved_audiences,
    validate_saved_audience_currentness,
)


DEFAULT_CAMPAIGN_LIST_LIMIT = 20
MAXIMUM_CAMPAIGN_LIST_LIMIT = 100
DEFAULT_EXPORT_EVENT_LIST_LIMIT = 50
MAXIMUM_EXPORT_EVENT_LIST_LIMIT = 200
MEMBER_RESOLUTION_CHUNK_SIZE = 25_000
EXPORT_PROGRESS_UPDATE_CHUNK_INTERVAL = 3
MAX_CAMPAIGN_ISSUES = 12
CAMPAIGN_EXPORT_SNAPSHOT_CONTRACT_VERSION = "1"
CAMPAIGN_EXPORT_RECOVERY_THRESHOLD_SECONDS = 900

CAMPAIGN_NOT_FOUND_MESSAGE = "The requested campaign was not found."
CAMPAIGN_IMMUTABLE_MESSAGE = "FINALIZED campaigns are immutable."
CAMPAIGN_NOT_DRAFT_MESSAGE = "Only DRAFT campaigns can be modified."
CAMPAIGN_NOT_FINALIZED_MESSAGE = "Only FINALIZED campaigns can be exported."
CAMPAIGN_CURRENTNESS_REQUIRED_MESSAGE = "The campaign is not current and cannot be finalized or exported."
CAMPAIGN_PII_ACK_REQUIRED_MESSAGE = "acknowledge_pii must be true for export."
CAMPAIGN_EXPORT_FAILED_MESSAGE = "Campaign export failed safely."
CAMPAIGN_EXPORT_ABORTED_MESSAGE = "Campaign export was aborted before completion."
CAMPAIGN_EXPORT_LOCKED_MESSAGE = "Campaign export could not complete due to a database lock."
CAMPAIGN_EXPORT_EVENT_NOT_FOUND_MESSAGE = "Campaign export event was not found."

_EMAIL_REGEX = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$"
)


class CampaignServiceError(RuntimeError):
    """Base class for campaign service failures."""


class CampaignServiceValidationError(CampaignServiceError):
    """Raised for invalid request payloads and constraints."""


class CampaignServiceConflictError(CampaignServiceError):
    """Raised when campaign operations conflict with current state."""


class CampaignServiceNotFoundError(CampaignServiceError):
    """Raised when campaign or dependent resources are missing."""


class CampaignServiceUnavailableError(CampaignServiceError):
    """Raised when the operation is unavailable due to infrastructure state."""


class CampaignExportAbortedError(CampaignServiceError):
    """Raised when export streaming is cancelled or disconnected."""


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _require_positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CampaignServiceValidationError(f"{field_name} must be a positive integer.")
    return value


def _optional_bounded_text(value: Any, *, field_name: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CampaignServiceValidationError(f"{field_name} must be text when provided.")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise CampaignServiceValidationError(f"{field_name} must not exceed {maximum} characters.")
    return normalized


def _require_non_empty_text(value: Any, *, field_name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise CampaignServiceValidationError(f"{field_name} must be text.")
    normalized = value.strip()
    if not normalized:
        raise CampaignServiceValidationError(f"{field_name} must not be blank.")
    if len(normalized) > maximum:
        raise CampaignServiceValidationError(f"{field_name} must not exceed {maximum} characters.")
    return normalized


def _optional_iso_date(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CampaignServiceValidationError(f"{field_name} must be text when provided.")
    normalized = value.strip()
    if not normalized:
        return None
    try:
        parsed = datetime.strptime(normalized, "%Y-%m-%d")
    except ValueError as exc:
        raise CampaignServiceValidationError(f"{field_name} must be YYYY-MM-DD when provided.") from exc
    return parsed.strftime("%Y-%m-%d")


def _require_campaign_channel(value: Any) -> str:
    channel = _require_non_empty_text(value, field_name="channel", maximum=32).upper()
    if channel not in CAMPAIGN_CHANNELS:
        raise CampaignServiceValidationError("channel is invalid.")
    return channel


def _decode_json_object(raw_value: Any, *, field_name: str) -> dict[str, Any]:
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise CampaignServiceValidationError(f"{field_name} is missing.")
    try:
        decoded = json.loads(raw_value)
    except (TypeError, ValueError) as exc:
        raise CampaignServiceValidationError(f"{field_name} is invalid.") from exc
    if not isinstance(decoded, dict):
        raise CampaignServiceValidationError(f"{field_name} is invalid.")
    return decoded


def _bounded_issues(issues: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for issue in issues:
        normalized = str(issue).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
        if len(deduped) >= MAX_CAMPAIGN_ISSUES:
            break
    return deduped


def _rank_band_for_bucket(percentile_bucket: int) -> str:
    if percentile_bucket <= 1:
        return "ELITE"
    if percentile_bucket <= 5:
        return "VERY_HIGH"
    if percentile_bucket <= 10:
        return "HIGH"
    if percentile_bucket <= 25:
        return "MEDIUM"
    if percentile_bucket <= 50:
        return "LOW"
    return "VERY_LOW"


def _csv_safe_value(value: Any) -> str | int | float:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    stripped = text.lstrip()
    if stripped and stripped[0] in {"=", "+", "-", "@"}:
        return "'" + text
    return text


def _safe_export_error_message(exc: Exception) -> str:
    if isinstance(exc, CampaignExportAbortedError):
        return CAMPAIGN_EXPORT_ABORTED_MESSAGE
    if isinstance(exc, CampaignServiceConflictError):
        return str(exc)
    if isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc).lower():
        return CAMPAIGN_EXPORT_LOCKED_MESSAGE
    return CAMPAIGN_EXPORT_FAILED_MESSAGE


def _validate_email_deliverability(email: Any) -> bool:
    if not isinstance(email, str):
        return False
    normalized = email.strip()
    if not normalized:
        return False
    if len(normalized) > 320:
        return False
    return _EMAIL_REGEX.fullmatch(normalized) is not None


def _validate_direct_mail_deliverability(row: dict[str, Any]) -> bool:
    for field in ("address_line_1", "city", "state", "postal_code"):
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            return False
    return True


def _selection_json_from_payload(selection_payload: dict[str, Any]) -> str:
    return json.dumps(
        selection_payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _filter_hash_from_payload(filters_payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        filters_payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _provenance_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_list_bounds(*, limit: int, offset: int, maximum_limit: int) -> tuple[int, int]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= maximum_limit:
        raise CampaignServiceValidationError(
            f"limit must be an integer between 1 and {maximum_limit}."
        )
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise CampaignServiceValidationError("offset must be a non-negative integer.")
    return limit, offset


def _extract_saved_audience_snapshot(
    database_path: Path,
    *,
    saved_audience_id: int,
) -> dict[str, Any]:
    try:
        detail = get_saved_audience_detail(database_path, audience_id=saved_audience_id)
    except SavedAudienceServiceNotFoundError as exc:
        raise CampaignServiceNotFoundError("Saved audience was not found.") from exc
    except SavedAudienceServiceValidationError as exc:
        raise CampaignServiceValidationError(str(exc)) from exc

    filters_payload = detail["definition"]["filters"]
    selection_payload = detail["definition"]["selection"]

    normalized_filters = normalize_audience_filters(filters_payload)
    normalized_selection = normalize_selection(selection_payload)

    if int(detail["definition"]["resolved_count"]) <= 0:
        raise CampaignServiceConflictError("Saved audience resolved_count must be positive.")

    scoring_run_id = _require_positive_int(
        detail["definition"]["scoring_run_id"],
        field_name="saved_audience.scoring_run_id",
    )

    scoring_currentness: dict[str, Any]
    try:
        scoring_currentness = resolve_current_scoring_context_lightweight(
            database_path,
            scoring_run_id=scoring_run_id,
            verify_current_source_match=True,
        )
    except ProspectScoringVerificationError as exc:
        raise CampaignServiceConflictError("Saved audience scoring run could not be verified.") from exc

    try:
        analytics = validate_audience_analytics_snapshot_currentness(
            database_path,
            scoring_run_id=scoring_run_id,
            analytics_contract_version=AUDIENCE_ANALYTICS_CONTRACT_VERSION,
        )
    except Exception as exc:
        raise CampaignServiceConflictError("Saved audience analytics snapshot could not be verified.") from exc

    try:
        currentness = validate_saved_audience_currentness(
            database_path,
            audience_id=saved_audience_id,
        )
    except Exception as exc:
        raise CampaignServiceConflictError("Saved audience currentness could not be verified.") from exc

    rank_ready = len(AudienceRankRepository(database_path).fetch_boundaries(scoring_run_id)) == 100

    issues: list[str] = []
    if not bool(currentness["is_current"]):
        issues.extend([f"saved audience: {issue}" for issue in currentness.get("issues", [])])
    if not bool(scoring_currentness["is_canonical"]):
        issues.extend([f"scoring: {issue}" for issue in scoring_currentness.get("issues", [])])
    if not bool(analytics["analytics_prepared"]):
        issues.extend([f"analytics: {issue}" for issue in analytics.get("issues", [])])
    if not rank_ready:
        issues.append("rank boundaries are not prepared for this scoring run")

    contract_checks = {
        "filter_contract_version": detail["contracts"].get("filter_contract_version"),
        "rank_contract_version": detail["contracts"].get("rank_contract_version"),
        "selection_contract_version": detail["contracts"].get("selection_contract_version"),
    }
    if contract_checks["filter_contract_version"] != AUDIENCE_FILTER_CONTRACT_VERSION:
        issues.append("saved audience filter contract version is unsupported")
    if contract_checks["rank_contract_version"] != AUDIENCE_RANK_CONTRACT_VERSION:
        issues.append("saved audience rank contract version is unsupported")
    if contract_checks["selection_contract_version"] != AUDIENCE_SELECTION_CONTRACT_VERSION:
        issues.append("saved audience selection contract version is unsupported")

    return {
        "detail": detail,
        "normalized_filters": normalized_filters,
        "normalized_selection": normalized_selection,
        "saved_audience_current": bool(currentness["is_current"]),
        "scoring_current": bool(scoring_currentness["is_canonical"]),
        "historical_source_verified": bool(scoring_currentness["historical_source_verified"]),
        "demographic_source_verified": bool(scoring_currentness["demographic_source_verified"]),
        "model_verified": bool(scoring_currentness["is_canonical"]),
        "rank_ready": rank_ready,
        "analytics_ready": bool(analytics["analytics_prepared"]),
        "issues": _bounded_issues(issues),
        "analytics_currentness": analytics,
        "scoring_currentness": scoring_currentness,
    }


def _campaign_currentness_from_row(path: Path, row: dict[str, Any]) -> dict[str, Any]:
    campaign_id = int(row["campaign_id"])
    status = str(row["status"])
    issues: list[str] = []

    if status not in {CAMPAIGN_STATUS_DRAFT, CAMPAIGN_STATUS_FINALIZED}:
        issues.append("campaign status is unsupported")

    if str(row["campaign_contract_version"]) != CAMPAIGN_CONTRACT_VERSION:
        issues.append("campaign contract version is unsupported")
    if str(row["member_resolution_contract_version"]) != CAMPAIGN_MEMBER_RESOLUTION_CONTRACT_VERSION:
        issues.append("campaign member resolution contract version is unsupported")
    if str(row["export_contract_version"]) != CAMPAIGN_EXPORT_CONTRACT_VERSION:
        issues.append("campaign export contract version is unsupported")

    if str(row["filter_contract_version"]) != AUDIENCE_FILTER_CONTRACT_VERSION:
        issues.append("campaign filter contract version is unsupported")
    if str(row["rank_contract_version"]) != AUDIENCE_RANK_CONTRACT_VERSION:
        issues.append("campaign rank contract version is unsupported")
    if str(row["selection_contract_version"]) != AUDIENCE_SELECTION_CONTRACT_VERSION:
        issues.append("campaign selection contract version is unsupported")
    if str(row["analytics_contract_version"]) != AUDIENCE_ANALYTICS_CONTRACT_VERSION:
        issues.append("campaign analytics contract version is unsupported")

    saved_audience_current = False
    scoring_current = False
    historical_source_verified = False
    demographic_source_verified = False
    model_verified = False
    rank_ready = False
    analytics_ready = False

    try:
        snapshot = _extract_saved_audience_snapshot(path, saved_audience_id=int(row["saved_audience_id"]))
        detail = snapshot["detail"]

        if int(detail["definition"]["scoring_run_id"]) != int(row["scoring_run_id"]):
            issues.append("campaign scoring_run_id does not match immutable saved audience definition")
        if int(detail["provenance"]["model_run_id"]) != int(row["model_run_id"]):
            issues.append("campaign model_run_id does not match immutable saved audience provenance")
        if int(detail["provenance"]["analysis_run_id"]) != int(row["analysis_run_id"]):
            issues.append("campaign analysis_run_id does not match immutable saved audience provenance")

        expected_filter_hash = _filter_hash_from_payload(snapshot["normalized_filters"].payload)
        if str(row["saved_audience_filter_hash"]).strip().lower() != expected_filter_hash:
            issues.append("campaign filter hash does not match immutable saved audience filters")

        expected_selection_json = _selection_json_from_payload(snapshot["normalized_selection"].payload)
        if str(row["saved_audience_selection_json"]) != expected_selection_json:
            issues.append("campaign selection payload does not match immutable saved audience selection")

        if int(detail["definition"]["resolved_count"]) != int(row["saved_audience_resolved_count"]):
            issues.append("campaign resolved_count does not match immutable saved audience selection")

        issues.extend(snapshot["issues"])
        saved_audience_current = bool(snapshot["saved_audience_current"])
        scoring_current = bool(snapshot["scoring_current"])
        historical_source_verified = bool(snapshot["historical_source_verified"])
        demographic_source_verified = bool(snapshot["demographic_source_verified"])
        model_verified = bool(snapshot["model_verified"])
        rank_ready = bool(snapshot["rank_ready"])
        analytics_ready = bool(snapshot["analytics_ready"])
    except CampaignServiceError as exc:
        issues.append(str(exc))

    bounded = _bounded_issues(issues)
    is_current = len(bounded) == 0
    return {
        "campaign_id": campaign_id,
        "status": status,
        "is_current": is_current,
        "ready_for_finalize": status == CAMPAIGN_STATUS_DRAFT and is_current,
        "ready_for_export": status == CAMPAIGN_STATUS_FINALIZED and is_current,
        "saved_audience_current": saved_audience_current,
        "scoring_current": scoring_current,
        "historical_source_verified": historical_source_verified,
        "demographic_source_verified": demographic_source_verified,
        "model_verified": model_verified,
        "rank_ready": rank_ready,
        "analytics_ready": analytics_ready,
        "issues": bounded,
    }


def evaluate_campaign_currentness(
    database_path: str | Path,
    *,
    campaign_id: int,
) -> dict[str, Any]:
    path = initialize_database(database_path)
    try:
        row = CampaignRepository(path).fetch_campaign(campaign_id)
    except CampaignNotFoundError as exc:
        raise CampaignServiceNotFoundError(CAMPAIGN_NOT_FOUND_MESSAGE) from exc
    except CampaignValidationError as exc:
        raise CampaignServiceValidationError(str(exc)) from exc

    return _campaign_currentness_from_row(path, row)


def _campaign_summary_from_row(path: Path, row: dict[str, Any]) -> dict[str, Any]:
    currentness = _campaign_currentness_from_row(path, row)
    return {
        "campaign_id": int(row["campaign_id"]),
        "campaign_name": str(row["campaign_name"]),
        "description": row.get("description"),
        "channel": str(row["channel"]),
        "planned_launch_date": row.get("planned_launch_date"),
        "status": str(row["status"]),
        "saved_audience_id": int(row["saved_audience_id"]),
        "saved_audience_resolved_count": int(row["saved_audience_resolved_count"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "finalized_at": row.get("finalized_at"),
        "currentness": currentness,
    }


def _campaign_detail_from_row(path: Path, row: dict[str, Any]) -> dict[str, Any]:
    currentness = _campaign_currentness_from_row(path, row)
    saved_selection = _decode_json_object(
        row["saved_audience_selection_json"],
        field_name="campaign.saved_audience_selection_json",
    )

    profile = CHANNEL_EXPORT_PROFILE.get(str(row["channel"]))
    if profile is None:
        raise CampaignServiceValidationError("Campaign channel cannot resolve an export profile.")

    return {
        "campaign_id": int(row["campaign_id"]),
        "campaign_contract_version": str(row["campaign_contract_version"]),
        "campaign_name": str(row["campaign_name"]),
        "description": row.get("description"),
        "channel": str(row["channel"]),
        "planned_launch_date": row.get("planned_launch_date"),
        "status": str(row["status"]),
        "saved_audience_id": int(row["saved_audience_id"]),
        "scoring_run_id": int(row["scoring_run_id"]),
        "model_run_id": int(row["model_run_id"]),
        "analysis_run_id": int(row["analysis_run_id"]),
        "saved_audience_filter_hash": str(row["saved_audience_filter_hash"]),
        "saved_audience_selection": saved_selection,
        "saved_audience_resolved_count": int(row["saved_audience_resolved_count"]),
        "filter_contract_version": str(row["filter_contract_version"]),
        "rank_contract_version": str(row["rank_contract_version"]),
        "selection_contract_version": str(row["selection_contract_version"]),
        "analytics_contract_version": str(row["analytics_contract_version"]),
        "member_resolution_contract_version": str(row["member_resolution_contract_version"]),
        "export_contract_version": str(row["export_contract_version"]),
        "export_profile": profile,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "finalized_at": row.get("finalized_at"),
        "immutable": str(row["status"]) == CAMPAIGN_STATUS_FINALIZED,
        "currentness": currentness,
    }


def get_campaign_options(database_path: str | Path) -> dict[str, Any]:
    path = initialize_database(database_path)
    audiences = list_saved_audiences(path, limit=100, offset=0)
    eligible = [item for item in audiences if bool(item.get("is_current"))]

    return {
        "campaign_contract_version": CAMPAIGN_CONTRACT_VERSION,
        "export_contract_version": CAMPAIGN_EXPORT_CONTRACT_VERSION,
        "member_resolution_contract_version": CAMPAIGN_MEMBER_RESOLUTION_CONTRACT_VERSION,
        "supported_channels": [CAMPAIGN_CHANNEL_EMAIL, CAMPAIGN_CHANNEL_DIRECT_MAIL],
        "profiles_by_channel": {
            CAMPAIGN_CHANNEL_EMAIL: EXPORT_PROFILE_EMAIL_CONTACT_V1,
            CAMPAIGN_CHANNEL_DIRECT_MAIL: EXPORT_PROFILE_DIRECT_MAIL_CONTACT_V1,
        },
        "eligible_saved_audiences": eligible,
    }


def create_campaign(database_path: str | Path, request_payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request_payload, dict):
        raise CampaignServiceValidationError("Campaign create request must be a JSON object.")

    path = initialize_database(database_path)
    campaign_name = _require_non_empty_text(
        request_payload.get("campaign_name"),
        field_name="campaign_name",
        maximum=120,
    )
    description = _optional_bounded_text(
        request_payload.get("description"),
        field_name="description",
        maximum=500,
    )
    channel = _require_campaign_channel(request_payload.get("channel"))
    planned_launch_date = _optional_iso_date(
        request_payload.get("planned_launch_date"),
        field_name="planned_launch_date",
    )
    saved_audience_id = _require_positive_int(
        request_payload.get("saved_audience_id"),
        field_name="saved_audience_id",
    )

    snapshot = _extract_saved_audience_snapshot(path, saved_audience_id=saved_audience_id)
    if snapshot["issues"]:
        raise CampaignServiceConflictError(snapshot["issues"][0])

    detail = snapshot["detail"]
    now = _utc_timestamp()

    try:
        campaign_id = CampaignRepository(path).create_campaign(
            campaign_name=campaign_name,
            description=description,
            channel=channel,
            planned_launch_date=planned_launch_date,
            saved_audience_id=saved_audience_id,
            scoring_run_id=int(detail["definition"]["scoring_run_id"]),
            model_run_id=int(detail["provenance"]["model_run_id"]),
            analysis_run_id=int(detail["provenance"]["analysis_run_id"]),
            saved_audience_filter_hash=_filter_hash_from_payload(snapshot["normalized_filters"].payload),
            saved_audience_selection_payload=snapshot["normalized_selection"].payload,
            saved_audience_resolved_count=int(detail["definition"]["resolved_count"]),
            filter_contract_version=AUDIENCE_FILTER_CONTRACT_VERSION,
            rank_contract_version=AUDIENCE_RANK_CONTRACT_VERSION,
            selection_contract_version=AUDIENCE_SELECTION_CONTRACT_VERSION,
            analytics_contract_version=AUDIENCE_ANALYTICS_CONTRACT_VERSION,
            member_resolution_contract_version=CAMPAIGN_MEMBER_RESOLUTION_CONTRACT_VERSION,
            export_contract_version=CAMPAIGN_EXPORT_CONTRACT_VERSION,
            created_at=now,
        )
    except CampaignValidationError as exc:
        raise CampaignServiceValidationError(str(exc)) from exc

    return get_campaign(path, campaign_id=campaign_id)


def list_campaigns(
    database_path: str | Path,
    *,
    limit: int = DEFAULT_CAMPAIGN_LIST_LIMIT,
    offset: int = 0,
) -> list[dict[str, Any]]:
    normalized_limit, normalized_offset = _validate_list_bounds(
        limit=limit,
        offset=offset,
        maximum_limit=MAXIMUM_CAMPAIGN_LIST_LIMIT,
    )
    path = initialize_database(database_path)

    try:
        rows = CampaignRepository(path).list_campaigns(limit=normalized_limit, offset=normalized_offset)
    except CampaignValidationError as exc:
        raise CampaignServiceValidationError(str(exc)) from exc

    return [_campaign_summary_from_row(path, row) for row in rows]


def get_campaign(database_path: str | Path, *, campaign_id: int) -> dict[str, Any]:
    path = initialize_database(database_path)
    try:
        row = CampaignRepository(path).fetch_campaign(campaign_id)
    except CampaignNotFoundError as exc:
        raise CampaignServiceNotFoundError(CAMPAIGN_NOT_FOUND_MESSAGE) from exc
    except CampaignValidationError as exc:
        raise CampaignServiceValidationError(str(exc)) from exc

    return _campaign_detail_from_row(path, row)


def update_campaign(
    database_path: str | Path,
    *,
    campaign_id: int,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(request_payload, dict):
        raise CampaignServiceValidationError("Campaign update request must be a JSON object.")

    path = initialize_database(database_path)
    repository = CampaignRepository(path)
    try:
        row = repository.fetch_campaign(campaign_id)
    except CampaignNotFoundError as exc:
        raise CampaignServiceNotFoundError(CAMPAIGN_NOT_FOUND_MESSAGE) from exc
    except CampaignValidationError as exc:
        raise CampaignServiceValidationError(str(exc)) from exc

    if str(row["status"]) != CAMPAIGN_STATUS_DRAFT:
        raise CampaignServiceConflictError(CAMPAIGN_IMMUTABLE_MESSAGE)

    campaign_name = _require_non_empty_text(
        request_payload.get("campaign_name", row["campaign_name"]),
        field_name="campaign_name",
        maximum=120,
    )
    description = _optional_bounded_text(
        request_payload.get("description", row.get("description")),
        field_name="description",
        maximum=500,
    )
    channel = _require_campaign_channel(request_payload.get("channel", row["channel"]))
    planned_launch_date = _optional_iso_date(
        request_payload.get("planned_launch_date", row.get("planned_launch_date")),
        field_name="planned_launch_date",
    )
    saved_audience_id = _require_positive_int(
        request_payload.get("saved_audience_id", row["saved_audience_id"]),
        field_name="saved_audience_id",
    )

    snapshot = _extract_saved_audience_snapshot(path, saved_audience_id=saved_audience_id)
    if snapshot["issues"]:
        raise CampaignServiceConflictError(snapshot["issues"][0])
    detail = snapshot["detail"]

    try:
        repository.update_draft(
            campaign_id=int(row["campaign_id"]),
            campaign_name=campaign_name,
            description=description,
            channel=channel,
            planned_launch_date=planned_launch_date,
            saved_audience_id=saved_audience_id,
            scoring_run_id=int(detail["definition"]["scoring_run_id"]),
            model_run_id=int(detail["provenance"]["model_run_id"]),
            analysis_run_id=int(detail["provenance"]["analysis_run_id"]),
            saved_audience_filter_hash=_filter_hash_from_payload(snapshot["normalized_filters"].payload),
            saved_audience_selection_payload=snapshot["normalized_selection"].payload,
            saved_audience_resolved_count=int(detail["definition"]["resolved_count"]),
            filter_contract_version=AUDIENCE_FILTER_CONTRACT_VERSION,
            rank_contract_version=AUDIENCE_RANK_CONTRACT_VERSION,
            selection_contract_version=AUDIENCE_SELECTION_CONTRACT_VERSION,
            analytics_contract_version=AUDIENCE_ANALYTICS_CONTRACT_VERSION,
            member_resolution_contract_version=CAMPAIGN_MEMBER_RESOLUTION_CONTRACT_VERSION,
            export_contract_version=CAMPAIGN_EXPORT_CONTRACT_VERSION,
            updated_at=_utc_timestamp(),
        )
    except CampaignNotFoundError as exc:
        raise CampaignServiceNotFoundError(CAMPAIGN_NOT_FOUND_MESSAGE) from exc
    except CampaignValidationError as exc:
        message = str(exc)
        if "Only DRAFT campaigns can be updated." in message:
            raise CampaignServiceConflictError(CAMPAIGN_IMMUTABLE_MESSAGE) from exc
        raise CampaignServiceValidationError(message) from exc

    return get_campaign(path, campaign_id=int(row["campaign_id"]))


def finalize_campaign(database_path: str | Path, *, campaign_id: int) -> dict[str, Any]:
    path = initialize_database(database_path)
    repository = CampaignRepository(path)
    try:
        row = repository.fetch_campaign(campaign_id)
    except CampaignNotFoundError as exc:
        raise CampaignServiceNotFoundError(CAMPAIGN_NOT_FOUND_MESSAGE) from exc
    except CampaignValidationError as exc:
        raise CampaignServiceValidationError(str(exc)) from exc

    if str(row["status"]) != CAMPAIGN_STATUS_DRAFT:
        raise CampaignServiceConflictError("Only DRAFT campaigns can be finalized.")

    currentness = _campaign_currentness_from_row(path, row)
    if not currentness["ready_for_finalize"]:
        message = currentness["issues"][0] if currentness["issues"] else CAMPAIGN_CURRENTNESS_REQUIRED_MESSAGE
        raise CampaignServiceConflictError(message)

    profile = CHANNEL_EXPORT_PROFILE.get(str(row["channel"]))
    if profile is None:
        raise CampaignServiceValidationError("Campaign channel cannot resolve an export profile.")

    timestamp = _utc_timestamp()
    try:
        repository.finalize_campaign(campaign_id=int(row["campaign_id"]), finalized_at=timestamp)
    except CampaignNotFoundError as exc:
        raise CampaignServiceNotFoundError(CAMPAIGN_NOT_FOUND_MESSAGE) from exc
    except CampaignValidationError as exc:
        message = str(exc)
        if "Only DRAFT campaigns can be finalized." in message:
            raise CampaignServiceConflictError("Only DRAFT campaigns can be finalized.") from exc
        raise CampaignServiceValidationError(message) from exc

    refreshed = repository.fetch_campaign(int(row["campaign_id"]))
    refreshed_currentness = _campaign_currentness_from_row(path, refreshed)
    return {
        "campaign_id": int(refreshed["campaign_id"]),
        "status": str(refreshed["status"]),
        "finalized_at": refreshed["finalized_at"],
        "currentness": refreshed_currentness,
    }


def list_campaign_export_events(
    database_path: str | Path,
    *,
    campaign_id: int,
    limit: int = DEFAULT_EXPORT_EVENT_LIST_LIMIT,
) -> list[dict[str, Any]]:
    path = initialize_database(database_path)
    _require_positive_int(campaign_id, field_name="campaign_id")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAXIMUM_EXPORT_EVENT_LIST_LIMIT:
        raise CampaignServiceValidationError(
            f"limit must be an integer between 1 and {MAXIMUM_EXPORT_EVENT_LIST_LIMIT}."
        )

    try:
        CampaignRepository(path).fetch_campaign(campaign_id)
    except CampaignNotFoundError as exc:
        raise CampaignServiceNotFoundError(CAMPAIGN_NOT_FOUND_MESSAGE) from exc

    try:
        rows = CampaignExportRepository(path).list_campaign_exports(campaign_id=campaign_id, limit=limit)
    except CampaignExportValidationError as exc:
        raise CampaignServiceValidationError(str(exc)) from exc

    return [
        {
            "export_event_id": int(row["export_event_id"]),
            "campaign_id": int(row["campaign_id"]),
            "export_contract_version": str(row["export_contract_version"]),
            "export_snapshot_contract_version": str(row["export_snapshot_contract_version"]),
            "export_profile": str(row["export_profile"]),
            "status": str(row["status"]),
            "selected_count": int(row["selected_count"]),
            "deliverable_count": int(row["deliverable_count"]),
            "undeliverable_count": int(row["undeliverable_count"]),
            "row_count": int(row["row_count"]),
            "csv_sha256": row.get("csv_sha256"),
            "start_provenance_sha256": row.get("start_provenance_sha256"),
            "source_changed_during_export": bool(row.get("source_changed_during_export")),
            "completion_currentness_state": row.get("completion_currentness_state"),
            "started_at": row["started_at"],
            "completed_at": row.get("completed_at"),
            "safe_error_message": row.get("safe_error_message"),
        }
        for row in rows
    ]


def reconcile_stale_campaign_export_events(database_path: str | Path) -> int:
    path = initialize_database(database_path)
    repository = CampaignExportRepository(path)

    now = datetime.now(timezone.utc)
    stale_cutoff = now.timestamp() - CAMPAIGN_EXPORT_RECOVERY_THRESHOLD_SECONDS
    stale_cutoff_iso = datetime.fromtimestamp(stale_cutoff, tz=timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00",
        "Z",
    )
    reconciled_at = now.isoformat(timespec="seconds").replace("+00:00", "Z")

    try:
        return repository.reconcile_stale_started_events(
            stale_started_at_max=stale_cutoff_iso,
            reconciled_at=reconciled_at,
            safe_error_message=EXPORT_RECOVERY_INTERRUPTED_MESSAGE,
        )
    except CampaignExportValidationError as exc:
        raise CampaignServiceUnavailableError("Campaign export startup reconciliation failed.") from exc


def _resolve_campaign_member_query_context(path: Path, campaign_row: dict[str, Any]) -> dict[str, Any]:
    with get_connection(path) as connection:
        connection.execute("BEGIN")
        return _resolve_campaign_member_query_context_on_connection(connection, campaign_row=campaign_row)


def _resolve_campaign_member_query_context_on_connection(
    connection: sqlite3.Connection,
    *,
    campaign_row: dict[str, Any],
) -> dict[str, Any]:
    saved_audience_id = int(campaign_row["saved_audience_id"])
    saved_row = connection.execute(
        "SELECT * FROM saved_audiences WHERE audience_id = ?",
        (saved_audience_id,),
    ).fetchone()
    if saved_row is None:
        raise CampaignServiceConflictError("Saved audience backing this campaign was not found.")

    saved_row_dict = dict(saved_row)
    saved_filters = _decode_json_object(
        saved_row_dict["filters_json"],
        field_name="saved_audience.filters_json",
    )
    saved_selection = _decode_json_object(
        saved_row_dict["selection_json"],
        field_name="saved_audience.selection_json",
    )

    normalized_filters = normalize_audience_filters(saved_filters)
    normalized_selection = normalize_selection(saved_selection)

    saved_filter_hash = _filter_hash_from_payload(normalized_filters.payload)
    if saved_filter_hash != str(campaign_row["saved_audience_filter_hash"]).strip().lower():
        raise CampaignServiceConflictError("Campaign filter hash no longer matches immutable saved audience filters.")

    selection_json = _selection_json_from_payload(normalized_selection.payload)
    if selection_json != str(campaign_row["saved_audience_selection_json"]):
        raise CampaignServiceConflictError("Campaign selection no longer matches immutable saved audience selection.")

    if int(saved_row_dict["resolved_count"]) != int(campaign_row["saved_audience_resolved_count"]):
        raise CampaignServiceConflictError("Campaign resolved_count no longer matches immutable saved audience selection.")

    scoring_run_id = int(campaign_row["scoring_run_id"])
    scoring_row = connection.execute(
        "SELECT * FROM scoring_runs WHERE scoring_run_id = ?",
        (scoring_run_id,),
    ).fetchone()
    if scoring_row is None:
        raise CampaignServiceConflictError("Campaign scoring run was not found.")
    scoring_row_dict = dict(scoring_row)
    if str(scoring_row_dict["status"]) != "COMPLETED":
        raise CampaignServiceConflictError("Campaign scoring run is not completed.")

    boundary_rows = connection.execute(
        """
        SELECT percentile_bucket, boundary_score, boundary_person_id
        FROM audience_rank_boundaries
        WHERE scoring_run_id = ?
        ORDER BY percentile_bucket ASC
        """,
        (scoring_run_id,),
    ).fetchall()
    boundaries = [dict(row) for row in boundary_rows]
    if len(boundaries) != 100:
        raise CampaignServiceConflictError("Audience rank boundaries are not prepared for this scoring run.")

    analytics_row = connection.execute(
        """
        SELECT *
        FROM audience_analytics_snapshots
        WHERE scoring_run_id = ? AND analytics_contract_version = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (scoring_run_id, AUDIENCE_ANALYTICS_CONTRACT_VERSION),
    ).fetchone()
    if analytics_row is None:
        raise CampaignServiceConflictError("Audience analytics snapshot is not prepared for this scoring run.")
    analytics_snapshot = dict(analytics_row)

    try:
        categorical_vocabularies = _categorical_vocabularies_from_snapshot(analytics_snapshot)
    except Exception as exc:
        raise CampaignServiceConflictError("Audience analytics snapshot is not prepared for this scoring run.") from exc
    (
        score_predicates,
        score_parameters,
        demographic_predicates,
        demographic_parameters,
    ) = _build_filter_predicates_split(
        normalized_filters=normalized_filters,
        boundaries=boundaries,
        categorical_vocabularies=categorical_vocabularies,
    )

    export_provenance_payload = {
        "campaign_id": int(campaign_row["campaign_id"]),
        "campaign_contract_version": str(campaign_row["campaign_contract_version"]),
        "export_contract_version": str(campaign_row["export_contract_version"]),
        "export_snapshot_contract_version": CAMPAIGN_EXPORT_SNAPSHOT_CONTRACT_VERSION,
        "saved_audience_id": int(campaign_row["saved_audience_id"]),
        "scoring_run_id": int(campaign_row["scoring_run_id"]),
        "model_run_id": int(campaign_row["model_run_id"]),
        "analysis_run_id": int(campaign_row["analysis_run_id"]),
        "saved_audience_filter_hash": str(campaign_row["saved_audience_filter_hash"]),
        "saved_audience_selection_json": str(campaign_row["saved_audience_selection_json"]),
        "saved_audience_resolved_count": int(campaign_row["saved_audience_resolved_count"]),
        "customer_import_id": int(saved_row_dict["customer_import_id"]),
        "customer_source_checksum": str(saved_row_dict["customer_source_checksum"]),
        "campaign_sales_import_id": int(saved_row_dict["campaign_sales_import_id"]),
        "campaign_sales_source_checksum": str(saved_row_dict["campaign_sales_source_checksum"]),
        "demographic_import_id": int(saved_row_dict["demographic_import_id"]),
        "demographic_source_checksum": str(saved_row_dict["demographic_source_checksum"]),
        "feature_contract_version": str(saved_row_dict["feature_contract_version"]),
        "feature_contract_sha256": str(saved_row_dict["feature_contract_sha256"]),
        "artifact_sha256": str(saved_row_dict["artifact_sha256"]),
        "selected_candidate": str(scoring_row_dict["selected_candidate"]),
    }

    return {
        "normalized_selection": normalized_selection,
        "boundaries": boundaries,
        "scoring_run_id": scoring_run_id,
        "score_predicates": score_predicates,
        "score_parameters": score_parameters,
        "demographic_predicates": demographic_predicates,
        "demographic_parameters": demographic_parameters,
        "start_provenance_sha256": _provenance_sha256(export_provenance_payload),
    }


def _compile_boundary_lookup(boundaries: list[dict[str, Any]]) -> tuple[list[tuple[int, float, str]], bool]:
    if len(boundaries) != 100:
        raise CampaignServiceConflictError("Audience rank boundaries are not prepared for this scoring run.")

    compiled: list[tuple[int, float, str]] = []
    previous_score: float | None = None
    previous_person_id: str | None = None
    binary_safe = True

    for expected_bucket, row in enumerate(boundaries, start=1):
        bucket = int(row["percentile_bucket"])
        score = float(row["boundary_score"])
        person_id = str(row["boundary_person_id"])
        compiled.append((bucket, score, person_id))

        if bucket != expected_bucket:
            binary_safe = False
        if previous_score is not None:
            if score > previous_score:
                binary_safe = False
            if score == previous_score and previous_person_id is not None and person_id < previous_person_id:
                binary_safe = False
        previous_score = score
        previous_person_id = person_id

    return compiled, binary_safe


def _classify_percentile_bucket_from_lookup(
    score: float,
    person_id: str,
    boundary_lookup: list[tuple[int, float, str]],
    *,
    binary_safe: bool,
) -> int:
    if not binary_safe:
        for bucket, boundary_score, boundary_person_id in boundary_lookup:
            if score > boundary_score:
                return bucket
            if score == boundary_score and person_id <= boundary_person_id:
                return bucket
        return 100

    low = 0
    high = len(boundary_lookup) - 1
    best_index = len(boundary_lookup) - 1

    while low <= high:
        mid = (low + high) // 2
        _, boundary_score, boundary_person_id = boundary_lookup[mid]
        qualifies = score > boundary_score or (score == boundary_score and person_id <= boundary_person_id)
        if qualifies:
            best_index = mid
            high = mid - 1
        else:
            low = mid + 1

    return boundary_lookup[best_index][0]


def _iter_selected_member_chunks(
    connection: sqlite3.Connection,
    *,
    query_context: dict[str, Any],
    export_profile: str,
    chunk_size: int,
) -> Iterator[list[dict[str, Any]]]:
    scoring_run_id = int(query_context["scoring_run_id"])
    boundaries = query_context["boundaries"]
    score_predicates = list(query_context["score_predicates"])
    score_parameters = list(query_context["score_parameters"])
    demographic_predicates = list(query_context["demographic_predicates"])
    demographic_parameters = list(query_context["demographic_parameters"])
    selection_payload = dict(query_context["normalized_selection"].payload)

    boundary_lookup, binary_safe = _compile_boundary_lookup(boundaries)

    if export_profile == EXPORT_PROFILE_EMAIL_CONTACT_V1:
        contact_select = (
            "d.first_name AS first_name",
            "d.last_name AS last_name",
            "d.email AS email",
        )
    elif export_profile == EXPORT_PROFILE_DIRECT_MAIL_CONTACT_V1:
        contact_select = (
            "d.first_name AS first_name",
            "d.last_name AS last_name",
            "d.address_line_1 AS address_line_1",
            "d.address_line_2 AS address_line_2",
            "d.city AS city",
            "d.state AS state",
            "d.postal_code AS postal_code",
        )
    else:
        raise CampaignServiceValidationError("Unsupported export profile.")

    join_clause = "INNER JOIN demographics d ON d.person_id = p.person_id"
    where_predicates = ["p.scoring_run_id = ?"]
    base_params: list[Any] = [scoring_run_id]

    if score_predicates:
        where_predicates.extend(score_predicates)
        base_params.extend(score_parameters)

    if demographic_predicates:
        where_predicates.extend(demographic_predicates)
        base_params.extend(demographic_parameters)

    top_n_limit: int | None = None
    if selection_payload["mode"] == "TOP_N":
        target = selection_payload.get("target_count")
        if not isinstance(target, int) or target <= 0:
            raise CampaignServiceValidationError("selection.target_count is required when mode is TOP_N.")
        top_n_limit = target

    params = list(base_params)
    limit_clause = ""
    if top_n_limit is not None:
        limit_clause = "LIMIT ?"
        params.append(top_n_limit)

    select_columns = [
        "p.person_id AS person_id",
        "p.propensity_score AS propensity_score",
        *contact_select,
    ]
    query = f"""
        SELECT {', '.join(select_columns)}
        FROM propensity_scores p
        {join_clause}
        WHERE {' AND '.join(where_predicates)}
        ORDER BY p.propensity_score DESC, p.person_id ASC
        {limit_clause}
    """

    cursor = connection.execute(query, params)
    while True:
        rows = cursor.fetchmany(chunk_size)
        if not rows:
            break

        chunk: list[dict[str, Any]] = []
        for row in rows:
            person_id = str(row["person_id"])
            propensity_score = float(row["propensity_score"])
            percentile_bucket = _classify_percentile_bucket_from_lookup(
                propensity_score,
                person_id,
                boundary_lookup,
                binary_safe=binary_safe,
            )
            decile = classify_decile(percentile_bucket)
            rank_band = _rank_band_for_bucket(percentile_bucket)
            row_payload: dict[str, Any] = {
                "person_id": person_id,
                "propensity_score": propensity_score,
                "percentile_bucket": percentile_bucket,
                "decile": decile,
                "rank_band": rank_band,
            }
            for field in (
                "first_name",
                "last_name",
                "email",
                "address_line_1",
                "address_line_2",
                "city",
                "state",
                "postal_code",
            ):
                if field in row.keys():
                    row_payload[field] = row[field]
            chunk.append(row_payload)

        yield chunk


def _export_header_bytes(columns: tuple[str, ...], writer: csv.writer, buffer: io.StringIO) -> bytes:
    buffer.seek(0)
    buffer.truncate(0)
    writer.writerow(list(columns))
    return buffer.getvalue().encode("utf-8")


def _export_row_bytes(row: list[Any], writer: csv.writer, buffer: io.StringIO) -> bytes:
    buffer.seek(0)
    buffer.truncate(0)
    writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def stream_campaign_export_csv(
    database_path: str | Path,
    *,
    campaign_id: int,
    acknowledge_pii: bool,
    request: Request,
) -> StreamingResponse:
    if not acknowledge_pii:
        raise CampaignServiceValidationError(CAMPAIGN_PII_ACK_REQUIRED_MESSAGE)

    path = initialize_database(database_path)
    campaign_repository = CampaignRepository(path)
    export_repository = CampaignExportRepository(path)

    try:
        campaign_row = campaign_repository.fetch_campaign(campaign_id)
    except CampaignNotFoundError as exc:
        raise CampaignServiceNotFoundError(CAMPAIGN_NOT_FOUND_MESSAGE) from exc
    except CampaignValidationError as exc:
        raise CampaignServiceValidationError(str(exc)) from exc

    if str(campaign_row["status"]) != CAMPAIGN_STATUS_FINALIZED:
        raise CampaignServiceConflictError(CAMPAIGN_NOT_FINALIZED_MESSAGE)

    currentness = _campaign_currentness_from_row(path, campaign_row)
    if not currentness["ready_for_export"]:
        issue = currentness["issues"][0] if currentness["issues"] else CAMPAIGN_CURRENTNESS_REQUIRED_MESSAGE
        raise CampaignServiceConflictError(issue)

    export_profile = CHANNEL_EXPORT_PROFILE.get(str(campaign_row["channel"]))
    if export_profile is None:
        raise CampaignServiceValidationError("Campaign channel cannot resolve an export profile.")

    expected_selected_count = int(campaign_row["saved_audience_resolved_count"])
    columns = PROFILE_EXPORT_COLUMNS[export_profile]
    filename = f"campaign_{int(campaign_row['campaign_id'])}_{export_profile.lower()}.csv"

    async def _stream() -> AsyncIterator[bytes]:
        export_event_id: int | None = None
        selected_count = 0
        deliverable_count = 0
        undeliverable_count = 0
        row_count = 0
        processed_chunks = 0
        digest = hashlib.sha256()

        writer_buffer = io.StringIO()
        writer = csv.writer(writer_buffer, lineterminator="\n")

        try:
            with get_connection(path) as connection:
                connection.execute("BEGIN")
                query_context = _resolve_campaign_member_query_context_on_connection(
                    connection,
                    campaign_row=campaign_row,
                )

                if await request.is_disconnected():
                    raise CampaignExportAbortedError(CAMPAIGN_EXPORT_ABORTED_MESSAGE)

                started_at = _utc_timestamp()
                export_event_id = export_repository.create_started_event(
                    campaign_id=int(campaign_row["campaign_id"]),
                    export_profile=export_profile,
                    started_at=started_at,
                    export_snapshot_contract_version=CAMPAIGN_EXPORT_SNAPSHOT_CONTRACT_VERSION,
                    start_provenance_sha256=str(query_context["start_provenance_sha256"]),
                )

                header = _export_header_bytes(columns, writer, writer_buffer)
                digest.update(header)
                yield header

                previous_person_id: str | None = None
                for chunk in _iter_selected_member_chunks(
                    connection,
                    query_context=query_context,
                    export_profile=export_profile,
                    chunk_size=MEMBER_RESOLUTION_CHUNK_SIZE,
                ):
                    if await request.is_disconnected():
                        raise CampaignExportAbortedError(CAMPAIGN_EXPORT_ABORTED_MESSAGE)

                    processed_chunks += 1

                    for member in chunk:
                        selected_count += 1
                        person_id = str(member["person_id"])
                        if previous_person_id is not None and previous_person_id == person_id:
                            raise CampaignServiceConflictError("Duplicate person_id detected during deterministic export.")
                        previous_person_id = person_id

                        if export_profile == EXPORT_PROFILE_EMAIL_CONTACT_V1:
                            deliverable = _validate_email_deliverability(member.get("email"))
                        else:
                            deliverable = _validate_direct_mail_deliverability(member)

                        if not deliverable:
                            undeliverable_count += 1
                            continue

                        deliverable_count += 1

                        output_row = [
                            _csv_safe_value(member["person_id"]),
                            member["propensity_score"],
                            member["percentile_bucket"],
                            member["decile"],
                            _csv_safe_value(member["rank_band"]),
                        ]

                        if export_profile == EXPORT_PROFILE_EMAIL_CONTACT_V1:
                            output_row.extend(
                                [
                                    _csv_safe_value(member.get("first_name")),
                                    _csv_safe_value(member.get("last_name")),
                                    _csv_safe_value(member.get("email")),
                                ]
                            )
                        else:
                            output_row.extend(
                                [
                                    _csv_safe_value(member.get("first_name")),
                                    _csv_safe_value(member.get("last_name")),
                                    _csv_safe_value(member.get("address_line_1")),
                                    _csv_safe_value(member.get("address_line_2")),
                                    _csv_safe_value(member.get("city")),
                                    _csv_safe_value(member.get("state")),
                                    _csv_safe_value(member.get("postal_code")),
                                ]
                            )

                        encoded = _export_row_bytes(output_row, writer, writer_buffer)
                        digest.update(encoded)
                        row_count += 1
                        yield encoded

                    if (
                        export_event_id is not None
                        and processed_chunks % EXPORT_PROGRESS_UPDATE_CHUNK_INTERVAL == 0
                    ):
                        export_repository.update_started_progress(
                            export_event_id=export_event_id,
                            selected_count=selected_count,
                            deliverable_count=deliverable_count,
                            undeliverable_count=undeliverable_count,
                            row_count=row_count,
                        )

                if selected_count != expected_selected_count:
                    raise CampaignServiceConflictError(
                        "Resolved selected member count does not match immutable saved audience count."
                    )

            if selected_count != expected_selected_count:
                raise CampaignServiceConflictError(
                    "Selected audience count reconciliation failed during export."
                )
            if deliverable_count + undeliverable_count != selected_count:
                raise CampaignServiceConflictError(
                    "Deliverability reconciliation failed during export."
                )
            if row_count != deliverable_count:
                raise CampaignServiceConflictError("Exported row count does not match deliverable count.")

            refreshed_currentness = evaluate_campaign_currentness(path, campaign_id=int(campaign_row["campaign_id"]))
            source_changed_during_export = not bool(refreshed_currentness.get("ready_for_export"))
            completion_currentness_state = (
                EXPORT_CURRENTNESS_STATE_STALE
                if source_changed_during_export
                else EXPORT_CURRENTNESS_STATE_CURRENT
            )

            if export_event_id is not None:
                export_repository.mark_completed(
                    export_event_id=export_event_id,
                    selected_count=selected_count,
                    deliverable_count=deliverable_count,
                    undeliverable_count=undeliverable_count,
                    row_count=row_count,
                    csv_sha256=digest.hexdigest(),
                    completed_at=_utc_timestamp(),
                    source_changed_during_export=source_changed_during_export,
                    completion_currentness_state=completion_currentness_state,
                )
        except asyncio.CancelledError as exc:
            safe_message = _safe_export_error_message(CampaignExportAbortedError(str(exc) or CAMPAIGN_EXPORT_ABORTED_MESSAGE))
            try:
                if export_event_id is not None:
                    export_repository.mark_aborted(
                        export_event_id=export_event_id,
                        selected_count=selected_count,
                        deliverable_count=deliverable_count,
                        undeliverable_count=undeliverable_count,
                        row_count=row_count,
                        completed_at=_utc_timestamp(),
                        safe_error_message=safe_message,
                        completion_currentness_state=EXPORT_CURRENTNESS_STATE_UNKNOWN,
                    )
            except (CampaignExportValidationError, CampaignExportNotFoundError):
                pass
            raise
        except CampaignExportAbortedError as exc:
            safe_message = _safe_export_error_message(exc)
            try:
                if export_event_id is not None:
                    export_repository.mark_aborted(
                        export_event_id=export_event_id,
                        selected_count=selected_count,
                        deliverable_count=deliverable_count,
                        undeliverable_count=undeliverable_count,
                        row_count=row_count,
                        completed_at=_utc_timestamp(),
                        safe_error_message=safe_message,
                        completion_currentness_state=EXPORT_CURRENTNESS_STATE_UNKNOWN,
                    )
            except (CampaignExportValidationError, CampaignExportNotFoundError):
                pass
        except Exception as exc:  # pragma: no cover - guarded by public API tests
            safe_message = _safe_export_error_message(exc)
            try:
                if export_event_id is not None:
                    export_repository.mark_failed(
                        export_event_id=export_event_id,
                        selected_count=selected_count,
                        deliverable_count=deliverable_count,
                        undeliverable_count=undeliverable_count,
                        row_count=row_count,
                        completed_at=_utc_timestamp(),
                        safe_error_message=safe_message,
                        completion_currentness_state=EXPORT_CURRENTNESS_STATE_UNKNOWN,
                    )
            except (CampaignExportValidationError, CampaignExportNotFoundError):
                pass
            raise

    return StreamingResponse(
        _stream(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


__all__ = (
    "CAMPAIGN_CURRENTNESS_REQUIRED_MESSAGE",
    "CAMPAIGN_IMMUTABLE_MESSAGE",
    "CAMPAIGN_NOT_DRAFT_MESSAGE",
    "CAMPAIGN_NOT_FINALIZED_MESSAGE",
    "CAMPAIGN_NOT_FOUND_MESSAGE",
    "CAMPAIGN_PII_ACK_REQUIRED_MESSAGE",
    "CampaignServiceConflictError",
    "CampaignServiceError",
    "CampaignServiceNotFoundError",
    "CampaignServiceUnavailableError",
    "CampaignServiceValidationError",
    "create_campaign",
    "evaluate_campaign_currentness",
    "finalize_campaign",
    "get_campaign",
    "get_campaign_options",
    "list_campaign_export_events",
    "list_campaigns",
    "reconcile_stale_campaign_export_events",
    "stream_campaign_export_csv",
    "update_campaign",
)
