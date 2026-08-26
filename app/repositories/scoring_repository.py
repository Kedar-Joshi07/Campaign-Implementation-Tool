"""Persistent scoring-run lifecycle repository for Phase 5 foundations."""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from string import hexdigits
from typing import Any

from app.database.connection import get_connection


SCORING_STATUS_RUNNING = "RUNNING"
SCORING_STATUS_COMPLETED = "COMPLETED"
SCORING_STATUS_FAILED = "FAILED"

MAXIMUM_ERROR_MESSAGE_LENGTH = 4_096
MAXIMUM_SUMMARY_JSON_BYTES = 65_536


class ScoringRepositoryError(RuntimeError):
    """Base class for scoring repository failures."""


class ScoringValidationError(ScoringRepositoryError):
    """Raised when a scoring lifecycle value is invalid."""


class ScoringStateTransitionError(ScoringRepositoryError):
    """Raised when a scoring run transition is invalid."""


def _require_positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ScoringValidationError(f"{field_name} must be a positive integer.")
    return value


def _require_non_negative_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ScoringValidationError(f"{field_name} must be a non-negative integer.")
    return value


def _require_timestamp(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScoringValidationError(f"{field_name} must be a non-empty timestamp string.")
    return value.strip()


def _optional_text(value: Any, *, field_name: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ScoringValidationError(f"{field_name} must be text when provided.")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise ScoringValidationError(f"{field_name} must not exceed {maximum} characters.")
    return normalized


def _required_text(value: Any, *, field_name: str, maximum: int) -> str:
    normalized = _optional_text(value, field_name=field_name, maximum=maximum)
    if normalized is None:
        raise ScoringValidationError(f"{field_name} must not be blank.")
    return normalized


def _require_hash64(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ScoringValidationError(f"{field_name} must be text.")
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(char not in hexdigits for char in normalized):
        raise ScoringValidationError(f"{field_name} must be a 64-character hex digest.")
    return normalized


def _optional_score(value: Any, *, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScoringValidationError(f"{field_name} must be numeric when provided.")
    score = float(value)
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise ScoringValidationError(f"{field_name} must be finite and between 0 and 1.")
    return score


def _canonical_summary_json(summary_payload: dict[str, Any] | None) -> str | None:
    if summary_payload is None:
        return None
    if not isinstance(summary_payload, dict):
        raise ScoringValidationError("score_summary_json payload must be an object.")
    try:
        encoded = json.dumps(
            summary_payload,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ScoringValidationError("score_summary_json payload is invalid.") from exc
    if len(encoded.encode("utf-8")) > MAXIMUM_SUMMARY_JSON_BYTES:
        raise ScoringValidationError("score_summary_json payload is too large.")
    return encoded


class ScoringRepository:
    """Persist bounded Phase 5 scoring-run lifecycle state."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def create_scoring_run(
        self,
        *,
        job_id: int,
        model_run_id: int,
        created_at: str,
        demographic_snapshot_count: int,
        demographic_min_person_id: str | None,
        demographic_max_person_id: str | None,
        chunk_size: int,
        selected_candidate: str,
        model_role_policy_version: str,
        feature_contract_version: str,
        feature_contract_sha256: str,
        artifact_sha256: str,
    ) -> int:
        normalized_job_id = _require_positive_int(job_id, field_name="job_id")
        normalized_model_run_id = _require_positive_int(model_run_id, field_name="model_run_id")
        normalized_created_at = _require_timestamp(created_at, field_name="created_at")
        snapshot_count = _require_non_negative_int(
            demographic_snapshot_count,
            field_name="demographic_snapshot_count",
        )
        if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or not 1000 <= chunk_size <= 100000:
            raise ScoringValidationError("chunk_size must be between 1000 and 100000.")
        selected = _required_text(selected_candidate, field_name="selected_candidate", maximum=120)
        policy_version = _required_text(
            model_role_policy_version,
            field_name="model_role_policy_version",
            maximum=24,
        )
        contract_version = _required_text(
            feature_contract_version,
            field_name="feature_contract_version",
            maximum=24,
        )
        contract_hash = _require_hash64(
            feature_contract_sha256,
            field_name="feature_contract_sha256",
        )
        artifact_hash = _require_hash64(artifact_sha256, field_name="artifact_sha256")

        min_person_id = _optional_text(
            demographic_min_person_id,
            field_name="demographic_min_person_id",
            maximum=128,
        )
        max_person_id = _optional_text(
            demographic_max_person_id,
            field_name="demographic_max_person_id",
            maximum=128,
        )

        with get_connection(self.database_path, write=True) as connection:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO scoring_runs (
                        job_id,
                        model_run_id,
                        created_at,
                        status,
                        demographic_snapshot_count,
                        demographic_min_person_id,
                        demographic_max_person_id,
                        scored_person_count,
                        chunk_size,
                        last_person_id,
                        selected_candidate,
                        model_role_policy_version,
                        feature_contract_version,
                        feature_contract_sha256,
                        artifact_sha256
                    ) VALUES (?, ?, ?, 'RUNNING', ?, ?, ?, 0, ?, NULL, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized_job_id,
                        normalized_model_run_id,
                        normalized_created_at,
                        snapshot_count,
                        min_person_id,
                        max_person_id,
                        chunk_size,
                        selected,
                        policy_version,
                        contract_version,
                        contract_hash,
                        artifact_hash,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ScoringValidationError(
                    "Scoring run creation violated storage constraints."
                ) from exc
        return int(cursor.lastrowid)

    def fetch_scoring_run(self, scoring_run_id: int) -> dict[str, Any] | None:
        normalized_id = _require_positive_int(scoring_run_id, field_name="scoring_run_id")
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM scoring_runs WHERE scoring_run_id = ?",
                (normalized_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def fetch_by_job_id(self, job_id: int) -> dict[str, Any] | None:
        normalized_job_id = _require_positive_int(job_id, field_name="job_id")
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM scoring_runs WHERE job_id = ?",
                (normalized_job_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_scoring_runs(
        self,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        model_run_id: int | None = None,
    ) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ScoringValidationError("limit must be an integer between 1 and 100.")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ScoringValidationError("offset must be a non-negative integer.")
        if status is not None and status not in {
            SCORING_STATUS_RUNNING,
            SCORING_STATUS_COMPLETED,
            SCORING_STATUS_FAILED,
        }:
            raise ScoringValidationError("status filter is invalid.")
        if model_run_id is not None:
            model_run_id = _require_positive_int(model_run_id, field_name="model_run_id")

        predicates: list[str] = []
        parameters: list[Any] = []
        if status is not None:
            predicates.append("status = ?")
            parameters.append(status)
        if model_run_id is not None:
            predicates.append("model_run_id = ?")
            parameters.append(model_run_id)

        where_clause = ""
        if predicates:
            where_clause = "WHERE " + " AND ".join(predicates)

        parameters.extend((limit, offset))
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM scoring_runs
                {where_clause}
                ORDER BY created_at DESC, scoring_run_id DESC
                LIMIT ? OFFSET ?
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def update_counters(
        self,
        *,
        scoring_run_id: int,
        scored_person_count: int,
        last_person_id: str | None,
        score_min: float | None,
        score_max: float | None,
        score_mean: float | None,
    ) -> None:
        normalized_id = _require_positive_int(scoring_run_id, field_name="scoring_run_id")
        if (
            isinstance(scored_person_count, bool)
            or not isinstance(scored_person_count, int)
            or scored_person_count < 0
        ):
            raise ScoringValidationError("scored_person_count must be a non-negative integer.")
        normalized_last_person_id = _optional_text(
            last_person_id,
            field_name="last_person_id",
            maximum=128,
        )
        normalized_score_min = _optional_score(score_min, field_name="score_min")
        normalized_score_max = _optional_score(score_max, field_name="score_max")
        normalized_score_mean = _optional_score(score_mean, field_name="score_mean")

        if (
            normalized_score_min is not None
            and normalized_score_max is not None
            and normalized_score_min > normalized_score_max
        ):
            raise ScoringValidationError("score_min cannot exceed score_max.")
        if (
            normalized_score_mean is not None
            and normalized_score_min is not None
            and normalized_score_mean < normalized_score_min
        ):
            raise ScoringValidationError("score_mean cannot be less than score_min.")
        if (
            normalized_score_mean is not None
            and normalized_score_max is not None
            and normalized_score_mean > normalized_score_max
        ):
            raise ScoringValidationError("score_mean cannot exceed score_max.")

        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM scoring_runs WHERE scoring_run_id = ?",
                (normalized_id,),
            ).fetchone()
            if row is None:
                raise ScoringValidationError("The requested scoring run was not found.")
            if row["status"] != SCORING_STATUS_RUNNING:
                raise ScoringStateTransitionError("Only RUNNING scoring runs accept progress updates.")
            current_count = int(row["scored_person_count"])
            if scored_person_count < current_count:
                raise ScoringStateTransitionError("scored_person_count must be monotonic.")
            if scored_person_count > int(row["demographic_snapshot_count"]):
                raise ScoringValidationError(
                    "scored_person_count cannot exceed demographic_snapshot_count."
                )

            try:
                connection.execute(
                    """
                    UPDATE scoring_runs
                    SET
                        scored_person_count = ?,
                        last_person_id = ?,
                        score_min = ?,
                        score_max = ?,
                        score_mean = ?
                    WHERE scoring_run_id = ? AND status = 'RUNNING'
                    """,
                    (
                        scored_person_count,
                        normalized_last_person_id,
                        normalized_score_min,
                        normalized_score_max,
                        normalized_score_mean,
                        normalized_id,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ScoringValidationError(
                    "Scoring progress update violated storage constraints."
                ) from exc

    def mark_completed(
        self,
        *,
        scoring_run_id: int,
        completed_at: str,
        scored_person_count: int,
        score_min: float,
        score_max: float,
        score_mean: float,
        summary_payload: dict[str, Any] | None,
    ) -> None:
        normalized_id = _require_positive_int(scoring_run_id, field_name="scoring_run_id")
        normalized_completed_at = _require_timestamp(completed_at, field_name="completed_at")
        if (
            isinstance(scored_person_count, bool)
            or not isinstance(scored_person_count, int)
            or scored_person_count < 0
        ):
            raise ScoringValidationError("scored_person_count must be a non-negative integer.")
        normalized_score_min = _optional_score(score_min, field_name="score_min")
        normalized_score_max = _optional_score(score_max, field_name="score_max")
        normalized_score_mean = _optional_score(score_mean, field_name="score_mean")
        if (
            normalized_score_min is None
            or normalized_score_max is None
            or normalized_score_mean is None
        ):
            raise ScoringValidationError("Completed runs require score_min/score_max/score_mean.")
        if normalized_score_min > normalized_score_max:
            raise ScoringValidationError("score_min cannot exceed score_max.")
        if not normalized_score_min <= normalized_score_mean <= normalized_score_max:
            raise ScoringValidationError("score_mean must lie between score_min and score_max.")

        if summary_payload is None or not isinstance(summary_payload, dict) or not summary_payload:
            raise ScoringValidationError("Completed runs require a non-empty score_summary_json payload.")
        summary_json = _canonical_summary_json(summary_payload)

        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM scoring_runs WHERE scoring_run_id = ?",
                (normalized_id,),
            ).fetchone()
            if row is None:
                raise ScoringValidationError("The requested scoring run was not found.")
            if row["status"] != SCORING_STATUS_RUNNING:
                raise ScoringStateTransitionError("Only RUNNING scoring runs can complete.")
            if scored_person_count != int(row["demographic_snapshot_count"]):
                raise ScoringValidationError(
                    "Completed runs must report scored_person_count equal to demographic_snapshot_count."
                )
            if int(row["scored_person_count"]) > scored_person_count:
                raise ScoringStateTransitionError(
                    "scored_person_count must be monotonic at completion."
                )

            try:
                cursor = connection.execute(
                    """
                    UPDATE scoring_runs
                    SET
                        status = 'COMPLETED',
                        completed_at = ?,
                        scored_person_count = ?,
                        score_min = ?,
                        score_max = ?,
                        score_mean = ?,
                        score_summary_json = ?,
                        error_message = NULL
                    WHERE scoring_run_id = ? AND status = 'RUNNING'
                    """,
                    (
                        normalized_completed_at,
                        scored_person_count,
                        normalized_score_min,
                        normalized_score_max,
                        normalized_score_mean,
                        summary_json,
                        normalized_id,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ScoringStateTransitionError(
                    "Scoring run completion violated storage constraints."
                ) from exc
            if cursor.rowcount != 1:
                raise ScoringStateTransitionError("Scoring run could not transition to COMPLETED.")

    def mark_failed(
        self,
        *,
        scoring_run_id: int,
        completed_at: str,
        error_message: str,
        summary_payload: dict[str, Any] | None = None,
    ) -> None:
        normalized_id = _require_positive_int(scoring_run_id, field_name="scoring_run_id")
        normalized_completed_at = _require_timestamp(completed_at, field_name="completed_at")
        normalized_error = _required_text(
            error_message,
            field_name="error_message",
            maximum=MAXIMUM_ERROR_MESSAGE_LENGTH,
        )
        summary_json = _canonical_summary_json(summary_payload)

        with get_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM scoring_runs WHERE scoring_run_id = ?",
                (normalized_id,),
            ).fetchone()
            if row is None:
                raise ScoringValidationError("The requested scoring run was not found.")
            if row["status"] != SCORING_STATUS_RUNNING:
                raise ScoringStateTransitionError("Only RUNNING scoring runs can fail.")

            try:
                cursor = connection.execute(
                    """
                    UPDATE scoring_runs
                    SET
                        status = 'FAILED',
                        completed_at = ?,
                        score_summary_json = COALESCE(?, score_summary_json),
                        error_message = ?
                    WHERE scoring_run_id = ? AND status = 'RUNNING'
                    """,
                    (
                        normalized_completed_at,
                        summary_json,
                        normalized_error,
                        normalized_id,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ScoringStateTransitionError(
                    "Scoring run failure transition violated storage constraints."
                ) from exc
            if cursor.rowcount != 1:
                raise ScoringStateTransitionError("Scoring run could not transition to FAILED.")

    def find_completed_runs_for_model(
        self,
        model_run_id: int,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        normalized_model_run_id = _require_positive_int(model_run_id, field_name="model_run_id")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ScoringValidationError("limit must be an integer between 1 and 1000.")
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM scoring_runs
                WHERE model_run_id = ? AND status = 'COMPLETED'
                ORDER BY completed_at DESC, scoring_run_id DESC
                LIMIT ?
                """,
                (normalized_model_run_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def find_completed_run_for_model(self, model_run_id: int) -> dict[str, Any] | None:
        normalized_model_run_id = _require_positive_int(model_run_id, field_name="model_run_id")
        rows = self.find_completed_runs_for_model(normalized_model_run_id, limit=1)
        return rows[0] if rows else None

    def find_running_run_for_model(self, model_run_id: int) -> dict[str, Any] | None:
        normalized_model_run_id = _require_positive_int(model_run_id, field_name="model_run_id")
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM scoring_runs
                WHERE model_run_id = ? AND status = 'RUNNING'
                ORDER BY created_at DESC, scoring_run_id DESC
                LIMIT 1
                """,
                (normalized_model_run_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def insert_scores_chunk(
        self,
        *,
        scoring_run_id: int,
        model_run_id: int,
        person_ids: list[str],
        propensity_scores: list[float],
    ) -> int:
        normalized_scoring_run_id = _require_positive_int(
            scoring_run_id,
            field_name="scoring_run_id",
        )
        normalized_model_run_id = _require_positive_int(
            model_run_id,
            field_name="model_run_id",
        )
        if len(person_ids) != len(propensity_scores):
            raise ScoringValidationError("person_ids and propensity_scores must have equal length.")
        if not person_ids:
            return 0

        rows: list[tuple[int, int, str, float]] = []
        seen_person_ids: set[str] = set()
        for person_id, score in zip(person_ids, propensity_scores, strict=True):
            normalized_person_id = _required_text(
                person_id,
                field_name="person_id",
                maximum=128,
            )
            if normalized_person_id in seen_person_ids:
                raise ScoringValidationError("person_ids must be unique within a persisted chunk.")
            seen_person_ids.add(normalized_person_id)
            normalized_score = _optional_score(score, field_name="propensity_score")
            if normalized_score is None:
                raise ScoringValidationError("propensity_score must be provided for every row.")
            rows.append(
                (
                    normalized_scoring_run_id,
                    normalized_model_run_id,
                    normalized_person_id,
                    normalized_score,
                )
            )

        with get_connection(self.database_path, write=True) as connection:
            try:
                connection.executemany(
                    """
                    INSERT INTO propensity_scores (
                        scoring_run_id,
                        model_run_id,
                        person_id,
                        propensity_score
                    ) VALUES (?, ?, ?, ?)
                    """,
                    rows,
                )
            except sqlite3.IntegrityError as exc:
                raise ScoringValidationError(
                    "Chunk score persistence violated storage constraints."
                ) from exc
        return len(rows)

    def fetch_score_aggregates(self, scoring_run_id: int) -> dict[str, Any]:
        normalized_scoring_run_id = _require_positive_int(
            scoring_run_id,
            field_name="scoring_run_id",
        )
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS score_count,
                    COUNT(DISTINCT person_id) AS distinct_person_count,
                    MIN(person_id) AS min_person_id,
                    MAX(person_id) AS max_person_id,
                    MIN(propensity_score) AS score_min,
                    MAX(propensity_score) AS score_max,
                    AVG(propensity_score) AS score_mean
                FROM propensity_scores
                WHERE scoring_run_id = ?
                """,
                (normalized_scoring_run_id,),
            ).fetchone()
        aggregates = dict(row)
        aggregates["score_count"] = int(aggregates["score_count"])
        aggregates["distinct_person_count"] = int(aggregates["distinct_person_count"])
        if aggregates["score_count"] > 0:
            aggregates["score_min"] = float(aggregates["score_min"])
            aggregates["score_max"] = float(aggregates["score_max"])
            aggregates["score_mean"] = float(aggregates["score_mean"])
        return aggregates

    def fetch_score_sample(
        self,
        *,
        scoring_run_id: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        normalized_scoring_run_id = _require_positive_int(
            scoring_run_id,
            field_name="scoring_run_id",
        )
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ScoringValidationError("limit must be an integer between 1 and 1000.")

        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT person_id, propensity_score
                FROM propensity_scores
                WHERE scoring_run_id = ?
                ORDER BY person_id
                LIMIT ?
                """,
                (normalized_scoring_run_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def fail_running_scoring_runs(
        self,
        *,
        completed_at: str,
        error_message: str,
    ) -> int:
        normalized_completed_at = _require_timestamp(completed_at, field_name="completed_at")
        normalized_error = _required_text(
            error_message,
            field_name="error_message",
            maximum=MAXIMUM_ERROR_MESSAGE_LENGTH,
        )
        with get_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                """
                UPDATE scoring_runs
                SET
                    status = 'FAILED',
                    completed_at = ?,
                    error_message = ?
                WHERE status = 'RUNNING'
                """,
                (
                    normalized_completed_at,
                    normalized_error,
                ),
            )
        return int(cursor.rowcount)


__all__ = (
    "SCORING_STATUS_COMPLETED",
    "SCORING_STATUS_FAILED",
    "SCORING_STATUS_RUNNING",
    "ScoringRepository",
    "ScoringRepositoryError",
    "ScoringStateTransitionError",
    "ScoringValidationError",
)
