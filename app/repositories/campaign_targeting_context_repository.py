"""Persistence and reference-data queries for Phase 9 campaign context."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.database.connection import get_connection


PRODUCT_OPTION_LIMIT = 250
DIMENSION_OPTION_LIMIT = 100


class CampaignTargetingContextRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def fetch_context_options(self) -> dict[str, Any]:
        with get_connection(self.database_path) as connection:
            products = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT
                        TRIM(product_id) AS product_id,
                        COALESCE(
                            MIN(NULLIF(TRIM(product_name), '')),
                            TRIM(product_id)
                        ) AS product_name,
                        COALESCE(
                            MIN(NULLIF(TRIM(product_category), '')),
                            ''
                        ) AS product_category
                    FROM campaign_sales
                    WHERE NULLIF(TRIM(product_id), '') IS NOT NULL
                    GROUP BY TRIM(product_id)
                    ORDER BY product_id COLLATE NOCASE, product_id
                    LIMIT ?
                    """,
                    (PRODUCT_OPTION_LIMIT,),
                ).fetchall()
            ]
            return {
                "products": products,
                "campaign_types": self._distinct_values(connection, "campaign_type"),
                "campaign_categories": self._distinct_values(
                    connection, "campaign_category"
                ),
                "offer_types": self._distinct_values(connection, "offer_type"),
                "historical_campaign_channels": self._distinct_values(
                    connection, "campaign_channel"
                ),
            }

    def fetch_targeting_options(self) -> dict[str, Any]:
        """Read business-targeting vocabularies from the current demographics data."""

        fields = {
            "genders": "gender",
            "states": "state",
            "marital_statuses": "marital_status",
            "education_levels": "education",
            "employment_statuses": "employment_status",
            "resident_statuses": "resident_status",
            "resident_types": "resident_type",
            "employment_types": "type_of_employment",
        }
        with get_connection(self.database_path) as connection:
            values = {
                response_field: self._demographic_values(connection, column)
                for response_field, column in fields.items()
            }
            family_range = connection.execute(
                """
                SELECT
                    MIN(family_member_count) AS minimum,
                    MAX(family_member_count) AS maximum
                FROM demographics
                """
            ).fetchone()
        values["family_size_minimum"] = family_range["minimum"]
        values["family_size_maximum"] = family_range["maximum"]
        return values

    @staticmethod
    def _demographic_values(connection, column: str) -> list[str]:
        allowed_columns = {
            "gender",
            "state",
            "marital_status",
            "education",
            "employment_status",
            "resident_status",
            "resident_type",
            "type_of_employment",
        }
        if column not in allowed_columns:
            raise ValueError("unsupported targeting option column")
        rows = connection.execute(
            f"""
            SELECT DISTINCT
                COALESCE(
                    NULLIF(TRIM(CAST({column} AS TEXT)), ''),
                    'Unknown/Other'
                ) AS value
            FROM demographics
            ORDER BY value COLLATE NOCASE, value
            LIMIT ?
            """,
            (DIMENSION_OPTION_LIMIT,),
        ).fetchall()
        return [str(row["value"]) for row in rows]

    @staticmethod
    def _distinct_values(connection, column: str) -> list[str]:
        allowed_columns = {
            "campaign_type",
            "campaign_category",
            "offer_type",
            "campaign_channel",
        }
        if column not in allowed_columns:
            raise ValueError("unsupported campaign context option column")
        rows = connection.execute(
            f"""
            SELECT DISTINCT TRIM({column}) AS value
            FROM campaign_sales
            WHERE NULLIF(TRIM({column}), '') IS NOT NULL
            ORDER BY value COLLATE NOCASE, value
            LIMIT ?
            """,
            (DIMENSION_OPTION_LIMIT,),
        ).fetchall()
        return [str(row["value"]) for row in rows]

    def create_context(
        self,
        *,
        campaign_context_contract_version: str,
        targeting_segment_contract_version: str,
        business_match_strength_contract_version: str,
        campaign_context_json: str,
        campaign_context_sha256: str,
        targeting_criteria_json: str,
        targeting_criteria_sha256: str,
        timestamp: str,
    ) -> int:
        with get_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                """
                INSERT INTO campaign_targeting_contexts (
                    campaign_targeting_context_contract_version,
                    targeting_segment_contract_version,
                    business_match_strength_contract_version,
                    campaign_context_json,
                    campaign_context_sha256,
                    targeting_criteria_json,
                    targeting_criteria_sha256,
                    source_scoring_run_id,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    campaign_context_contract_version,
                    targeting_segment_contract_version,
                    business_match_strength_contract_version,
                    campaign_context_json,
                    campaign_context_sha256,
                    targeting_criteria_json,
                    targeting_criteria_sha256,
                    timestamp,
                    timestamp,
                ),
            )
            return int(cursor.lastrowid)

    def update_context(
        self,
        *,
        targeting_context_id: int,
        campaign_context_contract_version: str,
        campaign_context_json: str,
        campaign_context_sha256: str,
        timestamp: str,
    ) -> bool:
        with get_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                """
                UPDATE campaign_targeting_contexts
                SET campaign_targeting_context_contract_version = ?,
                    campaign_context_json = ?,
                    campaign_context_sha256 = ?,
                    updated_at = ?
                WHERE targeting_context_id = ?
                """,
                (
                    campaign_context_contract_version,
                    campaign_context_json,
                    campaign_context_sha256,
                    timestamp,
                    targeting_context_id,
                ),
            )
            return cursor.rowcount == 1

    def update_targeting_criteria(
        self,
        *,
        targeting_context_id: int,
        targeting_segment_contract_version: str,
        business_match_strength_contract_version: str,
        targeting_criteria_json: str,
        targeting_criteria_sha256: str,
        timestamp: str,
    ) -> bool:
        with get_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                """
                UPDATE campaign_targeting_contexts
                SET targeting_segment_contract_version = ?,
                    business_match_strength_contract_version = ?,
                    targeting_criteria_json = ?,
                    targeting_criteria_sha256 = ?,
                    updated_at = ?
                WHERE targeting_context_id = ?
                """,
                (
                    targeting_segment_contract_version,
                    business_match_strength_contract_version,
                    targeting_criteria_json,
                    targeting_criteria_sha256,
                    timestamp,
                    targeting_context_id,
                ),
            )
            return cursor.rowcount == 1

    def fetch_targeting_criteria(
        self, targeting_context_id: int
    ) -> dict[str, Any] | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                    targeting_context_id,
                    targeting_segment_contract_version,
                    business_match_strength_contract_version,
                    targeting_criteria_json,
                    targeting_criteria_sha256,
                    source_scoring_run_id,
                    updated_at
                FROM campaign_targeting_contexts
                WHERE targeting_context_id = ?
                """,
                (targeting_context_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def set_source_scoring_run_id(
        self,
        *,
        targeting_context_id: int,
        scoring_run_id: int | None,
        timestamp: str,
    ) -> bool:
        with get_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                """
                UPDATE campaign_targeting_contexts
                SET source_scoring_run_id = ?, updated_at = ?
                WHERE targeting_context_id = ?
                """,
                (scoring_run_id, timestamp, targeting_context_id),
            )
            return cursor.rowcount == 1

    def create_saved_target_group(
        self,
        *,
        audience_id: int,
        targeting_context_id: int,
        target_group_contract_version: str,
        filter_branches_json: str,
        filter_branches_sha256: str,
        campaign_context_contract_version: str,
        campaign_context_json: str,
        campaign_context_sha256: str,
        targeting_segment_contract_version: str,
        business_match_strength_contract_version: str,
        targeting_criteria_json: str,
        targeting_criteria_sha256: str,
        source_scoring_run_id: int,
        resolved_count: int,
        created_at: str,
    ) -> None:
        with get_connection(self.database_path, write=True) as connection:
            connection.execute(
                """
                INSERT INTO phase9_saved_target_groups (
                    audience_id,
                    targeting_context_id,
                    target_group_contract_version,
                    filter_branches_json,
                    filter_branches_sha256,
                    campaign_context_contract_version,
                    campaign_context_json,
                    campaign_context_sha256,
                    targeting_segment_contract_version,
                    business_match_strength_contract_version,
                    targeting_criteria_json,
                    targeting_criteria_sha256,
                    source_scoring_run_id,
                    source_status,
                    resolved_count,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'READY', ?, ?)
                """,
                (
                    audience_id,
                    targeting_context_id,
                    target_group_contract_version,
                    filter_branches_json,
                    filter_branches_sha256,
                    campaign_context_contract_version,
                    campaign_context_json,
                    campaign_context_sha256,
                    targeting_segment_contract_version,
                    business_match_strength_contract_version,
                    targeting_criteria_json,
                    targeting_criteria_sha256,
                    source_scoring_run_id,
                    resolved_count,
                    created_at,
                ),
            )

    def fetch_saved_target_group(self, audience_id: int) -> dict[str, Any] | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM phase9_saved_target_groups
                WHERE audience_id = ?
                """,
                (audience_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def fetch_latest_saved_target_group_for_context(
        self, targeting_context_id: int
    ) -> dict[str, Any] | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM phase9_saved_target_groups
                WHERE targeting_context_id = ?
                ORDER BY created_at DESC, audience_id DESC
                LIMIT 1
                """,
                (targeting_context_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def attach_campaign(
        self,
        *,
        targeting_context_id: int,
        campaign_id: int,
        timestamp: str,
    ) -> bool:
        with get_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                """
                UPDATE campaign_targeting_contexts
                SET campaign_id = ?, updated_at = ?
                WHERE targeting_context_id = ?
                  AND (campaign_id IS NULL OR campaign_id = ?)
                """,
                (campaign_id, timestamp, targeting_context_id, campaign_id),
            )
            return cursor.rowcount == 1

    def fetch_targeting_source_details(
        self, scoring_run_id: int
    ) -> dict[str, Any] | None:
        """Fetch only the explicitly identified source; never apply latest fallback."""

        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                    s.scoring_run_id,
                    s.status AS scoring_status,
                    s.model_run_id,
                    s.selected_candidate,
                    s.model_role_policy_version,
                    s.feature_contract_version,
                    s.feature_contract_sha256,
                    s.artifact_sha256,
                    s.score_summary_json,
                    m.analysis_run_id,
                    h.filters_json AS analysis_filters_json
                FROM scoring_runs AS s
                LEFT JOIN model_runs AS m ON m.model_run_id = s.model_run_id
                LEFT JOIN historical_analysis_runs AS h
                    ON h.analysis_run_id = m.analysis_run_id
                WHERE s.scoring_run_id = ?
                """,
                (scoring_run_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def fetch_context(self, targeting_context_id: int) -> dict[str, Any] | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                    targeting_context_id,
                    campaign_id,
                    campaign_targeting_context_contract_version,
                    targeting_segment_contract_version,
                    business_match_strength_contract_version,
                    campaign_context_json,
                    campaign_context_sha256,
                    targeting_criteria_json,
                    targeting_criteria_sha256,
                    source_scoring_run_id,
                    created_at,
                    updated_at
                FROM campaign_targeting_contexts
                WHERE targeting_context_id = ?
                """,
                (targeting_context_id,),
            ).fetchone()
        return dict(row) if row is not None else None


__all__ = ("CampaignTargetingContextRepository",)
