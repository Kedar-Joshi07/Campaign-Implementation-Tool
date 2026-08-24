"""Bounded prospect-universe reads for Phase 5 scoring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from app.database.connection import get_connection
from app.ml.feature_contract import CATEGORICAL_FEATURES, ORDERED_FEATURES


SCORING_READ_COLUMNS = ("person_id", *ORDERED_FEATURES)
MAX_SCORING_CHUNK_LIMIT = 100_000

SCORING_CHUNK_QUERY_INITIAL = """
    SELECT
        person_id,
        age,
        gender,
        state,
        individual_yearly_income,
        marital_status,
        education,
        employment_status,
        resident_status,
        resident_type,
        family_member_count,
        type_of_employment
    FROM demographics
    ORDER BY person_id
    LIMIT ?
"""

SCORING_CHUNK_QUERY_AFTER = """
    SELECT
        person_id,
        age,
        gender,
        state,
        individual_yearly_income,
        marital_status,
        education,
        employment_status,
        resident_status,
        resident_type,
        family_member_count,
        type_of_employment
    FROM demographics
    WHERE person_id > ?
    ORDER BY person_id
    LIMIT ?
"""


@dataclass(frozen=True)
class ProspectPopulationSnapshot:
    demographic_snapshot_count: int
    demographic_min_person_id: str | None
    demographic_max_person_id: str | None


class ProspectScoringRepositoryError(RuntimeError):
    """Base class for prospect-scoring repository failures."""


class ProspectScoringValidationError(ProspectScoringRepositoryError):
    """Raised when invalid read parameters are supplied."""


def _positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ProspectScoringValidationError(f"{field_name} must be a positive integer.")
    if value > MAX_SCORING_CHUNK_LIMIT:
        raise ProspectScoringValidationError(
            f"{field_name} must not exceed {MAX_SCORING_CHUNK_LIMIT}."
        )
    return value


def _optional_cursor(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProspectScoringValidationError("after_person_id must be text when provided.")
    normalized = value.strip()
    if not normalized:
        return None
    return normalized


class ProspectScoringRepository:
    """Expose bounded keyset demographic reads for scoring."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def fetch_prospect_snapshot(self) -> ProspectPopulationSnapshot:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS demographic_snapshot_count,
                    MIN(person_id) AS demographic_min_person_id,
                    MAX(person_id) AS demographic_max_person_id
                FROM demographics
                """
            ).fetchone()
        return ProspectPopulationSnapshot(
            demographic_snapshot_count=int(row["demographic_snapshot_count"]),
            demographic_min_person_id=row["demographic_min_person_id"],
            demographic_max_person_id=row["demographic_max_person_id"],
        )

    def fetch_scoring_chunk(
        self,
        *,
        after_person_id: str | None,
        limit: int,
    ) -> tuple[list[str], pd.DataFrame]:
        normalized_limit = _positive_int(limit, field_name="limit")
        normalized_after_person_id = _optional_cursor(after_person_id)

        with get_connection(self.database_path) as connection:
            if normalized_after_person_id is None:
                rows = connection.execute(
                    SCORING_CHUNK_QUERY_INITIAL,
                    (normalized_limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    SCORING_CHUNK_QUERY_AFTER,
                    (normalized_after_person_id, normalized_limit),
                ).fetchall()

        person_ids = [str(row["person_id"]) for row in rows]
        if not rows:
            empty_frame = pd.DataFrame(columns=ORDERED_FEATURES)
            for column in ORDERED_FEATURES:
                if column in {"age", "family_member_count"}:
                    empty_frame[column] = empty_frame[column].astype("Int64")
                elif column == "individual_yearly_income":
                    empty_frame[column] = empty_frame[column].astype("Float64")
                else:
                    empty_frame[column] = empty_frame[column].astype("string")
            return person_ids, empty_frame

        frame = pd.DataFrame.from_records(rows, columns=SCORING_READ_COLUMNS)
        feature_frame = frame.loc[:, ORDERED_FEATURES].copy()
        feature_frame["age"] = feature_frame["age"].astype("Int64")
        feature_frame["individual_yearly_income"] = feature_frame[
            "individual_yearly_income"
        ].astype("Float64")
        feature_frame["family_member_count"] = feature_frame["family_member_count"].astype(
            "Int64"
        )
        for column in CATEGORICAL_FEATURES:
            feature_frame[column] = feature_frame[column].astype("string")

        return person_ids, feature_frame

    def fetch_features_for_person_ids(
        self,
        *,
        person_ids: list[str],
    ) -> tuple[list[str], pd.DataFrame]:
        if not person_ids:
            raise ProspectScoringValidationError("person_ids must contain at least one value.")
        if len(person_ids) > 1000:
            raise ProspectScoringValidationError("person_ids sample size must not exceed 1000.")

        normalized_ids: list[str] = []
        seen: set[str] = set()
        for person_id in person_ids:
            if not isinstance(person_id, str) or not person_id.strip():
                raise ProspectScoringValidationError("person_ids must contain non-empty strings.")
            normalized = person_id.strip()
            if normalized in seen:
                raise ProspectScoringValidationError("person_ids must be unique.")
            seen.add(normalized)
            normalized_ids.append(normalized)

        placeholders = ",".join("?" for _ in normalized_ids)
        query = f"""
            SELECT
                person_id,
                age,
                gender,
                state,
                individual_yearly_income,
                marital_status,
                education,
                employment_status,
                resident_status,
                resident_type,
                family_member_count,
                type_of_employment
            FROM demographics
            WHERE person_id IN ({placeholders})
            ORDER BY person_id
        """

        with get_connection(self.database_path) as connection:
            rows = connection.execute(query, normalized_ids).fetchall()

        resolved_person_ids = [str(row["person_id"]) for row in rows]
        frame = pd.DataFrame.from_records(rows, columns=SCORING_READ_COLUMNS)
        feature_frame = frame.loc[:, ORDERED_FEATURES].copy()
        feature_frame["age"] = feature_frame["age"].astype("Int64")
        feature_frame["individual_yearly_income"] = feature_frame[
            "individual_yearly_income"
        ].astype("Float64")
        feature_frame["family_member_count"] = feature_frame["family_member_count"].astype(
            "Int64"
        )
        for column in CATEGORICAL_FEATURES:
            feature_frame[column] = feature_frame[column].astype("string")

        return resolved_person_ids, feature_frame


__all__ = (
    "ProspectPopulationSnapshot",
    "ProspectScoringRepository",
    "ProspectScoringRepositoryError",
    "ProspectScoringValidationError",
    "MAX_SCORING_CHUNK_LIMIT",
    "SCORING_CHUNK_QUERY_AFTER",
    "SCORING_CHUNK_QUERY_INITIAL",
    "SCORING_READ_COLUMNS",
)
