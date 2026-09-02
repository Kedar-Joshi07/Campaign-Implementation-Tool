"""Repository for aggregate-only audience analytics snapshots."""

from __future__ import annotations

import json
import math
from pathlib import Path
from string import hexdigits
from typing import Any

from app.database.connection import get_connection


MAX_SNAPSHOT_JSON_BYTES = 1_048_576
MAX_JSON_LIST_LENGTH = 2_000

_FORBIDDEN_SNAPSHOT_KEYS = {
    "person_id",
    "person_ids",
    "customer_id",
    "customer_ids",
    "first_name",
    "last_name",
    "address_line_1",
    "address_line_2",
    "street",
    "postal_code",
    "city",
    "email",
    "phone_number",
}


class AudienceAnalyticsSnapshotRepositoryError(RuntimeError):
    """Base class for analytics snapshot persistence errors."""


class AudienceAnalyticsSnapshotValidationError(AudienceAnalyticsSnapshotRepositoryError):
    """Raised when an analytics snapshot payload is invalid."""


def _require_positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AudienceAnalyticsSnapshotValidationError(
            f"{field_name} must be a positive integer."
        )
    return value


def _require_non_empty_text(value: Any, *, field_name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise AudienceAnalyticsSnapshotValidationError(f"{field_name} must be text.")
    normalized = value.strip()
    if not normalized:
        raise AudienceAnalyticsSnapshotValidationError(
            f"{field_name} must not be blank."
        )
    if len(normalized) > maximum:
        raise AudienceAnalyticsSnapshotValidationError(
            f"{field_name} must not exceed {maximum} characters."
        )
    return normalized


def _require_hash64(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise AudienceAnalyticsSnapshotValidationError(f"{field_name} must be text.")
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(char not in hexdigits for char in normalized):
        raise AudienceAnalyticsSnapshotValidationError(
            f"{field_name} must be a 64-character hex digest."
        )
    return normalized


def _contains_forbidden_snapshot_content(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if isinstance(key, str) and key.casefold() in _FORBIDDEN_SNAPSHOT_KEYS:
                return True
            if _contains_forbidden_snapshot_content(nested):
                return True
        return False
    if isinstance(value, list):
        if len(value) > MAX_JSON_LIST_LENGTH:
            return True
        return any(_contains_forbidden_snapshot_content(item) for item in value)
    if isinstance(value, float):
        return not math.isfinite(value)
    return False


def _canonical_json(value: Any, *, field_name: str) -> str:
    if not isinstance(value, dict):
        raise AudienceAnalyticsSnapshotValidationError(f"{field_name} must be an object.")
    if _contains_forbidden_snapshot_content(value):
        raise AudienceAnalyticsSnapshotValidationError(
            f"{field_name} contains forbidden or oversized content."
        )
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise AudienceAnalyticsSnapshotValidationError(
            f"{field_name} contains non-serializable values."
        ) from exc

    encoded_bytes = len(encoded.encode("utf-8"))
    if encoded_bytes > MAX_SNAPSHOT_JSON_BYTES:
        raise AudienceAnalyticsSnapshotValidationError(
            f"{field_name} exceeds {MAX_SNAPSHOT_JSON_BYTES} bytes."
        )
    return encoded


class AudienceAnalyticsSnapshotRepository:
    """Persist and read aggregate-only snapshot payloads for a scoring run."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def upsert_snapshot(
        self,
        *,
        scoring_run_id: int,
        analytics_contract_version: str,
        model_run_id: int,
        analysis_run_id: int,
        customer_import_id: int,
        customer_source_checksum: str,
        campaign_sales_import_id: int,
        campaign_sales_source_checksum: str,
        demographic_import_id: int,
        demographic_source_checksum: str,
        feature_contract_version: str,
        feature_contract_sha256: str,
        artifact_sha256: str,
        filter_contract_version: str,
        rank_contract_version: str,
        selection_contract_version: str,
        population_count: int,
        options_payload: dict[str, Any],
        universe_profile_payload: dict[str, Any],
        historical_positive_profile_payload: dict[str, Any],
        score_bucket_stats_payload: dict[str, Any],
        created_at: str,
    ) -> None:
        normalized_scoring_run_id = _require_positive_int(
            scoring_run_id,
            field_name="scoring_run_id",
        )
        normalized_contract = _require_non_empty_text(
            analytics_contract_version,
            field_name="analytics_contract_version",
            maximum=24,
        )
        normalized_model_run_id = _require_positive_int(
            model_run_id,
            field_name="model_run_id",
        )
        normalized_analysis_run_id = _require_positive_int(
            analysis_run_id,
            field_name="analysis_run_id",
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
        normalized_campaign_checksum = _require_hash64(
            campaign_sales_source_checksum,
            field_name="campaign_sales_source_checksum",
        )
        normalized_demographic_checksum = _require_hash64(
            demographic_source_checksum,
            field_name="demographic_source_checksum",
        )
        normalized_feature_sha = _require_hash64(
            feature_contract_sha256,
            field_name="feature_contract_sha256",
        )
        normalized_artifact_sha = _require_hash64(
            artifact_sha256,
            field_name="artifact_sha256",
        )

        normalized_feature_contract = _require_non_empty_text(
            feature_contract_version,
            field_name="feature_contract_version",
            maximum=24,
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

        normalized_population_count = _require_positive_int(
            population_count,
            field_name="population_count",
        )
        normalized_created_at = _require_non_empty_text(
            created_at,
            field_name="created_at",
            maximum=64,
        )

        options_json = _canonical_json(options_payload, field_name="options_payload")
        universe_json = _canonical_json(
            universe_profile_payload,
            field_name="universe_profile_payload",
        )
        historical_json = _canonical_json(
            historical_positive_profile_payload,
            field_name="historical_positive_profile_payload",
        )
        bucket_json = _canonical_json(
            score_bucket_stats_payload,
            field_name="score_bucket_stats_payload",
        )

        with get_connection(self.database_path, write=True) as connection:
            connection.execute(
                """
                INSERT INTO audience_analytics_snapshots (
                    scoring_run_id,
                    analytics_contract_version,
                    model_run_id,
                    analysis_run_id,
                    customer_import_id,
                    customer_source_checksum,
                    campaign_sales_import_id,
                    campaign_sales_source_checksum,
                    demographic_import_id,
                    demographic_source_checksum,
                    feature_contract_version,
                    feature_contract_sha256,
                    artifact_sha256,
                    filter_contract_version,
                    rank_contract_version,
                    selection_contract_version,
                    population_count,
                    options_json,
                    universe_profile_json,
                    historical_positive_profile_json,
                    score_bucket_stats_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scoring_run_id, analytics_contract_version) DO UPDATE SET
                    model_run_id = excluded.model_run_id,
                    analysis_run_id = excluded.analysis_run_id,
                    customer_import_id = excluded.customer_import_id,
                    customer_source_checksum = excluded.customer_source_checksum,
                    campaign_sales_import_id = excluded.campaign_sales_import_id,
                    campaign_sales_source_checksum = excluded.campaign_sales_source_checksum,
                    demographic_import_id = excluded.demographic_import_id,
                    demographic_source_checksum = excluded.demographic_source_checksum,
                    feature_contract_version = excluded.feature_contract_version,
                    feature_contract_sha256 = excluded.feature_contract_sha256,
                    artifact_sha256 = excluded.artifact_sha256,
                    filter_contract_version = excluded.filter_contract_version,
                    rank_contract_version = excluded.rank_contract_version,
                    selection_contract_version = excluded.selection_contract_version,
                    population_count = excluded.population_count,
                    options_json = excluded.options_json,
                    universe_profile_json = excluded.universe_profile_json,
                    historical_positive_profile_json = excluded.historical_positive_profile_json,
                    score_bucket_stats_json = excluded.score_bucket_stats_json,
                    created_at = excluded.created_at
                """,
                (
                    normalized_scoring_run_id,
                    normalized_contract,
                    normalized_model_run_id,
                    normalized_analysis_run_id,
                    normalized_customer_import_id,
                    normalized_customer_checksum,
                    normalized_campaign_sales_import_id,
                    normalized_campaign_checksum,
                    normalized_demographic_import_id,
                    normalized_demographic_checksum,
                    normalized_feature_contract,
                    normalized_feature_sha,
                    normalized_artifact_sha,
                    normalized_filter_contract,
                    normalized_rank_contract,
                    normalized_selection_contract,
                    normalized_population_count,
                    options_json,
                    universe_json,
                    historical_json,
                    bucket_json,
                    normalized_created_at,
                ),
            )

    def fetch_snapshot(
        self,
        scoring_run_id: int,
        *,
        analytics_contract_version: str,
    ) -> dict[str, Any] | None:
        normalized_scoring_run_id = _require_positive_int(
            scoring_run_id,
            field_name="scoring_run_id",
        )
        normalized_contract = _require_non_empty_text(
            analytics_contract_version,
            field_name="analytics_contract_version",
            maximum=24,
        )

        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM audience_analytics_snapshots
                WHERE scoring_run_id = ? AND analytics_contract_version = ?
                """,
                (normalized_scoring_run_id, normalized_contract),
            ).fetchone()
        return dict(row) if row is not None else None

    def delete_snapshot(
        self,
        scoring_run_id: int,
        *,
        analytics_contract_version: str,
    ) -> None:
        normalized_scoring_run_id = _require_positive_int(
            scoring_run_id,
            field_name="scoring_run_id",
        )
        normalized_contract = _require_non_empty_text(
            analytics_contract_version,
            field_name="analytics_contract_version",
            maximum=24,
        )

        with get_connection(self.database_path, write=True) as connection:
            connection.execute(
                """
                DELETE FROM audience_analytics_snapshots
                WHERE scoring_run_id = ? AND analytics_contract_version = ?
                """,
                (normalized_scoring_run_id, normalized_contract),
            )


__all__ = (
    "MAX_JSON_LIST_LENGTH",
    "MAX_SNAPSHOT_JSON_BYTES",
    "AudienceAnalyticsSnapshotRepository",
    "AudienceAnalyticsSnapshotRepositoryError",
    "AudienceAnalyticsSnapshotValidationError",
)
