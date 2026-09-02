"""Aggregate export-event repository for campaign CSV streaming."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from string import hexdigits
from typing import Any

from app.database.connection import get_connection
from app.services.campaign_contracts import (
    CAMPAIGN_EXPORT_CONTRACT_VERSION,
    EXPORT_PROFILE_DIRECT_MAIL_CONTACT_V1,
    EXPORT_PROFILE_EMAIL_CONTACT_V1,
)

EXPORT_STATUS_STARTED = "STARTED"
EXPORT_STATUS_COMPLETED = "COMPLETED"
EXPORT_STATUS_FAILED = "FAILED"
EXPORT_STATUS_ABORTED = "ABORTED"
EXPORT_STATUSES = (
    EXPORT_STATUS_STARTED,
    EXPORT_STATUS_COMPLETED,
    EXPORT_STATUS_FAILED,
    EXPORT_STATUS_ABORTED,
)


class CampaignExportRepositoryError(RuntimeError):
    """Base class for campaign export repository failures."""


class CampaignExportValidationError(CampaignExportRepositoryError):
    """Raised when export event values are invalid."""


class CampaignExportNotFoundError(CampaignExportRepositoryError):
    """Raised when the requested export event does not exist."""


def _require_positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CampaignExportValidationError(f"{field_name} must be a positive integer.")
    return value


def _require_non_negative_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CampaignExportValidationError(f"{field_name} must be a non-negative integer.")
    return value


def _require_hash64_or_none(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CampaignExportValidationError(f"{field_name} must be text when provided.")
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(char not in hexdigits for char in normalized):
        raise CampaignExportValidationError(f"{field_name} must be a 64-character hex digest.")
    return normalized


def _optional_safe_text(value: Any, *, field_name: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CampaignExportValidationError(f"{field_name} must be text when provided.")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise CampaignExportValidationError(f"{field_name} must not exceed {maximum} characters.")
    return normalized


def _require_non_empty_text(value: Any, *, field_name: str, maximum: int) -> str:
    normalized = _optional_safe_text(value, field_name=field_name, maximum=maximum)
    if normalized is None:
        raise CampaignExportValidationError(f"{field_name} must not be blank.")
    return normalized


def _require_profile(value: Any) -> str:
    profile = _require_non_empty_text(value, field_name="export_profile", maximum=48).upper()
    if profile not in {EXPORT_PROFILE_EMAIL_CONTACT_V1, EXPORT_PROFILE_DIRECT_MAIL_CONTACT_V1}:
        raise CampaignExportValidationError("export_profile is invalid.")
    return profile


def _require_status(value: Any) -> str:
    status = _require_non_empty_text(value, field_name="status", maximum=24).upper()
    if status not in EXPORT_STATUSES:
        raise CampaignExportValidationError("status is invalid.")
    return status


class CampaignExportRepository:
    """Persist aggregate export metadata with safe failure semantics."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def create_started_event(
        self,
        *,
        campaign_id: int,
        export_profile: str,
        started_at: str,
    ) -> int:
        normalized_campaign_id = _require_positive_int(campaign_id, field_name="campaign_id")
        normalized_profile = _require_profile(export_profile)
        normalized_started_at = _require_non_empty_text(started_at, field_name="started_at", maximum=64)

        with get_connection(self.database_path, write=True) as connection:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO campaign_export_events (
                        campaign_id,
                        export_contract_version,
                        export_profile,
                        status,
                        selected_count,
                        deliverable_count,
                        undeliverable_count,
                        row_count,
                        csv_sha256,
                        started_at,
                        completed_at,
                        safe_error_message
                    ) VALUES (?, ?, ?, 'STARTED', 0, 0, 0, 0, NULL, ?, NULL, NULL)
                    """,
                    (
                        normalized_campaign_id,
                        CAMPAIGN_EXPORT_CONTRACT_VERSION,
                        normalized_profile,
                        normalized_started_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise CampaignExportValidationError("Export event creation violated storage constraints.") from exc
        return int(cursor.lastrowid)

    def list_campaign_exports(self, *, campaign_id: int, limit: int = 50) -> list[dict[str, Any]]:
        normalized_campaign_id = _require_positive_int(campaign_id, field_name="campaign_id")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise CampaignExportValidationError("limit must be an integer between 1 and 200.")

        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM campaign_export_events
                WHERE campaign_id = ?
                ORDER BY started_at DESC, export_event_id DESC
                LIMIT ?
                """,
                (normalized_campaign_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def _mark_terminal(
        self,
        *,
        export_event_id: int,
        status: str,
        selected_count: int,
        deliverable_count: int,
        undeliverable_count: int,
        row_count: int,
        csv_sha256: str | None,
        completed_at: str,
        safe_error_message: str | None,
    ) -> None:
        normalized_export_event_id = _require_positive_int(export_event_id, field_name="export_event_id")
        normalized_status = _require_status(status)
        if normalized_status == EXPORT_STATUS_STARTED:
            raise CampaignExportValidationError("Terminal event status cannot be STARTED.")
        normalized_selected_count = _require_non_negative_int(
            selected_count,
            field_name="selected_count",
        )
        normalized_deliverable_count = _require_non_negative_int(
            deliverable_count,
            field_name="deliverable_count",
        )
        normalized_undeliverable_count = _require_non_negative_int(
            undeliverable_count,
            field_name="undeliverable_count",
        )
        normalized_row_count = _require_non_negative_int(row_count, field_name="row_count")
        if normalized_deliverable_count + normalized_undeliverable_count != normalized_selected_count:
            raise CampaignExportValidationError(
                "deliverable_count plus undeliverable_count must equal selected_count."
            )
        if normalized_row_count != normalized_deliverable_count:
            raise CampaignExportValidationError("row_count must equal deliverable_count.")

        normalized_csv_sha256 = _require_hash64_or_none(csv_sha256, field_name="csv_sha256")
        normalized_completed_at = _require_non_empty_text(
            completed_at,
            field_name="completed_at",
            maximum=64,
        )
        normalized_safe_error = _optional_safe_text(
            safe_error_message,
            field_name="safe_error_message",
            maximum=512,
        )

        if normalized_status == EXPORT_STATUS_COMPLETED and normalized_csv_sha256 is None:
            raise CampaignExportValidationError("Completed export events require csv_sha256.")

        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status FROM campaign_export_events WHERE export_event_id = ?",
                (normalized_export_event_id,),
            ).fetchone()
            if row is None:
                raise CampaignExportNotFoundError("Export event was not found.")
            if str(row["status"]).upper() != EXPORT_STATUS_STARTED:
                raise CampaignExportValidationError("Only STARTED export events can transition to terminal states.")

            try:
                updated = connection.execute(
                    """
                    UPDATE campaign_export_events
                    SET
                        status = ?,
                        selected_count = ?,
                        deliverable_count = ?,
                        undeliverable_count = ?,
                        row_count = ?,
                        csv_sha256 = ?,
                        completed_at = ?,
                        safe_error_message = ?
                    WHERE export_event_id = ? AND status = 'STARTED'
                    """,
                    (
                        normalized_status,
                        normalized_selected_count,
                        normalized_deliverable_count,
                        normalized_undeliverable_count,
                        normalized_row_count,
                        normalized_csv_sha256,
                        normalized_completed_at,
                        normalized_safe_error,
                        normalized_export_event_id,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise CampaignExportValidationError("Export event update violated storage constraints.") from exc

            if updated.rowcount != 1:
                raise CampaignExportValidationError("Export event update could not be applied.")

    def mark_completed(
        self,
        *,
        export_event_id: int,
        selected_count: int,
        deliverable_count: int,
        undeliverable_count: int,
        row_count: int,
        csv_sha256: str,
        completed_at: str,
    ) -> None:
        self._mark_terminal(
            export_event_id=export_event_id,
            status=EXPORT_STATUS_COMPLETED,
            selected_count=selected_count,
            deliverable_count=deliverable_count,
            undeliverable_count=undeliverable_count,
            row_count=row_count,
            csv_sha256=csv_sha256,
            completed_at=completed_at,
            safe_error_message=None,
        )

    def mark_failed(
        self,
        *,
        export_event_id: int,
        selected_count: int,
        deliverable_count: int,
        undeliverable_count: int,
        row_count: int,
        completed_at: str,
        safe_error_message: str,
    ) -> None:
        self._mark_terminal(
            export_event_id=export_event_id,
            status=EXPORT_STATUS_FAILED,
            selected_count=selected_count,
            deliverable_count=deliverable_count,
            undeliverable_count=undeliverable_count,
            row_count=row_count,
            csv_sha256=None,
            completed_at=completed_at,
            safe_error_message=safe_error_message,
        )

    def mark_aborted(
        self,
        *,
        export_event_id: int,
        selected_count: int,
        deliverable_count: int,
        undeliverable_count: int,
        row_count: int,
        completed_at: str,
        safe_error_message: str,
    ) -> None:
        self._mark_terminal(
            export_event_id=export_event_id,
            status=EXPORT_STATUS_ABORTED,
            selected_count=selected_count,
            deliverable_count=deliverable_count,
            undeliverable_count=undeliverable_count,
            row_count=row_count,
            csv_sha256=None,
            completed_at=completed_at,
            safe_error_message=safe_error_message,
        )


__all__ = (
    "CampaignExportNotFoundError",
    "CampaignExportRepository",
    "CampaignExportRepositoryError",
    "CampaignExportValidationError",
    "EXPORT_STATUS_ABORTED",
    "EXPORT_STATUS_COMPLETED",
    "EXPORT_STATUS_FAILED",
    "EXPORT_STATUS_STARTED",
)
