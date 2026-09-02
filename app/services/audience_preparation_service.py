"""Deterministic audience rank preparation orchestration and helpers for Phase 6 Step 3."""

from __future__ import annotations

import math
import json
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories.audience_rank_repository import AudienceRankRepository
from app.repositories.audience_analytics_snapshot_repository import (
    AudienceAnalyticsSnapshotRepository,
)
from app.repositories.historical_repository import (
    HistoricalRepository,
    build_matching_observations_cte,
)
from app.repositories.job_repository import (
    ActiveComputeJobConflictError,
    JobRepository,
    JobValidationError,
)
from app.repositories.model_run_repository import ModelRunRepository
from app.repositories.scoring_repository import (
    MAXIMUM_SCORE_SCAN_CHUNK_SIZE,
    MINIMUM_SCORE_SCAN_CHUNK_SIZE,
    ScoringRepository,
)
from app.schemas.historical import HistoricalAnalysisFilters
from app.ml.evaluation import EVALUATION_CONTRACT_VERSION
from app.ml.model_roles import (
    CHALLENGER_1_MODEL_NAME,
    DIAGNOSTIC_CONTROL_NAME,
    MODEL_ROLE_POLICY_VERSION,
    PRIMARY_MODEL_NAME,
    PRIMARY_ROLE_GOVERNED_SELECTION,
)
from app.services.prospect_scoring_service import (
    find_current_canonical_run_for_model_lightweight,
    resolve_current_scoring_context_lightweight,
    validate_completed_scoring_run_integrity_deep,
)


DEFAULT_RANK_CONTRACT_VERSION = "1"
SUPPORTED_RANK_CONTRACT_VERSIONS = {DEFAULT_RANK_CONTRACT_VERSION}
AUDIENCE_ANALYTICS_CONTRACT_VERSION = "1"
SUPPORTED_AUDIENCE_ANALYTICS_CONTRACT_VERSIONS = {
    AUDIENCE_ANALYTICS_CONTRACT_VERSION
}
AUDIENCE_FILTER_CONTRACT_VERSION = "1"
AUDIENCE_SELECTION_CONTRACT_VERSION = "1"
DEFAULT_PREPARATION_SCAN_CHUNK_SIZE = 100_000
MAXIMUM_INTERNAL_ERROR_LENGTH = 4_096
MAXIMUM_CURRENTNESS_ISSUES = 5
MAXIMUM_CURRENTNESS_ISSUE_LENGTH = 160

SCORING_RUN_NOT_FOUND_MESSAGE = "The requested scoring run was not found."
SCORING_RUN_NOT_COMPLETED_MESSAGE = "The requested scoring run is not completed."
SCORING_RUN_NOT_CANONICAL_MESSAGE = (
    "The requested scoring run is not current for its model and source provenance."
)
RANK_BOUNDARIES_NOT_READY_MESSAGE = "Audience rank boundaries are not prepared for this scoring run."
SCORING_COUNT_MISMATCH_MESSAGE = "Scoring row count does not match completed scoring metadata."
EXISTING_AUDIENCE_PREPARATION_CONFLICT_MESSAGE = (
    "Audience rank boundaries already exist for this scoring run and contract."
)
ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE = "A compute job is already active."
AUDIENCE_PREPARATION_SUBMISSION_FAILURE_MESSAGE = "Audience preparation could not be completed."

_AUDIENCE_CATEGORICAL_FIELDS = (
    "gender",
    "state",
    "marital_status",
    "education",
    "employment_status",
    "resident_status",
    "resident_type",
    "type_of_employment",
)

_PROFILE_DIMENSIONS = (
    "age_band",
    "individual_yearly_income_band",
    "family_member_count_band",
    "gender",
    "state",
    "marital_status",
    "education",
    "employment_status",
    "resident_status",
    "resident_type",
    "type_of_employment",
)

_PROFILE_BAND_ORDERS: dict[str, tuple[str, ...]] = {
    "age_band": ("18-24", "25-34", "35-44", "45-54", "55-64", "65+", "Unknown/Other"),
    "individual_yearly_income_band": (
        "<50K",
        "50K-74,999",
        "75K-99,999",
        "100K-149,999",
        "150K-199,999",
        "200K+",
        "Unknown/Other",
    ),
    "family_member_count_band": ("1", "2", "3", "4", "5+", "Unknown/Other"),
}


class AudiencePreparationServiceError(RuntimeError):
    """Base class for audience preparation service failures."""


class AudiencePreparationValidationError(AudiencePreparationServiceError):
    """Raised when audience preparation request arguments are invalid."""


class AudiencePreparationConflictError(AudiencePreparationServiceError):
    """Raised when audience preparation conflicts with current persisted state."""


class AudiencePreparationSubmissionError(AudiencePreparationServiceError):
    """Raised when queue persistence succeeds but worker submission fails."""


@dataclass(frozen=True)
class RankBoundary:
    percentile_bucket: int
    boundary_rank: int
    boundary_score: float
    boundary_person_id: str
    total_population: int

    def to_row(self) -> dict[str, Any]:
        return {
            "percentile_bucket": self.percentile_bucket,
            "boundary_rank": self.boundary_rank,
            "boundary_score": self.boundary_score,
            "boundary_person_id": self.boundary_person_id,
            "total_population": self.total_population,
        }


@dataclass(frozen=True)
class PreparationMetrics:
    scanned_rows: int
    chunk_size: int
    chunk_count: int
    largest_chunk_rows: int
    runtime_seconds: float
    rows_per_second: float

    def to_payload(self) -> dict[str, Any]:
        return {
            "scanned_rows": int(self.scanned_rows),
            "chunk_size": int(self.chunk_size),
            "chunk_count": int(self.chunk_count),
            "largest_chunk_rows": int(self.largest_chunk_rows),
            "runtime_seconds": round(float(self.runtime_seconds), 6),
            "rows_per_second": round(float(self.rows_per_second), 6),
        }


@dataclass
class ScoreBucketAccumulator:
    bucket: int
    count: int = 0
    score_sum: float = 0.0
    score_min: float | None = None
    score_max: float | None = None

    def add(self, score: float) -> None:
        self.count += 1
        self.score_sum += float(score)
        if self.score_min is None or score < self.score_min:
            self.score_min = score
        if self.score_max is None or score > self.score_max:
            self.score_max = score

    def to_payload(self) -> dict[str, Any]:
        if self.count == 0:
            return {
                "bucket": int(self.bucket),
                "count": 0,
                "score_min": None,
                "score_max": None,
                "score_sum": 0.0,
                "score_mean": None,
            }
        if self.score_min is None or self.score_max is None:
            raise AudiencePreparationValidationError("Score bucket accumulation is incomplete.")
        return {
            "bucket": int(self.bucket),
            "count": int(self.count),
            "score_min": float(self.score_min),
            "score_max": float(self.score_max),
            "score_sum": round(float(self.score_sum), 12),
            "score_mean": float(self.score_sum / self.count),
        }


WorkerSubmitter = Callable[[str | Path, int], Any]


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _bounded_internal_error(exc: Exception) -> str:
    diagnostic = traceback.format_exc()[-MAXIMUM_INTERNAL_ERROR_LENGTH:]
    if diagnostic.strip():
        return diagnostic
    return f"{type(exc).__name__}: {exc}"[:MAXIMUM_INTERNAL_ERROR_LENGTH]


def _public_job_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": int(row["job_id"]),
        "job_type": str(row["job_type"]),
        "status": str(row["status"]),
        "progress_percent": int(row["progress_percent"]),
        "stage": str(row["stage"]),
        "message": row.get("message"),
        "analysis_run_id": row.get("analysis_run_id"),
        "model_run_id": row.get("model_run_id"),
        "created_at": row["created_at"],
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
    }


def _compact_currentness_issue(issue: Any) -> str | None:
    if not isinstance(issue, str):
        return None
    normalized = issue.strip()
    if not normalized:
        return None
    if len(normalized) <= MAXIMUM_CURRENTNESS_ISSUE_LENGTH:
        return normalized
    return normalized[: MAXIMUM_CURRENTNESS_ISSUE_LENGTH - 3].rstrip() + "..."


def _bounded_currentness_issues(issues: list[Any]) -> list[str]:
    bounded: list[str] = []
    seen: set[str] = set()
    for issue in issues:
        compact = _compact_currentness_issue(issue)
        if compact is None or compact in seen:
            continue
        seen.add(compact)
        bounded.append(compact)
        if len(bounded) >= MAXIMUM_CURRENTNESS_ISSUES:
            break
    return bounded


def _resolve_run_currentness(
    database_path: str | Path,
    *,
    scoring_run_id: int,
    model_run_id: int,
) -> dict[str, Any]:
    issues: list[Any] = []
    source_verified = False
    is_canonical = False

    try:
        provenance = resolve_current_scoring_context_lightweight(
            database_path,
            scoring_run_id=scoring_run_id,
            verify_current_source_match=True,
        )
    except Exception:
        provenance = None
        issues.append("Scoring provenance could not be validated.")

    if provenance is not None:
        is_canonical = bool(provenance.get("is_canonical"))
        historical_verified = bool(provenance.get("historical_source_verified"))
        demographic_verified = bool(provenance.get("demographic_source_verified"))
        source_verified = historical_verified and demographic_verified
        if not historical_verified:
            issues.append("Historical source provenance is stale for this scoring run.")
        if not demographic_verified:
            issues.append("Demographic source provenance is stale for this scoring run.")
        if not is_canonical:
            issues.extend(list(provenance.get("issues") or []))

    # Keep model linkage checks explicit in status/list surfaces.
    if provenance is not None and int(provenance.get("scoring_run_id") or 0) == scoring_run_id:
        if int(model_run_id) <= 0:
            is_canonical = False
            issues.append("Scoring run model linkage is invalid.")

    return {
        "is_canonical": is_canonical,
        "source_verified": source_verified,
        "currentness_issues": _bounded_currentness_issues(issues),
    }


def _require_positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AudiencePreparationValidationError(f"{field_name} must be a positive integer.")
    return value


def _require_non_empty_text(value: Any, *, field_name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise AudiencePreparationValidationError(f"{field_name} must be text.")
    normalized = value.strip()
    if not normalized:
        raise AudiencePreparationValidationError(f"{field_name} must not be blank.")
    if len(normalized) > maximum:
        raise AudiencePreparationValidationError(
            f"{field_name} must not exceed {maximum} characters."
        )
    return normalized


def _normalize_rank_contract_version(value: Any) -> str:
    if value is None:
        return DEFAULT_RANK_CONTRACT_VERSION
    if not isinstance(value, str):
        raise AudiencePreparationValidationError("rank_contract_version must be text.")
    normalized = value.strip()
    if not normalized:
        raise AudiencePreparationValidationError("rank_contract_version must not be blank.")
    if len(normalized) > 24:
        raise AudiencePreparationValidationError(
            "rank_contract_version must not exceed 24 characters."
        )
    if normalized not in SUPPORTED_RANK_CONTRACT_VERSIONS:
        raise AudiencePreparationValidationError(
            "rank_contract_version is not supported."
        )
    return normalized


def _normalize_scan_chunk_size(chunk_size: int) -> int:
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int):
        raise AudiencePreparationValidationError("scan_chunk_size must be an integer.")
    if not MINIMUM_SCORE_SCAN_CHUNK_SIZE <= chunk_size <= MAXIMUM_SCORE_SCAN_CHUNK_SIZE:
        raise AudiencePreparationValidationError(
            "scan_chunk_size must be between "
            f"{MINIMUM_SCORE_SCAN_CHUNK_SIZE} and {MAXIMUM_SCORE_SCAN_CHUNK_SIZE}."
        )
    return chunk_size


def _decode_json_object(raw: Any, *, field_name: str) -> dict[str, Any]:
    if not isinstance(raw, str) or not raw.strip():
        raise AudiencePreparationValidationError(f"{field_name} is missing.")
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise AudiencePreparationValidationError(f"{field_name} is invalid.") from exc
    if not isinstance(decoded, dict):
        raise AudiencePreparationValidationError(f"{field_name} is invalid.")
    return decoded


def _is_valid_hash64(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    if len(normalized) != 64:
        return False
    return all(char in "0123456789abcdef" for char in normalized)


def _dimension_sort_key(dimension: str, category: str) -> tuple[Any, ...]:
    if dimension in _PROFILE_BAND_ORDERS:
        order = _PROFILE_BAND_ORDERS[dimension]
        positions = {label: index for index, label in enumerate(order)}
        return (positions.get(category, len(order)), category.casefold(), category)
    return (category.casefold(), category)


def _safe_share(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 6)


def _normalize_category_expression(column_name: str) -> str:
    if column_name not in _AUDIENCE_CATEGORICAL_FIELDS:
        raise AudiencePreparationValidationError("Unsupported categorical column.")
    return f"COALESCE(NULLIF(TRIM(CAST({column_name} AS TEXT)), ''), 'Unknown/Other')"


def _static_profile_summary_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "count": int(row["member_count"]),
        "age_mean": float(row["age_mean"]) if row["age_mean"] is not None else None,
        "individual_yearly_income_mean": (
            float(row["individual_yearly_income_mean"])
            if row["individual_yearly_income_mean"] is not None
            else None
        ),
        "family_member_count_mean": (
            float(row["family_member_count_mean"])
            if row["family_member_count_mean"] is not None
            else None
        ),
        "score_min": None,
        "score_mean": None,
        "score_max": None,
    }


def _build_static_options_and_universe_profile(
    path: Path,
    *,
    population_count: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    with get_connection(path) as connection:
        numeric_row = dict(
            connection.execute(
                """
                SELECT
                    MIN(age) AS age_min,
                    MAX(age) AS age_max,
                    MIN(individual_yearly_income) AS individual_yearly_income_min,
                    MAX(individual_yearly_income) AS individual_yearly_income_max,
                    MIN(family_member_count) AS family_member_count_min,
                    MAX(family_member_count) AS family_member_count_max
                FROM demographics
                """
            ).fetchone()
        )

        options: dict[str, list[dict[str, Any]]] = {}
        for field in _AUDIENCE_CATEGORICAL_FIELDS:
            normalized_expression = _normalize_category_expression(field)
            rows = [
                dict(row)
                for row in connection.execute(
                    f"""
                    SELECT
                        {normalized_expression} AS option_value,
                        COUNT(*) AS option_count
                    FROM demographics
                    GROUP BY {normalized_expression}
                    ORDER BY option_value COLLATE NOCASE, option_value
                    """
                ).fetchall()
            ]
            options[field] = [
                {
                    "value": str(row["option_value"]),
                    "count": int(row["option_count"]),
                }
                for row in rows
            ]

        summary_row = dict(
            connection.execute(
                """
                SELECT
                    COUNT(*) AS member_count,
                    AVG(age) AS age_mean,
                    AVG(individual_yearly_income) AS individual_yearly_income_mean,
                    AVG(family_member_count) AS family_member_count_mean
                FROM demographics
                """
            ).fetchone()
        )

        distribution_rows = [
            dict(row)
            for row in connection.execute(
                """
                WITH normalized_members AS (
                    SELECT
                        CASE
                            WHEN age BETWEEN 18 AND 24 THEN '18-24'
                            WHEN age BETWEEN 25 AND 34 THEN '25-34'
                            WHEN age BETWEEN 35 AND 44 THEN '35-44'
                            WHEN age BETWEEN 45 AND 54 THEN '45-54'
                            WHEN age BETWEEN 55 AND 64 THEN '55-64'
                            WHEN age >= 65 THEN '65+'
                            ELSE 'Unknown/Other'
                        END AS age_band,
                        CASE
                            WHEN individual_yearly_income < 50000 THEN '<50K'
                            WHEN individual_yearly_income < 75000 THEN '50K-74,999'
                            WHEN individual_yearly_income < 100000 THEN '75K-99,999'
                            WHEN individual_yearly_income < 150000 THEN '100K-149,999'
                            WHEN individual_yearly_income < 200000 THEN '150K-199,999'
                            WHEN individual_yearly_income >= 200000 THEN '200K+'
                            ELSE 'Unknown/Other'
                        END AS individual_yearly_income_band,
                        CASE
                            WHEN family_member_count = 1 THEN '1'
                            WHEN family_member_count = 2 THEN '2'
                            WHEN family_member_count = 3 THEN '3'
                            WHEN family_member_count = 4 THEN '4'
                            WHEN family_member_count >= 5 THEN '5+'
                            ELSE 'Unknown/Other'
                        END AS family_member_count_band,
                        COALESCE(NULLIF(TRIM(CAST(gender AS TEXT)), ''), 'Unknown/Other') AS gender,
                        COALESCE(NULLIF(TRIM(CAST(state AS TEXT)), ''), 'Unknown/Other') AS state,
                        COALESCE(NULLIF(TRIM(CAST(marital_status AS TEXT)), ''), 'Unknown/Other') AS marital_status,
                        COALESCE(NULLIF(TRIM(CAST(education AS TEXT)), ''), 'Unknown/Other') AS education,
                        COALESCE(NULLIF(TRIM(CAST(employment_status AS TEXT)), ''), 'Unknown/Other') AS employment_status,
                        COALESCE(NULLIF(TRIM(CAST(resident_status AS TEXT)), ''), 'Unknown/Other') AS resident_status,
                        COALESCE(NULLIF(TRIM(CAST(resident_type AS TEXT)), ''), 'Unknown/Other') AS resident_type,
                        COALESCE(NULLIF(TRIM(CAST(type_of_employment AS TEXT)), ''), 'Unknown/Other') AS type_of_employment
                    FROM demographics
                ),
                profile_values AS (
                    SELECT 'age_band' AS dimension, age_band AS category FROM normalized_members
                    UNION ALL
                    SELECT 'individual_yearly_income_band', individual_yearly_income_band FROM normalized_members
                    UNION ALL
                    SELECT 'family_member_count_band', family_member_count_band FROM normalized_members
                    UNION ALL
                    SELECT 'gender', gender FROM normalized_members
                    UNION ALL
                    SELECT 'state', state FROM normalized_members
                    UNION ALL
                    SELECT 'marital_status', marital_status FROM normalized_members
                    UNION ALL
                    SELECT 'education', education FROM normalized_members
                    UNION ALL
                    SELECT 'employment_status', employment_status FROM normalized_members
                    UNION ALL
                    SELECT 'resident_status', resident_status FROM normalized_members
                    UNION ALL
                    SELECT 'resident_type', resident_type FROM normalized_members
                    UNION ALL
                    SELECT 'type_of_employment', type_of_employment FROM normalized_members
                )
                SELECT
                    dimension,
                    category,
                    COUNT(*) AS category_count
                FROM profile_values
                GROUP BY dimension, category
                ORDER BY dimension, category_count DESC, category COLLATE NOCASE, category
                """
            ).fetchall()
        ]

    universe_summary = _static_profile_summary_from_row(summary_row)
    if universe_summary["count"] != population_count:
        raise AudiencePreparationValidationError(
            "Universe profile count does not match scoring population count."
        )

    universe_distributions: dict[str, list[dict[str, Any]]] = {
        dimension: [] for dimension in _PROFILE_DIMENSIONS
    }
    for row in distribution_rows:
        dimension = str(row["dimension"])
        if dimension not in universe_distributions:
            continue
        count = int(row["category_count"])
        universe_distributions[dimension].append(
            {
                "category": str(row["category"]),
                "count": count,
                "share": _safe_share(count, population_count),
            }
        )

    for dimension, values in universe_distributions.items():
        values.sort(
            key=lambda item: _dimension_sort_key(dimension, str(item["category"]))
        )

    options_payload = {
        "population_count": int(population_count),
        "numeric_ranges": {
            "age": {
                "min": int(numeric_row["age_min"]) if numeric_row["age_min"] is not None else None,
                "max": int(numeric_row["age_max"]) if numeric_row["age_max"] is not None else None,
            },
            "individual_yearly_income": {
                "min": (
                    float(numeric_row["individual_yearly_income_min"])
                    if numeric_row["individual_yearly_income_min"] is not None
                    else None
                ),
                "max": (
                    float(numeric_row["individual_yearly_income_max"])
                    if numeric_row["individual_yearly_income_max"] is not None
                    else None
                ),
            },
            "family_member_count": {
                "min": (
                    int(numeric_row["family_member_count_min"])
                    if numeric_row["family_member_count_min"] is not None
                    else None
                ),
                "max": (
                    int(numeric_row["family_member_count_max"])
                    if numeric_row["family_member_count_max"] is not None
                    else None
                ),
            },
        },
        "categorical_options": options,
    }
    universe_profile_payload = {
        "summary": universe_summary,
        "distributions": universe_distributions,
    }
    return options_payload, universe_profile_payload


def _resolve_historical_context_for_snapshot(
    path: Path,
    *,
    scoring_row: dict[str, Any],
) -> tuple[dict[str, Any], str, int, bool]:
    score_summary = _decode_json_object(
        scoring_row.get("score_summary_json"),
        field_name="scoring_run.score_summary_json",
    )
    analysis_run_id = score_summary.get("analysis_run_id")
    if isinstance(analysis_run_id, bool) or not isinstance(analysis_run_id, int) or analysis_run_id <= 0:
        raise AudiencePreparationValidationError("Scoring analysis_run_id is invalid.")

    model_run = ModelRunRepository(path).fetch_run(int(scoring_row["model_run_id"]))
    if model_run is None or int(model_run["analysis_run_id"]) != analysis_run_id:
        raise AudiencePreparationConflictError(SCORING_RUN_NOT_CANONICAL_MESSAGE)

    analysis_row = HistoricalRepository(path).fetch_analysis_run(analysis_run_id)
    if analysis_row is None or str(analysis_row.get("status")) != "COMPLETED":
        raise AudiencePreparationValidationError("Saved historical analysis is unavailable.")

    raw_filters = analysis_row.get("filters_json")
    decoded_filters = _decode_json_object(raw_filters, field_name="analysis.filters_json")
    payload = HistoricalAnalysisFilters.model_validate(
        {
            "analysis_name": str(analysis_row["analysis_name"]),
            **decoded_filters,
            "conversion_definition": str(analysis_row["conversion_definition"]),
        }
    ).filter_payload()
    reference_date = payload.get("contact_date_to")
    if not isinstance(reference_date, str) or not reference_date.strip():
        fallback_timestamp = analysis_row.get("completed_at") or analysis_row.get("created_at")
        if isinstance(fallback_timestamp, str) and len(fallback_timestamp) >= 10:
            reference_date = fallback_timestamp[:10]
        else:
            raise AudiencePreparationValidationError("Saved historical analysis date context is invalid.")
    enforce_reconciliation = True
    customer_import_id = analysis_row.get("customer_import_id")
    campaign_import_id = analysis_row.get("campaign_sales_import_id")
    if (
        isinstance(customer_import_id, int)
        and customer_import_id > 0
        and isinstance(campaign_import_id, int)
        and campaign_import_id > 0
    ):
        with get_connection(path) as connection:
            customer_import_row = connection.execute(
                "SELECT rows_inserted FROM data_import_runs WHERE import_id = ?",
                (customer_import_id,),
            ).fetchone()
            campaign_import_row = connection.execute(
                "SELECT rows_inserted FROM data_import_runs WHERE import_id = ?",
                (campaign_import_id,),
            ).fetchone()
        if (
            customer_import_row is not None
            and campaign_import_row is not None
            and int(customer_import_row["rows_inserted"] or 0) == 0
            and int(campaign_import_row["rows_inserted"] or 0) == 0
        ):
            enforce_reconciliation = False

    return (
        payload,
        reference_date,
        int(analysis_row["positive_customer_count"]),
        enforce_reconciliation,
    )


def _build_historical_positive_profile_snapshot(
    path: Path,
    *,
    filters_payload: dict[str, Any],
    reference_date: str,
) -> dict[str, Any]:
    cte, parameters = build_matching_observations_cte(filters_payload)
    normalized_cte = cte.strip()
    if normalized_cte[:4].upper() == "WITH":
        normalized_cte = normalized_cte[4:].lstrip()

    shared_ctes = f"""
        {normalized_cte},
        analysis_reference AS (
            SELECT DATE(?) AS reference_date
        ),
        positive_members AS MATERIALIZED (
            SELECT
                CASE
                    WHEN DATE(c.date_of_birth) IS NULL THEN NULL
                    ELSE
                        CAST(STRFTIME('%Y', reference.reference_date) AS INTEGER)
                        - CAST(SUBSTR(c.date_of_birth, 1, 4) AS INTEGER)
                        - CASE
                            WHEN STRFTIME('%m-%d', reference.reference_date)
                                 < SUBSTR(c.date_of_birth, 6, 5) THEN 1
                            ELSE 0
                          END
                END AS age,
                c.individual_yearly_income,
                c.family_member_count,
                c.gender,
                c.state,
                c.marital_status,
                c.education,
                c.employment_status,
                c.resident_status,
                c.resident_type,
                c.type_of_employment
            FROM customer_labels AS labels
            INNER JOIN customers AS c ON c.customer_id = labels.customer_id
            CROSS JOIN analysis_reference AS reference
            WHERE labels.is_positive = 1
        )
    """

    summary_query = f"""
        WITH
        {shared_ctes}
        SELECT
            COUNT(*) AS member_count,
            AVG(age) AS age_mean,
            AVG(individual_yearly_income) AS individual_yearly_income_mean,
            AVG(family_member_count) AS family_member_count_mean
        FROM positive_members
    """

    distribution_query = f"""
        WITH
        {shared_ctes},
        normalized_members AS (
            SELECT
                CASE
                    WHEN age BETWEEN 18 AND 24 THEN '18-24'
                    WHEN age BETWEEN 25 AND 34 THEN '25-34'
                    WHEN age BETWEEN 35 AND 44 THEN '35-44'
                    WHEN age BETWEEN 45 AND 54 THEN '45-54'
                    WHEN age BETWEEN 55 AND 64 THEN '55-64'
                    WHEN age >= 65 THEN '65+'
                    ELSE 'Unknown/Other'
                END AS age_band,
                CASE
                    WHEN individual_yearly_income < 50000 THEN '<50K'
                    WHEN individual_yearly_income < 75000 THEN '50K-74,999'
                    WHEN individual_yearly_income < 100000 THEN '75K-99,999'
                    WHEN individual_yearly_income < 150000 THEN '100K-149,999'
                    WHEN individual_yearly_income < 200000 THEN '150K-199,999'
                    WHEN individual_yearly_income >= 200000 THEN '200K+'
                    ELSE 'Unknown/Other'
                END AS individual_yearly_income_band,
                CASE
                    WHEN family_member_count = 1 THEN '1'
                    WHEN family_member_count = 2 THEN '2'
                    WHEN family_member_count = 3 THEN '3'
                    WHEN family_member_count = 4 THEN '4'
                    WHEN family_member_count >= 5 THEN '5+'
                    ELSE 'Unknown/Other'
                END AS family_member_count_band,
                COALESCE(NULLIF(TRIM(CAST(gender AS TEXT)), ''), 'Unknown/Other') AS gender,
                COALESCE(NULLIF(TRIM(CAST(state AS TEXT)), ''), 'Unknown/Other') AS state,
                COALESCE(NULLIF(TRIM(CAST(marital_status AS TEXT)), ''), 'Unknown/Other') AS marital_status,
                COALESCE(NULLIF(TRIM(CAST(education AS TEXT)), ''), 'Unknown/Other') AS education,
                COALESCE(NULLIF(TRIM(CAST(employment_status AS TEXT)), ''), 'Unknown/Other') AS employment_status,
                COALESCE(NULLIF(TRIM(CAST(resident_status AS TEXT)), ''), 'Unknown/Other') AS resident_status,
                COALESCE(NULLIF(TRIM(CAST(resident_type AS TEXT)), ''), 'Unknown/Other') AS resident_type,
                COALESCE(NULLIF(TRIM(CAST(type_of_employment AS TEXT)), ''), 'Unknown/Other') AS type_of_employment
            FROM positive_members
        ),
        profile_values AS (
            SELECT 'age_band' AS dimension, age_band AS category FROM normalized_members
            UNION ALL
            SELECT 'individual_yearly_income_band', individual_yearly_income_band FROM normalized_members
            UNION ALL
            SELECT 'family_member_count_band', family_member_count_band FROM normalized_members
            UNION ALL
            SELECT 'gender', gender FROM normalized_members
            UNION ALL
            SELECT 'state', state FROM normalized_members
            UNION ALL
            SELECT 'marital_status', marital_status FROM normalized_members
            UNION ALL
            SELECT 'education', education FROM normalized_members
            UNION ALL
            SELECT 'employment_status', employment_status FROM normalized_members
            UNION ALL
            SELECT 'resident_status', resident_status FROM normalized_members
            UNION ALL
            SELECT 'resident_type', resident_type FROM normalized_members
            UNION ALL
            SELECT 'type_of_employment', type_of_employment FROM normalized_members
        )
        SELECT
            dimension,
            category,
            COUNT(*) AS category_count
        FROM profile_values
        GROUP BY dimension, category
        ORDER BY dimension, category_count DESC, category COLLATE NOCASE, category
    """

    query_parameters = [*parameters, reference_date]
    with get_connection(path) as connection:
        summary_row = dict(connection.execute(summary_query, query_parameters).fetchone())
        distribution_rows = [
            dict(row)
            for row in connection.execute(distribution_query, query_parameters).fetchall()
        ]

    total_count = int(summary_row["member_count"])
    distributions: dict[str, list[dict[str, Any]]] = {
        dimension: [] for dimension in _PROFILE_DIMENSIONS
    }
    for row in distribution_rows:
        dimension = str(row["dimension"])
        if dimension not in distributions:
            continue
        count = int(row["category_count"])
        distributions[dimension].append(
            {
                "category": str(row["category"]),
                "count": count,
                "share": _safe_share(count, total_count),
            }
        )

    for dimension, values in distributions.items():
        values.sort(
            key=lambda item: _dimension_sort_key(dimension, str(item["category"]))
        )

    return {
        "reference_date": reference_date,
        "summary": {
            "count": total_count,
            "age_mean": float(summary_row["age_mean"]) if summary_row["age_mean"] is not None else None,
            "individual_yearly_income_mean": (
                float(summary_row["individual_yearly_income_mean"])
                if summary_row["individual_yearly_income_mean"] is not None
                else None
            ),
            "family_member_count_mean": (
                float(summary_row["family_member_count_mean"])
                if summary_row["family_member_count_mean"] is not None
                else None
            ),
            "score_min": None,
            "score_mean": None,
            "score_max": None,
        },
        "distributions": distributions,
    }


def _model_governance_issues(
    *,
    model_row: dict[str, Any] | None,
    scoring_row: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    if model_row is None:
        return ["model_run_id does not exist"]
    if str(model_row.get("status")) != "COMPLETED":
        issues.append("model run is not COMPLETED")
    if model_row.get("selected_candidate") != PRIMARY_MODEL_NAME:
        issues.append("model selected_candidate is not the governed BAGGING_PU primary")
    model_artifact_sha = str(model_row.get("artifact_sha256") or "").strip().lower()
    if not _is_valid_hash64(model_artifact_sha):
        issues.append("model artifact_sha256 is invalid")
    elif model_artifact_sha != str(scoring_row.get("artifact_sha256") or "").strip().lower():
        issues.append("artifact_sha256 does not match model metadata")

    try:
        metrics = _decode_json_object(
            model_row.get("metrics_json"),
            field_name="model_run.metrics_json",
        )
    except AudiencePreparationValidationError:
        issues.append("model metrics_json is invalid")
        return issues
    governed_keys = {
        "model_role_policy_version",
        "evaluation_contract_version",
        "selection_policy",
        "primary_candidate",
        "selected_candidate",
        "challenger_candidates",
        "diagnostic_controls",
    }
    has_governance_payload = any(key in metrics for key in governed_keys)
    if has_governance_payload:
        if metrics.get("model_role_policy_version") != MODEL_ROLE_POLICY_VERSION:
            issues.append("model metrics model_role_policy_version is incompatible")
        if metrics.get("evaluation_contract_version") != EVALUATION_CONTRACT_VERSION:
            issues.append("model metrics evaluation_contract_version is incompatible")
        if metrics.get("selection_policy") != PRIMARY_ROLE_GOVERNED_SELECTION:
            issues.append("model metrics selection_policy is incompatible")
        if metrics.get("primary_candidate") != PRIMARY_MODEL_NAME:
            issues.append("model metrics primary_candidate is incompatible")
        if metrics.get("selected_candidate") != PRIMARY_MODEL_NAME:
            issues.append("model metrics selected_candidate is incompatible")
        if metrics.get("challenger_candidates") != [CHALLENGER_1_MODEL_NAME]:
            issues.append("model metrics challenger_candidates is incompatible")
        if metrics.get("diagnostic_controls") != [DIAGNOSTIC_CONTROL_NAME]:
            issues.append("model metrics diagnostic_controls is incompatible")
    return issues


def validate_audience_analytics_snapshot_currentness(
    database_path: str | Path,
    *,
    scoring_run_id: int,
    analytics_contract_version: str = AUDIENCE_ANALYTICS_CONTRACT_VERSION,
    cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = initialize_database(database_path)
    normalized_scoring_run_id = _require_positive_int(scoring_run_id, field_name="scoring_run_id")
    normalized_contract_version = _require_non_empty_text(
        analytics_contract_version,
        field_name="analytics_contract_version",
        maximum=24,
    )
    if normalized_contract_version not in SUPPORTED_AUDIENCE_ANALYTICS_CONTRACT_VERSIONS:
        raise AudiencePreparationValidationError("analytics_contract_version is not supported.")

    scoring_row = ScoringRepository(path).fetch_scoring_run(normalized_scoring_run_id)
    if scoring_row is None:
        raise AudiencePreparationValidationError(SCORING_RUN_NOT_FOUND_MESSAGE)

    shared_cache = {} if cache is None else cache
    currentness = _resolve_run_currentness(
        path,
        scoring_run_id=normalized_scoring_run_id,
        model_run_id=int(scoring_row["model_run_id"]),
    )
    issues: list[str] = list(currentness["currentness_issues"])

    if str(scoring_row.get("model_role_policy_version")) != MODEL_ROLE_POLICY_VERSION:
        issues.append("scoring model_role_policy_version is incompatible")
    if scoring_row.get("selected_candidate") != PRIMARY_MODEL_NAME:
        issues.append("scoring selected_candidate is not BAGGING_PU")
    if str(scoring_row.get("feature_contract_version") or "").strip() == "":
        issues.append("scoring feature_contract_version is missing")
    if not _is_valid_hash64(scoring_row.get("feature_contract_sha256")):
        issues.append("scoring feature_contract_sha256 is invalid")
    if not _is_valid_hash64(scoring_row.get("artifact_sha256")):
        issues.append("scoring artifact_sha256 is invalid")

    model_cache = shared_cache.setdefault("model_rows", {})
    model_run_id = int(scoring_row["model_run_id"])
    if model_run_id not in model_cache:
        model_cache[model_run_id] = ModelRunRepository(path).fetch_run(model_run_id)
    model_row = model_cache.get(model_run_id)
    issues.extend(_model_governance_issues(model_row=model_row, scoring_row=scoring_row))

    summary_payload = _decode_json_object(
        scoring_row.get("score_summary_json"),
        field_name="scoring_run.score_summary_json",
    )

    snapshot = AudienceAnalyticsSnapshotRepository(path).fetch_snapshot(
        normalized_scoring_run_id,
        analytics_contract_version=normalized_contract_version,
    )
    snapshot_created_at: str | None = None
    if snapshot is None:
        issues.append("analytics snapshot is missing")
    else:
        snapshot_created_at = snapshot.get("created_at")
        checks: tuple[tuple[str, Any], ...] = (
            ("scoring_run_id", normalized_scoring_run_id),
            ("analytics_contract_version", normalized_contract_version),
            ("model_run_id", int(scoring_row["model_run_id"])),
            ("analysis_run_id", summary_payload.get("analysis_run_id")),
            ("customer_import_id", summary_payload.get("customer_import_id")),
            ("customer_source_checksum", summary_payload.get("customer_source_checksum")),
            ("campaign_sales_import_id", summary_payload.get("campaign_sales_import_id")),
            (
                "campaign_sales_source_checksum",
                summary_payload.get("campaign_sales_source_checksum"),
            ),
            ("demographic_import_id", summary_payload.get("demographic_import_id")),
            ("demographic_source_checksum", summary_payload.get("demographic_source_checksum")),
            ("feature_contract_version", scoring_row.get("feature_contract_version")),
            ("feature_contract_sha256", scoring_row.get("feature_contract_sha256")),
            ("artifact_sha256", scoring_row.get("artifact_sha256")),
            ("filter_contract_version", AUDIENCE_FILTER_CONTRACT_VERSION),
            ("rank_contract_version", DEFAULT_RANK_CONTRACT_VERSION),
            ("selection_contract_version", AUDIENCE_SELECTION_CONTRACT_VERSION),
            ("population_count", int(scoring_row["scored_person_count"])),
        )
        for key, expected in checks:
            if snapshot.get(key) != expected:
                issues.append(f"analytics snapshot {key} does not match canonical provenance")

    deduped_issues = _bounded_currentness_issues(list(dict.fromkeys(issues)))
    return {
        "scoring_run_id": normalized_scoring_run_id,
        "analytics_contract_version": normalized_contract_version,
        "analytics_prepared": snapshot is not None and len(deduped_issues) == 0,
        "is_canonical": bool(currentness["is_canonical"]),
        "source_verified": bool(currentness["source_verified"]),
        "snapshot_created_at": snapshot_created_at,
        "snapshot": snapshot,
        "issues": deduped_issues,
    }


def _target_rank(total_population: int, bucket: int) -> int:
    base = math.ceil((total_population * bucket) / 100)
    return max(1, base)


def classify_percentile_bucket(
    score: float,
    person_id: str,
    boundaries: list[dict[str, Any]],
) -> int:
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise AudiencePreparationValidationError("score must be numeric.")
    normalized_score = float(score)
    if not math.isfinite(normalized_score) or not 0 <= normalized_score <= 1:
        raise AudiencePreparationValidationError("score must be finite and between 0 and 1.")
    if not isinstance(person_id, str) or not person_id.strip():
        raise AudiencePreparationValidationError("person_id must be a non-empty string.")
    normalized_person_id = person_id.strip()

    if len(boundaries) != 100:
        raise AudiencePreparationValidationError("boundaries must contain exactly 100 rows.")

    for row in boundaries:
        bucket = row.get("percentile_bucket")
        boundary_score = row.get("boundary_score")
        boundary_person_id = row.get("boundary_person_id")
        if isinstance(bucket, bool) or not isinstance(bucket, int) or not 1 <= bucket <= 100:
            raise AudiencePreparationValidationError("boundary percentile_bucket is invalid.")
        if isinstance(boundary_score, bool) or not isinstance(boundary_score, (int, float)):
            raise AudiencePreparationValidationError("boundary_score is invalid.")
        boundary_score = float(boundary_score)
        if not math.isfinite(boundary_score):
            raise AudiencePreparationValidationError("boundary_score must be finite.")
        if not isinstance(boundary_person_id, str) or not boundary_person_id.strip():
            raise AudiencePreparationValidationError("boundary_person_id is invalid.")

        # Sorted by score desc then person_id asc: first boundary at or below row is the row bucket.
        if normalized_score > boundary_score:
            return int(bucket)
        if normalized_score == boundary_score and normalized_person_id <= boundary_person_id:
            return int(bucket)

    return 100


def classify_decile(bucket: int) -> int:
    if isinstance(bucket, bool) or not isinstance(bucket, int) or not 1 <= bucket <= 100:
        raise AudiencePreparationValidationError("bucket must be an integer between 1 and 100.")
    return ((bucket - 1) // 10) + 1


def classify_rank_band(bucket: int) -> str:
    if isinstance(bucket, bool) or not isinstance(bucket, int) or not 1 <= bucket <= 100:
        raise AudiencePreparationValidationError("bucket must be an integer between 1 and 100.")
    if bucket == 1:
        return "ELITE"
    if bucket <= 5:
        return "VERY_HIGH"
    if bucket <= 10:
        return "HIGH"
    if bucket <= 25:
        return "MEDIUM"
    if bucket <= 50:
        return "LOW"
    return "VERY_LOW"


def _compute_boundaries_for_run(
    database_path: str | Path,
    *,
    scoring_run_id: int,
    chunk_size: int,
) -> tuple[list[RankBoundary], PreparationMetrics, dict[str, Any]]:
    repository = ScoringRepository(database_path)
    scoring_run = repository.fetch_scoring_run(scoring_run_id)
    if scoring_run is None:
        raise AudiencePreparationValidationError(SCORING_RUN_NOT_FOUND_MESSAGE)

    total_population = int(scoring_run["scored_person_count"])
    if total_population <= 0:
        raise AudiencePreparationValidationError(SCORING_COUNT_MISMATCH_MESSAGE)

    targets = [_target_rank(total_population, bucket) for bucket in range(1, 101)]

    boundaries: list[RankBoundary] = []
    bucket_accumulators = [ScoreBucketAccumulator(bucket=index) for index in range(1, 101)]
    current_bucket_index = 0
    stats_bucket_index = 0
    current_rank = 0
    cursor_score: float | None = None
    cursor_person_id: str | None = None
    scanned_rows = 0
    chunk_count = 0
    largest_chunk_rows = 0
    started = perf_counter()

    while current_bucket_index < 100:
        rows = repository.fetch_rank_scan_chunk(
            scoring_run_id=scoring_run_id,
            limit=chunk_size,
            after_score=cursor_score,
            after_person_id=cursor_person_id,
        )
        if not rows:
            break
        chunk_count += 1
        scanned_rows += len(rows)
        if len(rows) > largest_chunk_rows:
            largest_chunk_rows = len(rows)

        for row in rows:
            current_rank += 1
            row_score = float(row["propensity_score"])
            row_person_id = str(row["person_id"])

            while stats_bucket_index < 99 and current_rank > targets[stats_bucket_index]:
                stats_bucket_index += 1
            bucket_accumulators[stats_bucket_index].add(row_score)

            while current_bucket_index < 100 and current_rank >= targets[current_bucket_index]:
                boundaries.append(
                    RankBoundary(
                        percentile_bucket=current_bucket_index + 1,
                        boundary_rank=current_rank,
                        boundary_score=row_score,
                        boundary_person_id=row_person_id,
                        total_population=total_population,
                    )
                )
                current_bucket_index += 1

            cursor_score = row_score
            cursor_person_id = row_person_id

    if current_bucket_index != 100:
        raise AudiencePreparationValidationError(SCORING_COUNT_MISMATCH_MESSAGE)
    if boundaries[-1].boundary_rank != total_population:
        raise AudiencePreparationValidationError(
            "The 100th percentile boundary rank must equal scored population."
        )

    runtime_seconds = max(0.0, perf_counter() - started)
    rows_per_second = (scanned_rows / runtime_seconds) if runtime_seconds > 0 else 0.0
    metrics = PreparationMetrics(
        scanned_rows=scanned_rows,
        chunk_size=chunk_size,
        chunk_count=chunk_count,
        largest_chunk_rows=largest_chunk_rows,
        runtime_seconds=runtime_seconds,
        rows_per_second=rows_per_second,
    )
    bucket_payload = {
        "buckets": [accumulator.to_payload() for accumulator in bucket_accumulators],
        "total_count": int(sum(acc.count for acc in bucket_accumulators)),
        "total_score_sum": round(float(sum(acc.score_sum for acc in bucket_accumulators)), 12),
    }
    return boundaries, metrics, bucket_payload


def _compute_bucket_stats_from_existing_boundaries(
    path: Path,
    *,
    scoring_run_id: int,
    chunk_size: int,
    boundaries: list[dict[str, Any]],
) -> tuple[dict[str, Any], PreparationMetrics]:
    if len(boundaries) != 100:
        raise AudiencePreparationValidationError(RANK_BOUNDARIES_NOT_READY_MESSAGE)
    ordered_boundaries = sorted(boundaries, key=lambda row: int(row["percentile_bucket"]))
    bucket_accumulators = [ScoreBucketAccumulator(bucket=index) for index in range(1, 101)]

    repository = ScoringRepository(path)
    current_rank = 0
    bucket_index = 0
    cursor_score: float | None = None
    cursor_person_id: str | None = None
    scanned_rows = 0
    chunk_count = 0
    largest_chunk_rows = 0
    started = perf_counter()

    while True:
        rows = repository.fetch_rank_scan_chunk(
            scoring_run_id=scoring_run_id,
            limit=chunk_size,
            after_score=cursor_score,
            after_person_id=cursor_person_id,
        )
        if not rows:
            break
        chunk_count += 1
        scanned_rows += len(rows)
        if len(rows) > largest_chunk_rows:
            largest_chunk_rows = len(rows)
        for row in rows:
            current_rank += 1
            while (
                bucket_index < 99
                and current_rank > int(ordered_boundaries[bucket_index]["boundary_rank"])
            ):
                bucket_index += 1
            row_score = float(row["propensity_score"])
            bucket_accumulators[bucket_index].add(row_score)
            cursor_score = row_score
            cursor_person_id = str(row["person_id"])

    runtime_seconds = max(0.0, perf_counter() - started)
    rows_per_second = (scanned_rows / runtime_seconds) if runtime_seconds > 0 else 0.0
    payload = {
        "buckets": [accumulator.to_payload() for accumulator in bucket_accumulators],
        "total_count": int(sum(acc.count for acc in bucket_accumulators)),
        "total_score_sum": round(float(sum(acc.score_sum for acc in bucket_accumulators)), 12),
    }
    metrics = PreparationMetrics(
        scanned_rows=scanned_rows,
        chunk_size=chunk_size,
        chunk_count=chunk_count,
        largest_chunk_rows=largest_chunk_rows,
        runtime_seconds=runtime_seconds,
        rows_per_second=rows_per_second,
    )
    return payload, metrics


def _validate_snapshot_payload(
    *,
    population_count: int,
    options_payload: dict[str, Any],
    universe_profile_payload: dict[str, Any],
    historical_positive_profile_payload: dict[str, Any],
    score_bucket_stats_payload: dict[str, Any],
    expected_historical_positive_count: int,
    enforce_historical_positive_reconciliation: bool,
) -> None:
    if int(options_payload.get("population_count") or 0) != population_count:
        raise AudiencePreparationValidationError("Options population_count is inconsistent.")

    categorical_options = options_payload.get("categorical_options")
    if not isinstance(categorical_options, dict):
        raise AudiencePreparationValidationError("Options categorical payload is invalid.")
    for field in _AUDIENCE_CATEGORICAL_FIELDS:
        values = categorical_options.get(field)
        if not isinstance(values, list):
            raise AudiencePreparationValidationError(f"Options categorical field {field} is invalid.")
        count_total = 0
        for row in values:
            if not isinstance(row, dict):
                raise AudiencePreparationValidationError(f"Options categorical field {field} is invalid.")
            count = row.get("count")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise AudiencePreparationValidationError(f"Options categorical field {field} has invalid counts.")
            count_total += count
        if count_total != population_count:
            raise AudiencePreparationValidationError(
                f"Options categorical field {field} count total does not match population_count."
            )

    universe_summary = universe_profile_payload.get("summary")
    if not isinstance(universe_summary, dict):
        raise AudiencePreparationValidationError("Universe summary payload is invalid.")
    if int(universe_summary.get("count") or 0) != population_count:
        raise AudiencePreparationValidationError("Universe summary count is inconsistent.")

    universe_distributions = universe_profile_payload.get("distributions")
    if not isinstance(universe_distributions, dict):
        raise AudiencePreparationValidationError("Universe distribution payload is invalid.")
    for dimension in _PROFILE_DIMENSIONS:
        rows = universe_distributions.get(dimension)
        if not isinstance(rows, list):
            raise AudiencePreparationValidationError(
                f"Universe distribution {dimension} is invalid."
            )

    historical_summary = historical_positive_profile_payload.get("summary")
    if not isinstance(historical_summary, dict):
        raise AudiencePreparationValidationError("Historical summary payload is invalid.")
    historical_count = int(historical_summary.get("count") or 0)
    if historical_count < 0:
        raise AudiencePreparationValidationError("Historical summary count is invalid.")
    if enforce_historical_positive_reconciliation and historical_count != expected_historical_positive_count:
        raise AudiencePreparationValidationError(
            "Historical positives count does not match analysis provenance."
        )

    buckets = score_bucket_stats_payload.get("buckets")
    if not isinstance(buckets, list) or len(buckets) != 100:
        raise AudiencePreparationValidationError("Score bucket payload must include 100 buckets.")
    running_total = 0
    for index, bucket in enumerate(buckets, start=1):
        if not isinstance(bucket, dict):
            raise AudiencePreparationValidationError("Score bucket payload is invalid.")
        if int(bucket.get("bucket") or 0) != index:
            raise AudiencePreparationValidationError("Score bucket sequence is invalid.")
        count = bucket.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise AudiencePreparationValidationError("Score bucket count is invalid.")
        running_total += count
        for field in ("score_min", "score_max", "score_mean"):
            value = bucket.get(field)
            if value is None and count == 0:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise AudiencePreparationValidationError("Score bucket aggregate is invalid.")
            score = float(value)
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise AudiencePreparationValidationError("Score bucket aggregate is out of range.")
        if count > 0:
            score_min = float(bucket["score_min"])
            score_max = float(bucket["score_max"])
            score_mean = float(bucket["score_mean"])
            if not score_min <= score_mean <= score_max:
                raise AudiencePreparationValidationError("Score bucket ordering is invalid.")

    if running_total != population_count:
        raise AudiencePreparationValidationError("Score bucket total does not match population_count.")
    if int(score_bucket_stats_payload.get("total_count") or 0) != population_count:
        raise AudiencePreparationValidationError("Score bucket total_count is inconsistent.")


def _publish_analytics_snapshot(
    path: Path,
    *,
    scoring_row: dict[str, Any],
    score_bucket_stats_payload: dict[str, Any],
    created_at: str,
) -> None:
    score_summary = _decode_json_object(
        scoring_row.get("score_summary_json"),
        field_name="scoring_run.score_summary_json",
    )
    population_count = int(scoring_row["scored_person_count"])

    options_payload, universe_profile_payload = _build_static_options_and_universe_profile(
        path,
        population_count=population_count,
    )
    (
        historical_filters,
        reference_date,
        historical_positive_count,
        enforce_historical_positive_reconciliation,
    ) = _resolve_historical_context_for_snapshot(
        path,
        scoring_row=scoring_row,
    )
    historical_positive_profile_payload = _build_historical_positive_profile_snapshot(
        path,
        filters_payload=historical_filters,
        reference_date=reference_date,
    )

    _validate_snapshot_payload(
        population_count=population_count,
        options_payload=options_payload,
        universe_profile_payload=universe_profile_payload,
        historical_positive_profile_payload=historical_positive_profile_payload,
        score_bucket_stats_payload=score_bucket_stats_payload,
        expected_historical_positive_count=historical_positive_count,
        enforce_historical_positive_reconciliation=enforce_historical_positive_reconciliation,
    )

    AudienceAnalyticsSnapshotRepository(path).upsert_snapshot(
        scoring_run_id=int(scoring_row["scoring_run_id"]),
        analytics_contract_version=AUDIENCE_ANALYTICS_CONTRACT_VERSION,
        model_run_id=int(scoring_row["model_run_id"]),
        analysis_run_id=_require_positive_int(score_summary.get("analysis_run_id"), field_name="analysis_run_id"),
        customer_import_id=_require_positive_int(score_summary.get("customer_import_id"), field_name="customer_import_id"),
        customer_source_checksum=str(score_summary.get("customer_source_checksum", "")),
        campaign_sales_import_id=_require_positive_int(
            score_summary.get("campaign_sales_import_id"),
            field_name="campaign_sales_import_id",
        ),
        campaign_sales_source_checksum=str(score_summary.get("campaign_sales_source_checksum", "")),
        demographic_import_id=_require_positive_int(score_summary.get("demographic_import_id"), field_name="demographic_import_id"),
        demographic_source_checksum=str(score_summary.get("demographic_source_checksum", "")),
        feature_contract_version=str(scoring_row["feature_contract_version"]),
        feature_contract_sha256=str(scoring_row["feature_contract_sha256"]),
        artifact_sha256=str(scoring_row["artifact_sha256"]),
        filter_contract_version=AUDIENCE_FILTER_CONTRACT_VERSION,
        rank_contract_version=DEFAULT_RANK_CONTRACT_VERSION,
        selection_contract_version=AUDIENCE_SELECTION_CONTRACT_VERSION,
        population_count=population_count,
        options_payload=options_payload,
        universe_profile_payload=universe_profile_payload,
        historical_positive_profile_payload=historical_positive_profile_payload,
        score_bucket_stats_payload=score_bucket_stats_payload,
        created_at=created_at,
    )


def _validate_preparation_inputs(
    database_path: str | Path,
    *,
    scoring_run_id: int,
    rank_contract_version: str,
    conflict_when_fully_prepared: bool,
) -> dict[str, Any]:
    scoring_repository = ScoringRepository(database_path)
    scoring_run = scoring_repository.fetch_scoring_run(scoring_run_id)
    if scoring_run is None:
        raise AudiencePreparationValidationError(SCORING_RUN_NOT_FOUND_MESSAGE)
    if scoring_run["status"] != "COMPLETED":
        raise AudiencePreparationConflictError(SCORING_RUN_NOT_COMPLETED_MESSAGE)

    aggregates = scoring_repository.fetch_score_aggregates(scoring_run_id)
    score_count = int(aggregates["score_count"])
    if score_count != int(scoring_run["scored_person_count"]):
        raise AudiencePreparationConflictError(SCORING_COUNT_MISMATCH_MESSAGE)

    provenance = validate_completed_scoring_run_integrity_deep(
        database_path,
        scoring_run_id=scoring_run_id,
        verify_current_source_match=True,
    )
    if not provenance["is_canonical"]:
        raise AudiencePreparationConflictError(SCORING_RUN_NOT_CANONICAL_MESSAGE)

    canonical = find_current_canonical_run_for_model_lightweight(
        database_path,
        model_run_id=int(scoring_run["model_run_id"]),
    )
    if canonical is None or int(canonical["scoring_run_id"]) != scoring_run_id:
        raise AudiencePreparationConflictError(SCORING_RUN_NOT_CANONICAL_MESSAGE)

    existing_boundaries = AudienceRankRepository(database_path).fetch_boundaries(scoring_run_id)
    boundaries_prepared = (
        len(existing_boundaries) == 100
        and all(str(row["rank_contract_version"]) == rank_contract_version for row in existing_boundaries)
    )

    analytics_currentness = validate_audience_analytics_snapshot_currentness(
        database_path,
        scoring_run_id=scoring_run_id,
        analytics_contract_version=AUDIENCE_ANALYTICS_CONTRACT_VERSION,
        cache={},
    )
    analytics_prepared = bool(analytics_currentness["analytics_prepared"])
    if conflict_when_fully_prepared and boundaries_prepared and analytics_prepared:
        raise AudiencePreparationConflictError(EXISTING_AUDIENCE_PREPARATION_CONFLICT_MESSAGE)

    return {
        "scoring_run_id": scoring_run_id,
        "model_run_id": int(scoring_run["model_run_id"]),
        "score_count": score_count,
        "scoring_row": scoring_run,
        "existing_boundaries": existing_boundaries,
        "boundaries_prepared": boundaries_prepared,
        "analytics_prepared": analytics_prepared,
    }


def submit_audience_preparation_job_request(
    database_path: str | Path | None,
    request_payload: dict[str, Any],
    *,
    submitter: WorkerSubmitter | None = None,
) -> dict[str, Any]:
    path = initialize_database(database_path)
    if not isinstance(request_payload, dict):
        raise AudiencePreparationValidationError("Audience preparation request must be a JSON object.")

    scoring_run_id = _require_positive_int(
        request_payload.get("scoring_run_id"),
        field_name="scoring_run_id",
    )
    rank_contract_version = _normalize_rank_contract_version(
        request_payload.get("rank_contract_version", DEFAULT_RANK_CONTRACT_VERSION)
    )

    _validate_preparation_inputs(
        path,
        scoring_run_id=scoring_run_id,
        rank_contract_version=rank_contract_version,
        conflict_when_fully_prepared=True,
    )

    repository = JobRepository(path)
    if repository.find_active_compute_job() is not None:
        raise AudiencePreparationConflictError(ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE)

    try:
        job_id = repository.create_audience_preparation_job(
            created_at=_utc_timestamp(),
            request_payload={
                "scoring_run_id": scoring_run_id,
                "rank_contract_version": rank_contract_version,
            },
        )
    except ActiveComputeJobConflictError as exc:
        raise AudiencePreparationConflictError(ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE) from exc
    except JobValidationError as exc:
        raise AudiencePreparationValidationError(str(exc)) from exc

    worker_submitter = submit_audience_preparation_job if submitter is None else submitter
    try:
        if submitter is None:
            from app.jobs.executor import submit_audience_preparation_job

            worker_submitter = submit_audience_preparation_job
        else:
            worker_submitter = submitter
        worker_submitter(path, job_id)
    except Exception as exc:
        repository.mark_failed(
            job_id=job_id,
            finished_at=_utc_timestamp(),
            error_message=_bounded_internal_error(exc),
            model_run_id=None,
            message=AUDIENCE_PREPARATION_SUBMISSION_FAILURE_MESSAGE,
        )
        raise AudiencePreparationSubmissionError(AUDIENCE_PREPARATION_SUBMISSION_FAILURE_MESSAGE) from exc

    row = repository.fetch_job(job_id)
    if row is None:
        raise AudiencePreparationServiceError("Queued audience preparation job could not be reloaded.")
    return _public_job_summary(row)


def get_audience_preparation_status(
    database_path: str | Path,
    *,
    scoring_run_id: int,
    rank_contract_version: str = DEFAULT_RANK_CONTRACT_VERSION,
) -> dict[str, Any]:
    path = initialize_database(database_path)
    normalized_scoring_run_id = _require_positive_int(scoring_run_id, field_name="scoring_run_id")
    normalized_rank_contract_version = _normalize_rank_contract_version(rank_contract_version)

    scoring_row = ScoringRepository(path).fetch_scoring_run(normalized_scoring_run_id)
    if scoring_row is None:
        raise AudiencePreparationValidationError(SCORING_RUN_NOT_FOUND_MESSAGE)

    boundaries = AudienceRankRepository(path).fetch_boundaries(normalized_scoring_run_id)
    ready = (
        len(boundaries) == 100
        and all(
            str(row["rank_contract_version"]) == normalized_rank_contract_version
            for row in boundaries
        )
    )
    analytics_currentness = validate_audience_analytics_snapshot_currentness(
        path,
        scoring_run_id=normalized_scoring_run_id,
        analytics_contract_version=AUDIENCE_ANALYTICS_CONTRACT_VERSION,
        cache={},
    )
    ready_for_current_actions = (
        ready
        and bool(analytics_currentness["analytics_prepared"])
        and bool(analytics_currentness["is_canonical"])
        and bool(analytics_currentness["source_verified"])
    )

    active_job = JobRepository(path).find_active_compute_job()
    active_for_run: dict[str, Any] | None = None
    if active_job is not None and active_job.get("job_type") == "AUDIENCE_PREPARATION":
        request_json = active_job.get("request_json")
        if isinstance(request_json, str):
            try:
                request_payload = json.loads(request_json)
            except (TypeError, ValueError):
                request_payload = None
            if (
                isinstance(request_payload, dict)
                and request_payload.get("scoring_run_id") == normalized_scoring_run_id
            ):
                active_for_run = _public_job_summary(active_job)

    return {
        "scoring_run_id": normalized_scoring_run_id,
        "model_run_id": int(scoring_row["model_run_id"]),
        "status": str(scoring_row["status"]),
        "rank_contract_version": normalized_rank_contract_version,
        "analytics_contract_version": AUDIENCE_ANALYTICS_CONTRACT_VERSION,
        "prepared": ready,
        "analytics_prepared": bool(analytics_currentness["analytics_prepared"]),
        "is_canonical": bool(analytics_currentness["is_canonical"]),
        "source_verified": bool(analytics_currentness["source_verified"]),
        "ready_for_current_audience_actions": ready_for_current_actions,
        "currentness_issues": [str(item) for item in analytics_currentness["issues"]],
        "analytics_snapshot_created_at": analytics_currentness.get("snapshot_created_at"),
        "boundary_count": len(boundaries),
        "total_population": (
            int(boundaries[0]["total_population"]) if boundaries else int(scoring_row["scored_person_count"])
        ),
        "active_job": active_for_run,
    }


def list_audience_preparation_runs(
    database_path: str | Path,
    *,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    path = initialize_database(database_path)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise AudiencePreparationValidationError("limit must be an integer between 1 and 100.")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise AudiencePreparationValidationError("offset must be a non-negative integer.")

    with get_connection(path) as connection:
        rows = connection.execute(
            """
            SELECT
                s.scoring_run_id,
                s.model_run_id,
                s.completed_at,
                s.scored_person_count,
                COUNT(b.percentile_bucket) AS boundary_count,
                MIN(b.rank_contract_version) AS rank_contract_version
            FROM scoring_runs s
            LEFT JOIN audience_rank_boundaries b
                ON b.scoring_run_id = s.scoring_run_id
            WHERE s.status = 'COMPLETED'
            GROUP BY
                s.scoring_run_id,
                s.model_run_id,
                s.completed_at,
                s.scored_person_count
            ORDER BY s.completed_at DESC, s.scoring_run_id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

    summaries: list[dict[str, Any]] = []
    currentness_cache: dict[str, Any] = {}
    for row in rows:
        boundary_count = int(row["boundary_count"])
        analytics_currentness = validate_audience_analytics_snapshot_currentness(
            path,
            scoring_run_id=int(row["scoring_run_id"]),
            analytics_contract_version=AUDIENCE_ANALYTICS_CONTRACT_VERSION,
            cache=currentness_cache,
        )
        prepared = boundary_count == 100 and str(row["rank_contract_version"] or "") == DEFAULT_RANK_CONTRACT_VERSION
        analytics_prepared = bool(analytics_currentness["analytics_prepared"])
        summaries.append(
            {
                "scoring_run_id": int(row["scoring_run_id"]),
                "model_run_id": int(row["model_run_id"]),
                "completed_at": row["completed_at"],
                "scored_person_count": int(row["scored_person_count"]),
                "prepared": prepared,
                "analytics_prepared": analytics_prepared,
                "analytics_contract_version": AUDIENCE_ANALYTICS_CONTRACT_VERSION,
                "is_canonical": bool(analytics_currentness["is_canonical"]),
                "source_verified": bool(analytics_currentness["source_verified"]),
                "ready_for_current_audience_actions": (
                    prepared
                    and analytics_prepared
                    and bool(analytics_currentness["is_canonical"])
                    and bool(analytics_currentness["source_verified"])
                ),
                "currentness_issues": [str(item) for item in analytics_currentness["issues"]],
                "rank_contract_version": row["rank_contract_version"] if prepared else None,
                "boundary_count": boundary_count,
                "analytics_snapshot_created_at": analytics_currentness.get("snapshot_created_at"),
            }
        )
    return summaries


def run_audience_rank_preparation(
    database_path: str | Path,
    *,
    scoring_run_id: int,
    rank_contract_version: str = DEFAULT_RANK_CONTRACT_VERSION,
    chunk_size: int = DEFAULT_PREPARATION_SCAN_CHUNK_SIZE,
) -> dict[str, Any]:
    path = initialize_database(database_path)
    normalized_scoring_run_id = _require_positive_int(scoring_run_id, field_name="scoring_run_id")
    normalized_rank_contract_version = _normalize_rank_contract_version(rank_contract_version)
    normalized_chunk_size = _normalize_scan_chunk_size(chunk_size)

    envelope = _validate_preparation_inputs(
        path,
        scoring_run_id=normalized_scoring_run_id,
        rank_contract_version=normalized_rank_contract_version,
        conflict_when_fully_prepared=False,
    )

    existing_boundaries = envelope["existing_boundaries"]
    boundaries_prepared = bool(envelope["boundaries_prepared"])
    analytics_prepared = bool(envelope["analytics_prepared"])

    if boundaries_prepared and analytics_prepared:
        return {
            "scoring_run_id": normalized_scoring_run_id,
            "model_run_id": int(envelope["model_run_id"]),
            "rank_contract_version": normalized_rank_contract_version,
            "analytics_contract_version": AUDIENCE_ANALYTICS_CONTRACT_VERSION,
            "boundary_count": len(existing_boundaries),
            "total_population": int(envelope["score_count"]),
            "scanned_rows": 0,
            "chunk_size": normalized_chunk_size,
            "chunk_count": 0,
            "largest_chunk_rows": 0,
            "runtime_seconds": 0.0,
            "rows_per_second": 0.0,
            "boundaries_prepared": True,
            "analytics_prepared": True,
        }

    boundary_rows: list[dict[str, Any]]
    score_bucket_stats_payload: dict[str, Any]
    metrics: PreparationMetrics
    if boundaries_prepared:
        boundary_rows = [dict(row) for row in existing_boundaries]
        score_bucket_stats_payload, metrics = _compute_bucket_stats_from_existing_boundaries(
            path,
            scoring_run_id=normalized_scoring_run_id,
            chunk_size=normalized_chunk_size,
            boundaries=boundary_rows,
        )
    else:
        boundaries, metrics, score_bucket_stats_payload = _compute_boundaries_for_run(
            path,
            scoring_run_id=normalized_scoring_run_id,
            chunk_size=normalized_chunk_size,
        )
        boundary_rows = [row.to_row() for row in boundaries]

    # Revalidate canonical provenance and score count before publishing boundaries.
    revalidated = _validate_preparation_inputs(
        path,
        scoring_run_id=normalized_scoring_run_id,
        rank_contract_version=normalized_rank_contract_version,
        conflict_when_fully_prepared=False,
    )
    created_at = _utc_timestamp()
    rank_repository = AudienceRankRepository(path)
    if not boundaries_prepared:
        rank_repository.replace_boundaries(
            scoring_run_id=normalized_scoring_run_id,
            rank_contract_version=normalized_rank_contract_version,
            created_at=created_at,
            boundaries=boundary_rows,
        )

    persisted = rank_repository.fetch_boundaries(normalized_scoring_run_id)
    if len(persisted) != 100:
        raise AudiencePreparationValidationError("Persisted audience boundaries are incomplete.")

    _publish_analytics_snapshot(
        path,
        scoring_row=revalidated["scoring_row"],
        score_bucket_stats_payload=score_bucket_stats_payload,
        created_at=created_at,
    )
    snapshot_currentness = validate_audience_analytics_snapshot_currentness(
        path,
        scoring_run_id=normalized_scoring_run_id,
        analytics_contract_version=AUDIENCE_ANALYTICS_CONTRACT_VERSION,
        cache={},
    )
    if not snapshot_currentness["analytics_prepared"]:
        raise AudiencePreparationConflictError(
            "Audience analytics snapshot could not be validated after publication."
        )

    return {
        "scoring_run_id": normalized_scoring_run_id,
        "model_run_id": int(envelope["model_run_id"]),
        "rank_contract_version": normalized_rank_contract_version,
        "analytics_contract_version": AUDIENCE_ANALYTICS_CONTRACT_VERSION,
        "boundary_count": len(persisted),
        "total_population": int(revalidated["score_count"]),
        "boundaries_prepared": True,
        "analytics_prepared": True,
        **metrics.to_payload(),
    }


__all__ = (
    "ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE",
    "AUDIENCE_ANALYTICS_CONTRACT_VERSION",
    "AUDIENCE_FILTER_CONTRACT_VERSION",
    "AUDIENCE_SELECTION_CONTRACT_VERSION",
    "DEFAULT_PREPARATION_SCAN_CHUNK_SIZE",
    "DEFAULT_RANK_CONTRACT_VERSION",
    "EXISTING_AUDIENCE_PREPARATION_CONFLICT_MESSAGE",
    "RANK_BOUNDARIES_NOT_READY_MESSAGE",
    "SCORING_COUNT_MISMATCH_MESSAGE",
    "SCORING_RUN_NOT_CANONICAL_MESSAGE",
    "SCORING_RUN_NOT_COMPLETED_MESSAGE",
    "SCORING_RUN_NOT_FOUND_MESSAGE",
    "AudiencePreparationConflictError",
    "AudiencePreparationServiceError",
    "AudiencePreparationSubmissionError",
    "AudiencePreparationValidationError",
    "classify_decile",
    "classify_percentile_bucket",
    "classify_rank_band",
    "get_audience_preparation_status",
    "list_audience_preparation_runs",
    "run_audience_rank_preparation",
    "submit_audience_preparation_job_request",
    "validate_audience_analytics_snapshot_currentness",
)
