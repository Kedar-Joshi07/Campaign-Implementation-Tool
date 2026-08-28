"""Immutable repository for saved audience definitions and provenance."""

from __future__ import annotations

import json
from pathlib import Path
from string import hexdigits
from typing import Any

from app.database.connection import get_connection


SELECTION_MODE_ALL_MATCHING = "ALL_MATCHING"
SELECTION_MODE_TOP_N = "TOP_N"


class SavedAudienceRepositoryError(RuntimeError):
    """Base class for saved audience repository failures."""


class SavedAudienceValidationError(SavedAudienceRepositoryError):
    """Raised when saved audience payload constraints are violated."""


class SavedAudienceNotFoundError(SavedAudienceRepositoryError):
    """Raised when a requested audience id does not exist."""


def _require_positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SavedAudienceValidationError(f"{field_name} must be a positive integer.")
    return value


def _require_optional_positive_int(value: Any, *, field_name: str) -> int | None:
    if value is None:
        return None
    return _require_positive_int(value, field_name=field_name)


def _require_non_empty_text(value: Any, *, field_name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise SavedAudienceValidationError(f"{field_name} must be text.")
    normalized = value.strip()
    if not normalized:
        raise SavedAudienceValidationError(f"{field_name} must not be blank.")
    if len(normalized) > maximum:
        raise SavedAudienceValidationError(f"{field_name} must not exceed {maximum} characters.")
    return normalized


def _optional_bounded_text(value: Any, *, field_name: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SavedAudienceValidationError(f"{field_name} must be text when provided.")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise SavedAudienceValidationError(f"{field_name} must not exceed {maximum} characters.")
    return normalized


def _canonical_json(value: Any, *, field_name: str) -> str:
    if not isinstance(value, dict):
        raise SavedAudienceValidationError(f"{field_name} must be an object.")
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise SavedAudienceValidationError(f"{field_name} contains non-serializable values.") from exc
    if encoded == "{}":
        raise SavedAudienceValidationError(f"{field_name} must not be empty.")
    return encoded


def _require_hash64(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise SavedAudienceValidationError(f"{field_name} must be text.")
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(char not in hexdigits for char in normalized):
        raise SavedAudienceValidationError(f"{field_name} must be a 64-character hex digest.")
    return normalized


class SavedAudienceRepository:
    """Persist and read immutable saved audience definitions and provenance."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def create_saved_audience(
        self,
        *,
        audience_name: str,
        description: str | None,
        created_at: str,
        scoring_run_id: int,
        model_run_id: int,
        analysis_run_id: int,
        selection_mode: str,
        target_count: int | None,
        resolved_count: int,
        filter_contract_version: str,
        rank_contract_version: str,
        selection_contract_version: str,
        filters_payload: dict[str, Any],
        selection_payload: dict[str, Any],
        profile_summary_payload: dict[str, Any] | None,
        customer_import_id: int,
        customer_source_checksum: str,
        campaign_sales_import_id: int,
        campaign_sales_source_checksum: str,
        demographic_import_id: int,
        demographic_source_checksum: str,
        feature_contract_version: str,
        feature_contract_sha256: str,
        artifact_sha256: str,
    ) -> int:
        normalized_name = _require_non_empty_text(
            audience_name,
            field_name="audience_name",
            maximum=120,
        )
        normalized_description = _optional_bounded_text(
            description,
            field_name="description",
            maximum=500,
        )
        normalized_created_at = _require_non_empty_text(
            created_at,
            field_name="created_at",
            maximum=64,
        )
        normalized_scoring_run_id = _require_positive_int(scoring_run_id, field_name="scoring_run_id")
        normalized_model_run_id = _require_positive_int(model_run_id, field_name="model_run_id")
        normalized_analysis_run_id = _require_positive_int(analysis_run_id, field_name="analysis_run_id")
        normalized_resolved_count = _require_positive_int(resolved_count, field_name="resolved_count")

        if selection_mode not in {SELECTION_MODE_ALL_MATCHING, SELECTION_MODE_TOP_N}:
            raise SavedAudienceValidationError("selection_mode is invalid.")
        normalized_target_count = _require_optional_positive_int(
            target_count,
            field_name="target_count",
        )
        if selection_mode == SELECTION_MODE_TOP_N and normalized_target_count is None:
            raise SavedAudienceValidationError("target_count is required when selection_mode is TOP_N.")
        if selection_mode == SELECTION_MODE_ALL_MATCHING and normalized_target_count is not None:
            raise SavedAudienceValidationError(
                "target_count must be null when selection_mode is ALL_MATCHING."
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
        normalized_feature_contract = _require_non_empty_text(
            feature_contract_version,
            field_name="feature_contract_version",
            maximum=24,
        )

        filters_json = _canonical_json(filters_payload, field_name="filters_payload")
        selection_json = _canonical_json(selection_payload, field_name="selection_payload")
        profile_summary_json = (
            None
            if profile_summary_payload is None
            else _canonical_json(profile_summary_payload, field_name="profile_summary_payload")
        )

        normalized_customer_import_id = _require_positive_int(
            customer_import_id,
            field_name="customer_import_id",
        )
        normalized_campaign_sales_import_id = _require_positive_int(
            campaign_sales_import_id,
            field_name="campaign_sales_import_id",
        )
        normalized_demographic_import_id = _require_positive_int(
            demographic_import_id,
            field_name="demographic_import_id",
        )

        normalized_customer_checksum = _require_hash64(
            customer_source_checksum,
            field_name="customer_source_checksum",
        )
        normalized_campaign_sales_checksum = _require_hash64(
            campaign_sales_source_checksum,
            field_name="campaign_sales_source_checksum",
        )
        normalized_demographic_checksum = _require_hash64(
            demographic_source_checksum,
            field_name="demographic_source_checksum",
        )
        normalized_feature_contract_sha = _require_hash64(
            feature_contract_sha256,
            field_name="feature_contract_sha256",
        )
        normalized_artifact_sha = _require_hash64(
            artifact_sha256,
            field_name="artifact_sha256",
        )

        with get_connection(self.database_path, write=True) as connection:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO saved_audiences (
                        audience_name,
                        description,
                        created_at,
                        scoring_run_id,
                        model_run_id,
                        analysis_run_id,
                        selection_mode,
                        target_count,
                        resolved_count,
                        filter_contract_version,
                        rank_contract_version,
                        selection_contract_version,
                        filters_json,
                        selection_json,
                        profile_summary_json,
                        customer_import_id,
                        customer_source_checksum,
                        campaign_sales_import_id,
                        campaign_sales_source_checksum,
                        demographic_import_id,
                        demographic_source_checksum,
                        feature_contract_version,
                        feature_contract_sha256,
                        artifact_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized_name,
                        normalized_description,
                        normalized_created_at,
                        normalized_scoring_run_id,
                        normalized_model_run_id,
                        normalized_analysis_run_id,
                        selection_mode,
                        normalized_target_count,
                        normalized_resolved_count,
                        normalized_filter_contract,
                        normalized_rank_contract,
                        normalized_selection_contract,
                        filters_json,
                        selection_json,
                        profile_summary_json,
                        normalized_customer_import_id,
                        normalized_customer_checksum,
                        normalized_campaign_sales_import_id,
                        normalized_campaign_sales_checksum,
                        normalized_demographic_import_id,
                        normalized_demographic_checksum,
                        normalized_feature_contract,
                        normalized_feature_contract_sha,
                        normalized_artifact_sha,
                    ),
                )
            except Exception as exc:
                raise SavedAudienceValidationError(
                    "Saved audience write violated storage constraints."
                ) from exc
        return int(cursor.lastrowid)

    def fetch_saved_audience(self, audience_id: int) -> dict[str, Any]:
        normalized_audience_id = _require_positive_int(audience_id, field_name="audience_id")
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM saved_audiences WHERE audience_id = ?",
                (normalized_audience_id,),
            ).fetchone()
        if row is None:
            raise SavedAudienceNotFoundError("Saved audience was not found.")
        return dict(row)

    def list_saved_audiences(
        self,
        *,
        limit: int,
        offset: int,
        scoring_run_id: int | None = None,
        model_run_id: int | None = None,
    ) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise SavedAudienceValidationError("limit must be an integer between 1 and 200.")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise SavedAudienceValidationError("offset must be a non-negative integer.")

        normalized_scoring_run_id = None
        if scoring_run_id is not None:
            normalized_scoring_run_id = _require_positive_int(
                scoring_run_id,
                field_name="scoring_run_id",
            )

        normalized_model_run_id = None
        if model_run_id is not None:
            normalized_model_run_id = _require_positive_int(
                model_run_id,
                field_name="model_run_id",
            )

        predicates: list[str] = []
        parameters: list[Any] = []
        if normalized_scoring_run_id is not None:
            predicates.append("scoring_run_id = ?")
            parameters.append(normalized_scoring_run_id)
        if normalized_model_run_id is not None:
            predicates.append("model_run_id = ?")
            parameters.append(normalized_model_run_id)

        where_clause = ""
        if predicates:
            where_clause = "WHERE " + " AND ".join(predicates)

        parameters.extend((limit, offset))
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM saved_audiences
                {where_clause}
                ORDER BY created_at DESC, audience_id DESC
                LIMIT ? OFFSET ?
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]


__all__ = (
    "SELECTION_MODE_ALL_MATCHING",
    "SELECTION_MODE_TOP_N",
    "SavedAudienceNotFoundError",
    "SavedAudienceRepository",
    "SavedAudienceRepositoryError",
    "SavedAudienceValidationError",
)
