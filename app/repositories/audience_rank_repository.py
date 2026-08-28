"""Persistence helpers for percentile boundary rows used by Phase 6 audience preparation."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from app.database.connection import get_connection


class AudienceRankRepositoryError(RuntimeError):
    """Base class for audience rank boundary repository failures."""


class AudienceRankValidationError(AudienceRankRepositoryError):
    """Raised when boundary payloads violate repository invariants."""


def _require_positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AudienceRankValidationError(f"{field_name} must be a positive integer.")
    return value


def _require_timestamp(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AudienceRankValidationError(f"{field_name} must be a non-empty timestamp string.")
    return value.strip()


def _require_non_empty_text(value: Any, *, field_name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise AudienceRankValidationError(f"{field_name} must be text.")
    normalized = value.strip()
    if not normalized:
        raise AudienceRankValidationError(f"{field_name} must not be blank.")
    if len(normalized) > maximum:
        raise AudienceRankValidationError(f"{field_name} must not exceed {maximum} characters.")
    return normalized


def _require_score(value: Any, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AudienceRankValidationError(f"{field_name} must be numeric.")
    score = float(value)
    if not math.isfinite(score) or not 0 <= score <= 1:
        raise AudienceRankValidationError(f"{field_name} must be finite and between 0 and 1.")
    return score


class AudienceRankRepository:
    """Read/write `audience_rank_boundaries` rows with strict boundary guards."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def replace_boundaries(
        self,
        *,
        scoring_run_id: int,
        rank_contract_version: str,
        created_at: str,
        boundaries: list[dict[str, Any]],
    ) -> None:
        normalized_scoring_run_id = _require_positive_int(scoring_run_id, field_name="scoring_run_id")
        normalized_rank_contract = _require_non_empty_text(
            rank_contract_version,
            field_name="rank_contract_version",
            maximum=24,
        )
        normalized_created_at = _require_timestamp(created_at, field_name="created_at")

        if len(boundaries) != 100:
            raise AudienceRankValidationError("Exactly 100 percentile boundaries are required.")

        rows: list[tuple[int, int, int, float, str, int, str, str]] = []
        seen_buckets: set[int] = set()
        for boundary in boundaries:
            if not isinstance(boundary, dict):
                raise AudienceRankValidationError("Each boundary must be an object.")
            bucket = _require_positive_int(
                boundary.get("percentile_bucket"),
                field_name="percentile_bucket",
            )
            if not 1 <= bucket <= 100:
                raise AudienceRankValidationError("percentile_bucket must be between 1 and 100.")
            if bucket in seen_buckets:
                raise AudienceRankValidationError("percentile_bucket values must be unique.")
            seen_buckets.add(bucket)

            boundary_rank = _require_positive_int(
                boundary.get("boundary_rank"),
                field_name="boundary_rank",
            )
            total_population = _require_positive_int(
                boundary.get("total_population"),
                field_name="total_population",
            )
            if boundary_rank > total_population:
                raise AudienceRankValidationError(
                    "boundary_rank cannot exceed total_population."
                )
            if bucket == 100 and boundary_rank != total_population:
                raise AudienceRankValidationError(
                    "The 100th percentile boundary_rank must equal total_population."
                )

            boundary_score = _require_score(boundary.get("boundary_score"), field_name="boundary_score")
            boundary_person_id = _require_non_empty_text(
                boundary.get("boundary_person_id"),
                field_name="boundary_person_id",
                maximum=128,
            )

            rows.append(
                (
                    normalized_scoring_run_id,
                    bucket,
                    boundary_rank,
                    boundary_score,
                    boundary_person_id,
                    total_population,
                    normalized_rank_contract,
                    normalized_created_at,
                )
            )

        if seen_buckets != set(range(1, 101)):
            raise AudienceRankValidationError("percentile_bucket values must cover all integers from 1 to 100.")

        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM audience_rank_boundaries WHERE scoring_run_id = ?",
                (normalized_scoring_run_id,),
            )
            connection.executemany(
                """
                INSERT INTO audience_rank_boundaries (
                    scoring_run_id,
                    percentile_bucket,
                    boundary_rank,
                    boundary_score,
                    boundary_person_id,
                    total_population,
                    rank_contract_version,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def fetch_boundaries(self, scoring_run_id: int) -> list[dict[str, Any]]:
        normalized_scoring_run_id = _require_positive_int(scoring_run_id, field_name="scoring_run_id")
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    scoring_run_id,
                    percentile_bucket,
                    boundary_rank,
                    boundary_score,
                    boundary_person_id,
                    total_population,
                    rank_contract_version,
                    created_at
                FROM audience_rank_boundaries
                WHERE scoring_run_id = ?
                ORDER BY percentile_bucket ASC
                """,
                (normalized_scoring_run_id,),
            ).fetchall()
        return [dict(row) for row in rows]


__all__ = (
    "AudienceRankRepository",
    "AudienceRankRepositoryError",
    "AudienceRankValidationError",
)
