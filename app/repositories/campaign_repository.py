"""Campaign draft/finalized persistence for Phase 7."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from string import hexdigits
from typing import Any

from app.database.connection import get_connection
from app.services.campaign_contracts import (
    CAMPAIGN_CHANNELS,
    CAMPAIGN_CONTRACT_VERSION,
    CAMPAIGN_STATUSES,
    CAMPAIGN_STATUS_DRAFT,
    CAMPAIGN_STATUS_FINALIZED,
)


class CampaignRepositoryError(RuntimeError):
    """Base class for campaign repository failures."""


class CampaignValidationError(CampaignRepositoryError):
    """Raised when campaign payload values are invalid."""


class CampaignNotFoundError(CampaignRepositoryError):
    """Raised when the requested campaign id does not exist."""


def _require_positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CampaignValidationError(f"{field_name} must be a positive integer.")
    return value


def _require_non_empty_text(value: Any, *, field_name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise CampaignValidationError(f"{field_name} must be text.")
    normalized = value.strip()
    if not normalized:
        raise CampaignValidationError(f"{field_name} must not be blank.")
    if len(normalized) > maximum:
        raise CampaignValidationError(f"{field_name} must not exceed {maximum} characters.")
    return normalized


def _optional_bounded_text(value: Any, *, field_name: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CampaignValidationError(f"{field_name} must be text when provided.")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise CampaignValidationError(f"{field_name} must not exceed {maximum} characters.")
    return normalized


def _optional_iso_date(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CampaignValidationError(f"{field_name} must be text when provided.")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) != 10:
        raise CampaignValidationError(f"{field_name} must be YYYY-MM-DD when provided.")
    try:
        year = int(normalized[0:4])
        month = int(normalized[5:7])
        day = int(normalized[8:10])
    except ValueError as exc:
        raise CampaignValidationError(f"{field_name} must be YYYY-MM-DD when provided.") from exc
    if normalized[4] != "-" or normalized[7] != "-":
        raise CampaignValidationError(f"{field_name} must be YYYY-MM-DD when provided.")
    if not (1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2200):
        raise CampaignValidationError(f"{field_name} must be YYYY-MM-DD when provided.")
    return normalized


def _require_hash64(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise CampaignValidationError(f"{field_name} must be text.")
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(character not in hexdigits for character in normalized):
        raise CampaignValidationError(f"{field_name} must be a 64-character hex digest.")
    return normalized


def _canonical_json_object(value: Any, *, field_name: str) -> str:
    if not isinstance(value, dict):
        raise CampaignValidationError(f"{field_name} must be an object.")
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise CampaignValidationError(f"{field_name} contains non-serializable values.") from exc
    if encoded == "{}":
        raise CampaignValidationError(f"{field_name} must not be empty.")
    if len(encoded.encode("utf-8")) > 65_536:
        raise CampaignValidationError(f"{field_name} exceeds 65536 bytes.")
    return encoded


def _require_channel(value: Any) -> str:
    channel = _require_non_empty_text(value, field_name="channel", maximum=32).upper()
    if channel not in CAMPAIGN_CHANNELS:
        raise CampaignValidationError("channel is invalid.")
    return channel


def _require_status(value: Any) -> str:
    status = _require_non_empty_text(value, field_name="status", maximum=24).upper()
    if status not in CAMPAIGN_STATUSES:
        raise CampaignValidationError("status is invalid.")
    return status


class CampaignRepository:
    """Persist immutable campaign metadata without member-level rows."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def create_campaign(
        self,
        *,
        campaign_name: str,
        description: str | None,
        channel: str,
        planned_launch_date: str | None,
        saved_audience_id: int,
        scoring_run_id: int,
        model_run_id: int,
        analysis_run_id: int,
        saved_audience_filter_hash: str,
        saved_audience_selection_payload: dict[str, Any],
        saved_audience_resolved_count: int,
        filter_contract_version: str,
        rank_contract_version: str,
        selection_contract_version: str,
        analytics_contract_version: str,
        member_resolution_contract_version: str,
        export_contract_version: str,
        created_at: str,
    ) -> int:
        normalized_name = _require_non_empty_text(
            campaign_name,
            field_name="campaign_name",
            maximum=120,
        )
        normalized_description = _optional_bounded_text(
            description,
            field_name="description",
            maximum=500,
        )
        normalized_channel = _require_channel(channel)
        normalized_launch_date = _optional_iso_date(
            planned_launch_date,
            field_name="planned_launch_date",
        )
        normalized_saved_audience_id = _require_positive_int(
            saved_audience_id,
            field_name="saved_audience_id",
        )
        normalized_scoring_run_id = _require_positive_int(
            scoring_run_id,
            field_name="scoring_run_id",
        )
        normalized_model_run_id = _require_positive_int(
            model_run_id,
            field_name="model_run_id",
        )
        normalized_analysis_run_id = _require_positive_int(
            analysis_run_id,
            field_name="analysis_run_id",
        )
        normalized_filter_hash = _require_hash64(
            saved_audience_filter_hash,
            field_name="saved_audience_filter_hash",
        )
        normalized_selection_json = _canonical_json_object(
            saved_audience_selection_payload,
            field_name="saved_audience_selection_payload",
        )
        normalized_resolved_count = _require_positive_int(
            saved_audience_resolved_count,
            field_name="saved_audience_resolved_count",
        )
        normalized_filter_contract = _require_non_empty_text(
            filter_contract_version,
            field_name="filter_contract_version",
            maximum=24,
        )
        normalized_rank_contract = _require_non_empty_text(
            rank_contract_version,
            field_name="rank_contract_version",
            maximum=24,
        )
        normalized_selection_contract = _require_non_empty_text(
            selection_contract_version,
            field_name="selection_contract_version",
            maximum=24,
        )
        normalized_analytics_contract = _require_non_empty_text(
            analytics_contract_version,
            field_name="analytics_contract_version",
            maximum=24,
        )
        normalized_member_resolution_contract = _require_non_empty_text(
            member_resolution_contract_version,
            field_name="member_resolution_contract_version",
            maximum=24,
        )
        normalized_export_contract = _require_non_empty_text(
            export_contract_version,
            field_name="export_contract_version",
            maximum=24,
        )
        normalized_created_at = _require_non_empty_text(
            created_at,
            field_name="created_at",
            maximum=64,
        )

        with get_connection(self.database_path, write=True) as connection:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO campaigns (
                        campaign_contract_version,
                        campaign_name,
                        description,
                        channel,
                        planned_launch_date,
                        saved_audience_id,
                        scoring_run_id,
                        model_run_id,
                        analysis_run_id,
                        saved_audience_filter_hash,
                        saved_audience_selection_json,
                        saved_audience_resolved_count,
                        filter_contract_version,
                        rank_contract_version,
                        selection_contract_version,
                        analytics_contract_version,
                        member_resolution_contract_version,
                        export_contract_version,
                        status,
                        created_at,
                        updated_at,
                        finalized_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        CAMPAIGN_CONTRACT_VERSION,
                        normalized_name,
                        normalized_description,
                        normalized_channel,
                        normalized_launch_date,
                        normalized_saved_audience_id,
                        normalized_scoring_run_id,
                        normalized_model_run_id,
                        normalized_analysis_run_id,
                        normalized_filter_hash,
                        normalized_selection_json,
                        normalized_resolved_count,
                        normalized_filter_contract,
                        normalized_rank_contract,
                        normalized_selection_contract,
                        normalized_analytics_contract,
                        normalized_member_resolution_contract,
                        normalized_export_contract,
                        CAMPAIGN_STATUS_DRAFT,
                        normalized_created_at,
                        normalized_created_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise CampaignValidationError("Campaign write violated storage constraints.") from exc
        return int(cursor.lastrowid)

    def fetch_campaign(self, campaign_id: int) -> dict[str, Any]:
        normalized_campaign_id = _require_positive_int(campaign_id, field_name="campaign_id")
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM campaigns WHERE campaign_id = ?",
                (normalized_campaign_id,),
            ).fetchone()
        if row is None:
            raise CampaignNotFoundError("Campaign was not found.")
        return dict(row)

    def list_campaigns(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise CampaignValidationError("limit must be an integer between 1 and 100.")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise CampaignValidationError("offset must be a non-negative integer.")

        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM campaigns
                ORDER BY created_at DESC, campaign_id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_draft(
        self,
        *,
        campaign_id: int,
        campaign_name: str,
        description: str | None,
        channel: str,
        planned_launch_date: str | None,
        saved_audience_id: int,
        scoring_run_id: int,
        model_run_id: int,
        analysis_run_id: int,
        saved_audience_filter_hash: str,
        saved_audience_selection_payload: dict[str, Any],
        saved_audience_resolved_count: int,
        filter_contract_version: str,
        rank_contract_version: str,
        selection_contract_version: str,
        analytics_contract_version: str,
        member_resolution_contract_version: str,
        export_contract_version: str,
        updated_at: str,
    ) -> None:
        normalized_campaign_id = _require_positive_int(campaign_id, field_name="campaign_id")
        normalized_name = _require_non_empty_text(
            campaign_name,
            field_name="campaign_name",
            maximum=120,
        )
        normalized_description = _optional_bounded_text(
            description,
            field_name="description",
            maximum=500,
        )
        normalized_channel = _require_channel(channel)
        normalized_launch_date = _optional_iso_date(
            planned_launch_date,
            field_name="planned_launch_date",
        )
        normalized_saved_audience_id = _require_positive_int(
            saved_audience_id,
            field_name="saved_audience_id",
        )
        normalized_scoring_run_id = _require_positive_int(
            scoring_run_id,
            field_name="scoring_run_id",
        )
        normalized_model_run_id = _require_positive_int(
            model_run_id,
            field_name="model_run_id",
        )
        normalized_analysis_run_id = _require_positive_int(
            analysis_run_id,
            field_name="analysis_run_id",
        )
        normalized_filter_hash = _require_hash64(
            saved_audience_filter_hash,
            field_name="saved_audience_filter_hash",
        )
        normalized_selection_json = _canonical_json_object(
            saved_audience_selection_payload,
            field_name="saved_audience_selection_payload",
        )
        normalized_resolved_count = _require_positive_int(
            saved_audience_resolved_count,
            field_name="saved_audience_resolved_count",
        )
        normalized_filter_contract = _require_non_empty_text(
            filter_contract_version,
            field_name="filter_contract_version",
            maximum=24,
        )
        normalized_rank_contract = _require_non_empty_text(
            rank_contract_version,
            field_name="rank_contract_version",
            maximum=24,
        )
        normalized_selection_contract = _require_non_empty_text(
            selection_contract_version,
            field_name="selection_contract_version",
            maximum=24,
        )
        normalized_analytics_contract = _require_non_empty_text(
            analytics_contract_version,
            field_name="analytics_contract_version",
            maximum=24,
        )
        normalized_member_resolution_contract = _require_non_empty_text(
            member_resolution_contract_version,
            field_name="member_resolution_contract_version",
            maximum=24,
        )
        normalized_export_contract = _require_non_empty_text(
            export_contract_version,
            field_name="export_contract_version",
            maximum=24,
        )
        normalized_updated_at = _require_non_empty_text(
            updated_at,
            field_name="updated_at",
            maximum=64,
        )

        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status FROM campaigns WHERE campaign_id = ?",
                (normalized_campaign_id,),
            ).fetchone()
            if row is None:
                raise CampaignNotFoundError("Campaign was not found.")
            status = _require_status(row["status"])
            if status != CAMPAIGN_STATUS_DRAFT:
                raise CampaignValidationError("Only DRAFT campaigns can be updated.")

            try:
                updated = connection.execute(
                    """
                    UPDATE campaigns
                    SET
                        campaign_name = ?,
                        description = ?,
                        channel = ?,
                        planned_launch_date = ?,
                        saved_audience_id = ?,
                        scoring_run_id = ?,
                        model_run_id = ?,
                        analysis_run_id = ?,
                        saved_audience_filter_hash = ?,
                        saved_audience_selection_json = ?,
                        saved_audience_resolved_count = ?,
                        filter_contract_version = ?,
                        rank_contract_version = ?,
                        selection_contract_version = ?,
                        analytics_contract_version = ?,
                        member_resolution_contract_version = ?,
                        export_contract_version = ?,
                        updated_at = ?
                    WHERE campaign_id = ? AND status = 'DRAFT'
                    """,
                    (
                        normalized_name,
                        normalized_description,
                        normalized_channel,
                        normalized_launch_date,
                        normalized_saved_audience_id,
                        normalized_scoring_run_id,
                        normalized_model_run_id,
                        normalized_analysis_run_id,
                        normalized_filter_hash,
                        normalized_selection_json,
                        normalized_resolved_count,
                        normalized_filter_contract,
                        normalized_rank_contract,
                        normalized_selection_contract,
                        normalized_analytics_contract,
                        normalized_member_resolution_contract,
                        normalized_export_contract,
                        normalized_updated_at,
                        normalized_campaign_id,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise CampaignValidationError("Campaign update violated storage constraints.") from exc

            if updated.rowcount != 1:
                raise CampaignValidationError("Campaign update could not be applied.")

    def finalize_campaign(
        self,
        *,
        campaign_id: int,
        finalized_at: str,
    ) -> None:
        normalized_campaign_id = _require_positive_int(campaign_id, field_name="campaign_id")
        normalized_finalized_at = _require_non_empty_text(
            finalized_at,
            field_name="finalized_at",
            maximum=64,
        )

        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status FROM campaigns WHERE campaign_id = ?",
                (normalized_campaign_id,),
            ).fetchone()
            if row is None:
                raise CampaignNotFoundError("Campaign was not found.")
            status = _require_status(row["status"])
            if status != CAMPAIGN_STATUS_DRAFT:
                raise CampaignValidationError("Only DRAFT campaigns can be finalized.")

            try:
                updated = connection.execute(
                    """
                    UPDATE campaigns
                    SET
                        status = 'FINALIZED',
                        updated_at = ?,
                        finalized_at = ?
                    WHERE campaign_id = ? AND status = 'DRAFT'
                    """,
                    (normalized_finalized_at, normalized_finalized_at, normalized_campaign_id),
                )
            except sqlite3.IntegrityError as exc:
                raise CampaignValidationError("Campaign finalization violated storage constraints.") from exc

            if updated.rowcount != 1:
                raise CampaignValidationError("Campaign could not transition to FINALIZED.")


__all__ = (
    "CampaignNotFoundError",
    "CampaignRepository",
    "CampaignRepositoryError",
    "CampaignValidationError",
)
