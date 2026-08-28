"""Phase 6 Step 4 audience filter, estimate, and keyset search service."""

from __future__ import annotations

import base64
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from string import hexdigits
from typing import Any

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories.historical_repository import (
    HistoricalRepository,
    build_matching_observations_cte,
)
from app.repositories.model_run_repository import ModelRunRepository
from app.repositories.audience_rank_repository import AudienceRankRepository
from app.repositories.scoring_repository import ScoringRepository
from app.schemas.historical import HistoricalAnalysisFilters
from app.services.audience_preparation_service import classify_decile, classify_percentile_bucket
from app.services.historical_source_provenance_service import (
    HistoricalSourceProvenanceError,
    is_saved_analysis_provenance_current,
)
from app.services.prospect_scoring_service import (
    find_current_canonical_run_for_model,
    validate_completed_scoring_run_provenance,
)


AUDIENCE_FILTER_CONTRACT_VERSION = "1"
AUDIENCE_RANK_CONTRACT_VERSION = "1"
AUDIENCE_SELECTION_CONTRACT_VERSION = "1"

DEFAULT_SEARCH_PAGE_SIZE = 50
MINIMUM_SEARCH_PAGE_SIZE = 1
MAXIMUM_SEARCH_PAGE_SIZE = 100
MAXIMUM_CATEGORICAL_FILTER_VALUES = 100
MAXIMUM_SELECTION_TARGET_COUNT = 1_000_000
CURSOR_VERSION = "1"

SELECTION_MODE_ALL_MATCHING = "ALL_MATCHING"
SELECTION_MODE_TOP_N = "TOP_N"

SCORING_RUN_NOT_FOUND_MESSAGE = "The requested scoring run was not found."
SCORING_RUN_NOT_COMPLETED_MESSAGE = "The requested scoring run is not completed."
SCORING_RUN_NOT_CANONICAL_MESSAGE = (
    "The requested scoring run is not current for its model and source provenance."
)
RANK_BOUNDARIES_NOT_READY_MESSAGE = "Audience rank boundaries are not prepared for this scoring run."
CURSOR_INVALID_MESSAGE = "The pagination cursor is invalid."
CURSOR_MISMATCH_MESSAGE = "The pagination cursor does not match this request."

_ALLOWED_NUMERIC_FILTERS = {
    "score_min",
    "score_max",
    "age_min",
    "age_max",
    "individual_yearly_income_min",
    "individual_yearly_income_max",
    "family_member_count_min",
    "family_member_count_max",
}
_ALLOWED_RANKING_FILTERS = {
    "top_percentile_max",
    "deciles",
    "rank_bands",
}
_ALLOWED_CATEGORICAL_FILTERS = (
    "gender",
    "state",
    "marital_status",
    "education",
    "employment_status",
    "resident_status",
    "resident_type",
    "type_of_employment",
)
_ALLOWED_FILTER_KEYS = (
    _ALLOWED_NUMERIC_FILTERS
    | _ALLOWED_RANKING_FILTERS
    | set(_ALLOWED_CATEGORICAL_FILTERS)
)

_RANK_BAND_ORDER = (
    "ELITE",
    "VERY_HIGH",
    "HIGH",
    "MEDIUM",
    "LOW",
    "VERY_LOW",
)
_RANK_BAND_RANGES: dict[str, tuple[int, int]] = {
    "ELITE": (1, 1),
    "VERY_HIGH": (2, 5),
    "HIGH": (6, 10),
    "MEDIUM": (11, 25),
    "LOW": (26, 50),
    "VERY_LOW": (51, 100),
}

_SCORE_SEMANTICS = {
    "range": [0.0, 1.0],
    "higher_is_better": True,
    "ordering": "propensity_score DESC, person_id ASC",
    "note": "Scores are relative propensity ranks for the current scored universe.",
}

_PII_POLICY = {
    "person_level_pii_exposed": False,
    "blocked_fields": [
        "first_name",
        "last_name",
        "email",
        "phone_number",
        "address_line_1",
        "address_line_2",
        "street",
        "postal_code",
        "ethnicity",
        "religion",
    ],
}

PROFILE_GROUP_UNIVERSE = "universe"
PROFILE_GROUP_MATCHING = "matching"
PROFILE_GROUP_SELECTED = "selected"
PROFILE_GROUP_HISTORICAL_POSITIVES = "historical_positives"

PROFILE_DIMENSIONS = (
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

PROFILE_BAND_ORDERS: dict[str, tuple[str, ...]] = {
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

SAVED_ANALYSIS_NOT_FOUND_MESSAGE = "The model historical analysis was not found."
SAVED_ANALYSIS_INVALID_MESSAGE = "The model historical analysis is invalid for audience profiling."

SELECTED_TOPN_CTE = (
    "selected_members AS MATERIALIZED ("
    "SELECT * FROM matching_members "
    "ORDER BY propensity_score DESC, person_id ASC "
    "LIMIT ?"
    ")"
)

SELECTED_ALL_MATCHING_CTE = "selected_members AS MATERIALIZED (SELECT * FROM matching_members)"

SEARCH_QUERY_INITIAL = """
    SELECT
        p.person_id,
        p.propensity_score,
        d.age,
        d.gender,
        d.state,
        d.individual_yearly_income,
        d.marital_status,
        d.education,
        d.employment_status,
        d.resident_status,
        d.resident_type,
        d.family_member_count,
        d.type_of_employment
    FROM propensity_scores p
    INNER JOIN demographics d ON d.person_id = p.person_id
    WHERE p.scoring_run_id = ?
    {predicate_sql}
    ORDER BY p.propensity_score DESC, p.person_id ASC
    LIMIT ?
"""

SEARCH_QUERY_AFTER = """
    SELECT
        p.person_id,
        p.propensity_score,
        d.age,
        d.gender,
        d.state,
        d.individual_yearly_income,
        d.marital_status,
        d.education,
        d.employment_status,
        d.resident_status,
        d.resident_type,
        d.family_member_count,
        d.type_of_employment
    FROM propensity_scores p
    INNER JOIN demographics d ON d.person_id = p.person_id
    WHERE p.scoring_run_id = ?
    {predicate_sql}
    AND (p.propensity_score < ? OR (p.propensity_score = ? AND p.person_id > ?))
    ORDER BY p.propensity_score DESC, p.person_id ASC
    LIMIT ?
"""


class AudienceQueryServiceError(RuntimeError):
    """Base class for audience query failures."""


class AudienceQueryValidationError(AudienceQueryServiceError):
    """Raised when request payloads or cursor values are invalid."""


class AudienceQueryConflictError(AudienceQueryServiceError):
    """Raised when canonical-currentness or readiness constraints are violated."""


@dataclass(frozen=True)
class NormalizedAudienceFilters:
    payload: dict[str, Any]
    canonical_json: str
    filter_hash: str


@dataclass(frozen=True)
class NormalizedSelection:
    payload: dict[str, Any]


@dataclass(frozen=True)
class DecodedCursor:
    scoring_run_id: int
    last_score: float
    last_person_id: str
    filter_hash: str
    rank_contract_version: str


def _require_positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AudienceQueryValidationError(f"{field_name} must be a positive integer.")
    return value


def _require_non_empty_text(value: Any, *, field_name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise AudienceQueryValidationError(f"{field_name} must be text.")
    normalized = value.strip()
    if not normalized:
        raise AudienceQueryValidationError(f"{field_name} must not be blank.")
    if len(normalized) > maximum:
        raise AudienceQueryValidationError(f"{field_name} must not exceed {maximum} characters.")
    return normalized


def _optional_unit_interval(value: Any, *, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AudienceQueryValidationError(f"{field_name} must be numeric when provided.")
    score = float(value)
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise AudienceQueryValidationError(f"{field_name} must be finite and between 0 and 1.")
    return score


def _optional_non_negative_number(value: Any, *, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AudienceQueryValidationError(f"{field_name} must be numeric when provided.")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise AudienceQueryValidationError(f"{field_name} must be a finite non-negative number.")
    return numeric


def _optional_non_negative_int(value: Any, *, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AudienceQueryValidationError(
            f"{field_name} must be a non-negative integer when provided."
        )
    return value


def _normalize_deciles(value: Any) -> list[int]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AudienceQueryValidationError("deciles must be a list when provided.")
    if len(value) > MAXIMUM_CATEGORICAL_FILTER_VALUES:
        raise AudienceQueryValidationError(
            "deciles must not contain more than "
            f"{MAXIMUM_CATEGORICAL_FILTER_VALUES} values."
        )
    normalized: set[int] = set()
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or not 1 <= item <= 10:
            raise AudienceQueryValidationError("deciles values must be integers between 1 and 10.")
        normalized.add(item)
    return sorted(normalized)


def _normalize_rank_bands(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AudienceQueryValidationError("rank_bands must be a list when provided.")
    if len(value) > MAXIMUM_CATEGORICAL_FILTER_VALUES:
        raise AudienceQueryValidationError(
            "rank_bands must not contain more than "
            f"{MAXIMUM_CATEGORICAL_FILTER_VALUES} values."
        )
    seen: set[str] = set()
    for item in value:
        band = _require_non_empty_text(item, field_name="rank_bands[]", maximum=32).upper()
        if band not in _RANK_BAND_RANGES:
            raise AudienceQueryValidationError("rank_bands contains unsupported values.")
        seen.add(band)
    return [band for band in _RANK_BAND_ORDER if band in seen]


def _normalize_categorical_values(value: Any, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AudienceQueryValidationError(f"{field_name} must be a list when provided.")
    if len(value) > MAXIMUM_CATEGORICAL_FILTER_VALUES:
        raise AudienceQueryValidationError(
            f"{field_name} must not contain more than "
            f"{MAXIMUM_CATEGORICAL_FILTER_VALUES} values."
        )
    normalized: set[str] = set()
    for item in value:
        text = _require_non_empty_text(item, field_name=f"{field_name}[]", maximum=120)
        normalized.add(text)
    return sorted(normalized)


def _canonical_json(payload: dict[str, Any]) -> str:
    try:
        return json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise AudienceQueryValidationError("Audience filters contain non-serializable values.") from exc


def normalize_audience_filters(raw_filters: Any) -> NormalizedAudienceFilters:
    if raw_filters is None:
        raw_filters = {}
    if not isinstance(raw_filters, dict):
        raise AudienceQueryValidationError("filters must be an object.")

    unexpected_keys = sorted(set(raw_filters) - _ALLOWED_FILTER_KEYS)
    if unexpected_keys:
        joined = ", ".join(unexpected_keys)
        raise AudienceQueryValidationError(f"filters contain unknown keys: {joined}")

    score_min = _optional_unit_interval(raw_filters.get("score_min"), field_name="score_min")
    score_max = _optional_unit_interval(raw_filters.get("score_max"), field_name="score_max")
    if score_min is not None and score_max is not None and score_min > score_max:
        raise AudienceQueryValidationError("score_min cannot exceed score_max.")

    age_min = _optional_non_negative_int(raw_filters.get("age_min"), field_name="age_min")
    age_max = _optional_non_negative_int(raw_filters.get("age_max"), field_name="age_max")
    if age_min is not None and age_max is not None and age_min > age_max:
        raise AudienceQueryValidationError("age_min cannot exceed age_max.")

    income_min = _optional_non_negative_number(
        raw_filters.get("individual_yearly_income_min"),
        field_name="individual_yearly_income_min",
    )
    income_max = _optional_non_negative_number(
        raw_filters.get("individual_yearly_income_max"),
        field_name="individual_yearly_income_max",
    )
    if income_min is not None and income_max is not None and income_min > income_max:
        raise AudienceQueryValidationError(
            "individual_yearly_income_min cannot exceed individual_yearly_income_max."
        )

    family_min = _optional_non_negative_int(
        raw_filters.get("family_member_count_min"),
        field_name="family_member_count_min",
    )
    family_max = _optional_non_negative_int(
        raw_filters.get("family_member_count_max"),
        field_name="family_member_count_max",
    )
    if family_min is not None and family_max is not None and family_min > family_max:
        raise AudienceQueryValidationError(
            "family_member_count_min cannot exceed family_member_count_max."
        )

    top_percentile_max = raw_filters.get("top_percentile_max")
    if top_percentile_max is None:
        normalized_top_percentile = None
    elif isinstance(top_percentile_max, bool) or not isinstance(top_percentile_max, int):
        raise AudienceQueryValidationError("top_percentile_max must be an integer in 1..100.")
    elif not 1 <= top_percentile_max <= 100:
        raise AudienceQueryValidationError("top_percentile_max must be an integer in 1..100.")
    else:
        normalized_top_percentile = top_percentile_max

    deciles = _normalize_deciles(raw_filters.get("deciles"))
    rank_bands = _normalize_rank_bands(raw_filters.get("rank_bands"))

    normalized_payload = {
        "score_min": score_min,
        "score_max": score_max,
        "age_min": age_min,
        "age_max": age_max,
        "individual_yearly_income_min": income_min,
        "individual_yearly_income_max": income_max,
        "family_member_count_min": family_min,
        "family_member_count_max": family_max,
        "top_percentile_max": normalized_top_percentile,
        "deciles": deciles,
        "rank_bands": rank_bands,
    }
    for field in _ALLOWED_CATEGORICAL_FILTERS:
        normalized_payload[field] = _normalize_categorical_values(raw_filters.get(field), field_name=field)

    canonical = _canonical_json(normalized_payload)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return NormalizedAudienceFilters(
        payload=normalized_payload,
        canonical_json=canonical,
        filter_hash=digest,
    )


def normalize_selection(raw_selection: Any) -> NormalizedSelection:
    if raw_selection is None:
        raw_selection = {}
    if not isinstance(raw_selection, dict):
        raise AudienceQueryValidationError("selection must be an object.")

    unexpected = sorted(set(raw_selection) - {"mode", "target_count"})
    if unexpected:
        raise AudienceQueryValidationError(
            f"selection contains unknown keys: {', '.join(unexpected)}"
        )

    mode_raw = raw_selection.get("mode", SELECTION_MODE_ALL_MATCHING)
    mode = _require_non_empty_text(mode_raw, field_name="selection.mode", maximum=24).upper()
    if mode not in {SELECTION_MODE_ALL_MATCHING, SELECTION_MODE_TOP_N}:
        raise AudienceQueryValidationError("selection.mode is invalid.")

    target_count = raw_selection.get("target_count")
    normalized_target_count: int | None = None
    if target_count is not None:
        normalized_target_count = _require_positive_int(target_count, field_name="selection.target_count")

    if mode == SELECTION_MODE_TOP_N and normalized_target_count is None:
        raise AudienceQueryValidationError(
            "selection.target_count is required when selection.mode is TOP_N."
        )
    if (
        mode == SELECTION_MODE_TOP_N
        and normalized_target_count is not None
        and normalized_target_count > MAXIMUM_SELECTION_TARGET_COUNT
    ):
        raise AudienceQueryValidationError(
            "selection.target_count must not exceed "
            f"{MAXIMUM_SELECTION_TARGET_COUNT}."
        )
    if mode == SELECTION_MODE_ALL_MATCHING and normalized_target_count is not None:
        raise AudienceQueryValidationError(
            "selection.target_count must be null when selection.mode is ALL_MATCHING."
        )

    return NormalizedSelection(
        payload={
            "mode": mode,
            "target_count": normalized_target_count,
        }
    )


def _validate_cursor_hash(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise AudienceQueryValidationError(CURSOR_INVALID_MESSAGE)
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(char not in hexdigits for char in normalized):
        raise AudienceQueryValidationError(CURSOR_INVALID_MESSAGE)
    return normalized


def _encode_cursor(
    *,
    scoring_run_id: int,
    last_score: float,
    last_person_id: str,
    filter_hash: str,
    rank_contract_version: str,
) -> str:
    payload = {
        "v": CURSOR_VERSION,
        "scoring_run_id": int(scoring_run_id),
        "last_score": float(last_score),
        "last_person_id": last_person_id,
        "filter_hash": filter_hash,
        "rank_contract_version": rank_contract_version,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def _decode_cursor(cursor: Any) -> DecodedCursor:
    if cursor is None:
        raise AudienceQueryValidationError(CURSOR_INVALID_MESSAGE)
    token = _require_non_empty_text(cursor, field_name="cursor", maximum=512)
    padding = "=" * ((4 - (len(token) % 4)) % 4)
    try:
        raw_bytes = base64.urlsafe_b64decode(token + padding)
        decoded = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        raise AudienceQueryValidationError(CURSOR_INVALID_MESSAGE) from exc

    if not isinstance(decoded, dict):
        raise AudienceQueryValidationError(CURSOR_INVALID_MESSAGE)
    if decoded.get("v") != CURSOR_VERSION:
        raise AudienceQueryValidationError(CURSOR_INVALID_MESSAGE)

    scoring_run_id = _require_positive_int(decoded.get("scoring_run_id"), field_name="cursor.scoring_run_id")
    last_score = _optional_unit_interval(decoded.get("last_score"), field_name="cursor.last_score")
    if last_score is None:
        raise AudienceQueryValidationError(CURSOR_INVALID_MESSAGE)
    last_person_id = _require_non_empty_text(
        decoded.get("last_person_id"),
        field_name="cursor.last_person_id",
        maximum=128,
    )
    filter_hash = _validate_cursor_hash(decoded.get("filter_hash"), field_name="cursor.filter_hash")
    rank_contract_version = _require_non_empty_text(
        decoded.get("rank_contract_version"),
        field_name="cursor.rank_contract_version",
        maximum=24,
    )
    return DecodedCursor(
        scoring_run_id=scoring_run_id,
        last_score=last_score,
        last_person_id=last_person_id,
        filter_hash=filter_hash,
        rank_contract_version=rank_contract_version,
    )


def _bucket_upper_inclusive_sql(*, bucket: int, boundaries: list[dict[str, Any]]) -> tuple[str, list[Any]]:
    row = boundaries[bucket - 1]
    boundary_score = float(row["boundary_score"])
    boundary_person_id = str(row["boundary_person_id"])
    return (
        "(p.propensity_score > ? OR (p.propensity_score = ? AND p.person_id <= ?))",
        [boundary_score, boundary_score, boundary_person_id],
    )


def _bucket_lower_exclusive_sql(*, bucket: int, boundaries: list[dict[str, Any]]) -> tuple[str, list[Any]]:
    row = boundaries[bucket - 1]
    boundary_score = float(row["boundary_score"])
    boundary_person_id = str(row["boundary_person_id"])
    return (
        "(p.propensity_score < ? OR (p.propensity_score = ? AND p.person_id > ?))",
        [boundary_score, boundary_score, boundary_person_id],
    )


def _bucket_range_sql(
    *,
    start_bucket: int,
    end_bucket: int,
    boundaries: list[dict[str, Any]],
) -> tuple[str, list[Any]]:
    upper_sql, upper_params = _bucket_upper_inclusive_sql(bucket=end_bucket, boundaries=boundaries)
    if start_bucket <= 1:
        return upper_sql, upper_params
    lower_sql, lower_params = _bucket_lower_exclusive_sql(
        bucket=start_bucket - 1,
        boundaries=boundaries,
    )
    return f"({lower_sql} AND {upper_sql})", [*lower_params, *upper_params]


def _or_ranges_sql(
    ranges: list[tuple[int, int]],
    *,
    boundaries: list[dict[str, Any]],
) -> tuple[str, list[Any]]:
    range_sql_parts: list[str] = []
    params: list[Any] = []
    for start_bucket, end_bucket in ranges:
        sql, sql_params = _bucket_range_sql(
            start_bucket=start_bucket,
            end_bucket=end_bucket,
            boundaries=boundaries,
        )
        range_sql_parts.append(sql)
        params.extend(sql_params)
    return "(" + " OR ".join(range_sql_parts) + ")", params


def _rank_band_for_bucket(bucket: int) -> str:
    for name, (start_bucket, end_bucket) in _RANK_BAND_RANGES.items():
        if start_bucket <= bucket <= end_bucket:
            return name
    return "VERY_LOW"


def _optional_finite_float(value: Any) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if not math.isfinite(numeric):
        raise AudienceQueryValidationError("A computed aggregate value is not finite.")
    return numeric


def _safe_share(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 6)


def _selected_members_cte(selection: NormalizedSelection) -> tuple[str, list[Any]]:
    if selection.payload["mode"] == SELECTION_MODE_TOP_N:
        target_count = selection.payload["target_count"]
        if target_count is None:
            raise AudienceQueryValidationError(
                "selection.target_count is required when selection.mode is TOP_N."
            )
        return SELECTED_TOPN_CTE, [int(target_count)]
    return SELECTED_ALL_MATCHING_CTE, []


def _dimension_sort_key(dimension: str, category: str) -> tuple[Any, ...]:
    if dimension in PROFILE_BAND_ORDERS:
        order = PROFILE_BAND_ORDERS[dimension]
        positions = {label: index for index, label in enumerate(order)}
        return (positions.get(category, len(order)), category.casefold(), category)
    return (category.casefold(), category)


def _finalize_distribution_rows(
    *,
    rows: list[dict[str, Any]],
    group_counts: dict[str, int],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    distributions: dict[str, dict[str, list[dict[str, Any]]]] = {
        group_name: {dimension: [] for dimension in PROFILE_DIMENSIONS}
        for group_name in group_counts
    }
    for row in rows:
        group_name = str(row["group_name"])
        dimension = str(row["dimension"])
        if group_name not in distributions or dimension not in distributions[group_name]:
            continue
        count = int(row["category_count"])
        total = int(group_counts[group_name])
        distributions[group_name][dimension].append(
            {
                "category": str(row["category"]),
                "count": count,
                "share": _safe_share(count, total),
            }
        )

    for group_name, group_dimensions in distributions.items():
        for dimension, categories in group_dimensions.items():
            if dimension in PROFILE_BAND_ORDERS:
                categories.sort(
                    key=lambda item: _dimension_sort_key(
                        dimension,
                        str(item["category"]),
                    )
                )
            else:
                categories.sort(
                    key=lambda item: (
                        -int(item["count"]),
                        str(item["category"]).casefold(),
                        str(item["category"]),
                    )
                )
    return distributions


def _fetch_prospect_profile_summaries_and_distributions(
    *,
    path: Path,
    scoring_run_id: int,
    normalized_filters: NormalizedAudienceFilters,
    boundaries: list[dict[str, Any]],
    selection: NormalizedSelection,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, list[dict[str, Any]]]]]:
    predicates, predicate_params = _build_filter_predicates(
        normalized_filters=normalized_filters,
        boundaries=boundaries,
    )
    predicate_sql = ""
    if predicates:
        predicate_sql = " AND " + " AND ".join(predicates)

    selected_cte, selected_cte_params = _selected_members_cte(selection)

    summary_query = f"""
        WITH
        universe_members AS MATERIALIZED (
            SELECT
                p.person_id,
                p.propensity_score,
                d.age,
                d.individual_yearly_income,
                d.family_member_count,
                d.gender,
                d.state,
                d.marital_status,
                d.education,
                d.employment_status,
                d.resident_status,
                d.resident_type,
                d.type_of_employment
            FROM propensity_scores p
            INNER JOIN demographics d ON d.person_id = p.person_id
            WHERE p.scoring_run_id = ?
        ),
        matching_members AS MATERIALIZED (
            SELECT
                p.person_id,
                p.propensity_score,
                d.age,
                d.individual_yearly_income,
                d.family_member_count,
                d.gender,
                d.state,
                d.marital_status,
                d.education,
                d.employment_status,
                d.resident_status,
                d.resident_type,
                d.type_of_employment
            FROM propensity_scores p
            INNER JOIN demographics d ON d.person_id = p.person_id
            WHERE p.scoring_run_id = ?
            {predicate_sql}
        ),
        {selected_cte}
        SELECT
            '{PROFILE_GROUP_UNIVERSE}' AS group_name,
            COUNT(*) AS member_count,
            AVG(age) AS age_mean,
            AVG(individual_yearly_income) AS individual_yearly_income_mean,
            AVG(family_member_count) AS family_member_count_mean,
            MIN(propensity_score) AS score_min,
            AVG(propensity_score) AS score_mean,
            MAX(propensity_score) AS score_max
        FROM universe_members
        UNION ALL
        SELECT
            '{PROFILE_GROUP_MATCHING}' AS group_name,
            COUNT(*) AS member_count,
            AVG(age) AS age_mean,
            AVG(individual_yearly_income) AS individual_yearly_income_mean,
            AVG(family_member_count) AS family_member_count_mean,
            MIN(propensity_score) AS score_min,
            AVG(propensity_score) AS score_mean,
            MAX(propensity_score) AS score_max
        FROM matching_members
        UNION ALL
        SELECT
            '{PROFILE_GROUP_SELECTED}' AS group_name,
            COUNT(*) AS member_count,
            AVG(age) AS age_mean,
            AVG(individual_yearly_income) AS individual_yearly_income_mean,
            AVG(family_member_count) AS family_member_count_mean,
            MIN(propensity_score) AS score_min,
            AVG(propensity_score) AS score_mean,
            MAX(propensity_score) AS score_max
        FROM selected_members
    """

    summary_params: list[Any] = [
        scoring_run_id,
        scoring_run_id,
        *predicate_params,
        *selected_cte_params,
    ]

    distribution_query = f"""
        WITH
        universe_members AS MATERIALIZED (
            SELECT
                p.person_id,
                p.propensity_score,
                d.age,
                d.individual_yearly_income,
                d.family_member_count,
                d.gender,
                d.state,
                d.marital_status,
                d.education,
                d.employment_status,
                d.resident_status,
                d.resident_type,
                d.type_of_employment
            FROM propensity_scores p
            INNER JOIN demographics d ON d.person_id = p.person_id
            WHERE p.scoring_run_id = ?
        ),
        matching_members AS MATERIALIZED (
            SELECT
                p.person_id,
                p.propensity_score,
                d.age,
                d.individual_yearly_income,
                d.family_member_count,
                d.gender,
                d.state,
                d.marital_status,
                d.education,
                d.employment_status,
                d.resident_status,
                d.resident_type,
                d.type_of_employment
            FROM propensity_scores p
            INNER JOIN demographics d ON d.person_id = p.person_id
            WHERE p.scoring_run_id = ?
            {predicate_sql}
        ),
        {selected_cte},
        profile_members AS (
            SELECT '{PROFILE_GROUP_UNIVERSE}' AS group_name, * FROM universe_members
            UNION ALL
            SELECT '{PROFILE_GROUP_MATCHING}' AS group_name, * FROM matching_members
            UNION ALL
            SELECT '{PROFILE_GROUP_SELECTED}' AS group_name, * FROM selected_members
        ),
        normalized_members AS (
            SELECT
                group_name,
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
                COALESCE(NULLIF(TRIM(gender), ''), 'Unknown/Other') AS gender,
                COALESCE(NULLIF(TRIM(state), ''), 'Unknown/Other') AS state,
                COALESCE(NULLIF(TRIM(marital_status), ''), 'Unknown/Other') AS marital_status,
                COALESCE(NULLIF(TRIM(education), ''), 'Unknown/Other') AS education,
                COALESCE(NULLIF(TRIM(employment_status), ''), 'Unknown/Other') AS employment_status,
                COALESCE(NULLIF(TRIM(resident_status), ''), 'Unknown/Other') AS resident_status,
                COALESCE(NULLIF(TRIM(resident_type), ''), 'Unknown/Other') AS resident_type,
                COALESCE(NULLIF(TRIM(type_of_employment), ''), 'Unknown/Other') AS type_of_employment
            FROM profile_members
        ),
        profile_values AS (
            SELECT group_name, 'age_band' AS dimension, age_band AS category FROM normalized_members
            UNION ALL
            SELECT group_name, 'individual_yearly_income_band', individual_yearly_income_band FROM normalized_members
            UNION ALL
            SELECT group_name, 'family_member_count_band', family_member_count_band FROM normalized_members
            UNION ALL
            SELECT group_name, 'gender', gender FROM normalized_members
            UNION ALL
            SELECT group_name, 'state', state FROM normalized_members
            UNION ALL
            SELECT group_name, 'marital_status', marital_status FROM normalized_members
            UNION ALL
            SELECT group_name, 'education', education FROM normalized_members
            UNION ALL
            SELECT group_name, 'employment_status', employment_status FROM normalized_members
            UNION ALL
            SELECT group_name, 'resident_status', resident_status FROM normalized_members
            UNION ALL
            SELECT group_name, 'resident_type', resident_type FROM normalized_members
            UNION ALL
            SELECT group_name, 'type_of_employment', type_of_employment FROM normalized_members
        )
        SELECT
            group_name,
            dimension,
            category,
            COUNT(*) AS category_count
        FROM profile_values
        GROUP BY group_name, dimension, category
        ORDER BY group_name, dimension, category_count DESC, category COLLATE NOCASE, category
    """

    distribution_params: list[Any] = [
        scoring_run_id,
        scoring_run_id,
        *predicate_params,
        *selected_cte_params,
    ]

    with get_connection(path) as connection:
        summary_rows = [
            dict(row)
            for row in connection.execute(summary_query, summary_params).fetchall()
        ]
        distribution_rows = [
            dict(row)
            for row in connection.execute(distribution_query, distribution_params).fetchall()
        ]

    summaries: dict[str, dict[str, Any]] = {}
    group_counts: dict[str, int] = {}
    for row in summary_rows:
        group_name = str(row["group_name"])
        group_count = int(row["member_count"])
        group_counts[group_name] = group_count
        summaries[group_name] = {
            "count": group_count,
            "age_mean": _optional_finite_float(row["age_mean"]),
            "individual_yearly_income_mean": _optional_finite_float(
                row["individual_yearly_income_mean"]
            ),
            "family_member_count_mean": _optional_finite_float(
                row["family_member_count_mean"]
            ),
            "score_min": _optional_finite_float(row["score_min"]),
            "score_mean": _optional_finite_float(row["score_mean"]),
            "score_max": _optional_finite_float(row["score_max"]),
        }

    distributions = _finalize_distribution_rows(
        rows=distribution_rows,
        group_counts=group_counts,
    )
    return summaries, distributions


def _resolve_saved_historical_analysis_context(
    *,
    path: Path,
    scoring_row: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    model_row = ModelRunRepository(path).fetch_run(int(scoring_row["model_run_id"]))
    if model_row is None:
        raise AudienceQueryConflictError(SAVED_ANALYSIS_NOT_FOUND_MESSAGE)

    analysis_run_id = model_row.get("analysis_run_id")
    if isinstance(analysis_run_id, bool) or not isinstance(analysis_run_id, int) or analysis_run_id <= 0:
        raise AudienceQueryConflictError(SAVED_ANALYSIS_INVALID_MESSAGE)

    analysis_row = HistoricalRepository(path).fetch_analysis_run(analysis_run_id)
    if analysis_row is None:
        raise AudienceQueryConflictError(SAVED_ANALYSIS_NOT_FOUND_MESSAGE)
    if analysis_row.get("status") != "COMPLETED":
        raise AudienceQueryConflictError(SAVED_ANALYSIS_INVALID_MESSAGE)

    try:
        provenance_current, _ = is_saved_analysis_provenance_current(path, analysis_row)
    except HistoricalSourceProvenanceError as exc:
        raise AudienceQueryConflictError(SCORING_RUN_NOT_CANONICAL_MESSAGE) from exc
    if not provenance_current:
        raise AudienceQueryConflictError(SCORING_RUN_NOT_CANONICAL_MESSAGE)

    raw_filters = analysis_row.get("filters_json")
    if not isinstance(raw_filters, str) or not raw_filters.strip():
        raise AudienceQueryValidationError(SAVED_ANALYSIS_INVALID_MESSAGE)
    try:
        decoded_filters = json.loads(raw_filters)
    except (TypeError, ValueError) as exc:
        raise AudienceQueryValidationError(SAVED_ANALYSIS_INVALID_MESSAGE) from exc
    if not isinstance(decoded_filters, dict):
        raise AudienceQueryValidationError(SAVED_ANALYSIS_INVALID_MESSAGE)

    try:
        historical_filters = HistoricalAnalysisFilters.model_validate(
            {
                "analysis_name": str(analysis_row["analysis_name"]),
                **decoded_filters,
                "conversion_definition": str(analysis_row["conversion_definition"]),
            }
        )
    except Exception as exc:
        raise AudienceQueryValidationError(SAVED_ANALYSIS_INVALID_MESSAGE) from exc

    filters_payload = historical_filters.filter_payload()
    reference_date = filters_payload.get("contact_date_to")
    if not isinstance(reference_date, str) or not reference_date.strip():
        raise AudienceQueryValidationError(SAVED_ANALYSIS_INVALID_MESSAGE)
    return filters_payload, reference_date


def _fetch_historical_positive_summary_and_distributions(
    *,
    path: Path,
    filters_payload: dict[str, Any],
    reference_date: str,
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
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
                COALESCE(NULLIF(TRIM(gender), ''), 'Unknown/Other') AS gender,
                COALESCE(NULLIF(TRIM(state), ''), 'Unknown/Other') AS state,
                COALESCE(NULLIF(TRIM(marital_status), ''), 'Unknown/Other') AS marital_status,
                COALESCE(NULLIF(TRIM(education), ''), 'Unknown/Other') AS education,
                COALESCE(NULLIF(TRIM(employment_status), ''), 'Unknown/Other') AS employment_status,
                COALESCE(NULLIF(TRIM(resident_status), ''), 'Unknown/Other') AS resident_status,
                COALESCE(NULLIF(TRIM(resident_type), ''), 'Unknown/Other') AS resident_type,
                COALESCE(NULLIF(TRIM(type_of_employment), ''), 'Unknown/Other') AS type_of_employment
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

    summary = {
        "count": int(summary_row["member_count"]),
        "age_mean": _optional_finite_float(summary_row["age_mean"]),
        "individual_yearly_income_mean": _optional_finite_float(
            summary_row["individual_yearly_income_mean"]
        ),
        "family_member_count_mean": _optional_finite_float(
            summary_row["family_member_count_mean"]
        ),
        "score_min": None,
        "score_mean": None,
        "score_max": None,
    }

    grouped_rows = [
        {
            "group_name": PROFILE_GROUP_HISTORICAL_POSITIVES,
            "dimension": row["dimension"],
            "category": row["category"],
            "category_count": row["category_count"],
        }
        for row in distribution_rows
    ]
    distributions = _finalize_distribution_rows(
        rows=grouped_rows,
        group_counts={PROFILE_GROUP_HISTORICAL_POSITIVES: int(summary["count"])},
    )[PROFILE_GROUP_HISTORICAL_POSITIVES]
    return summary, distributions


def _build_dimension_comparison(
    *,
    dimension: str,
    selected_categories: list[dict[str, Any]],
    reference_categories: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    selected_share_by_category = {
        str(item["category"]): float(item["share"])
        for item in selected_categories
    }
    reference_share_by_category = {
        str(item["category"]): float(item["share"])
        for item in reference_categories
    }
    all_categories = sorted(
        set(selected_share_by_category) | set(reference_share_by_category),
        key=lambda category: _dimension_sort_key(dimension, category),
    )

    rows: list[dict[str, Any]] = []
    for category in all_categories:
        selected_share = selected_share_by_category.get(category, 0.0)
        reference_share = reference_share_by_category.get(category, 0.0)
        share_point_difference = round(selected_share - reference_share, 6)
        if reference_share == 0:
            index = None
        else:
            index = round(selected_share / reference_share, 6)
        rows.append(
            {
                "category": category,
                "selected_share": round(selected_share, 6),
                "reference_share": round(reference_share, 6),
                "share_point_difference": share_point_difference,
                "index": index,
            }
        )
    return rows


def _build_comparison_payload(
    *,
    selected_distributions: dict[str, list[dict[str, Any]]],
    reference_distributions: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    return {
        dimension: _build_dimension_comparison(
            dimension=dimension,
            selected_categories=selected_distributions.get(dimension, []),
            reference_categories=reference_distributions.get(dimension, []),
        )
        for dimension in PROFILE_DIMENSIONS
    }


def _derive_top_overindexed_traits(
    comparisons: dict[str, dict[str, list[dict[str, Any]]]],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    traits: list[dict[str, Any]] = []
    for comparison_name, dimensions in comparisons.items():
        for dimension, categories in dimensions.items():
            for category in categories:
                index = category.get("index")
                selected_share = float(category["selected_share"])
                if index is None or float(index) <= 1.0 or selected_share <= 0:
                    continue
                traits.append(
                    {
                        "comparison": comparison_name,
                        "dimension": dimension,
                        "category": category["category"],
                        "selected_share": selected_share,
                        "reference_share": float(category["reference_share"]),
                        "share_point_difference": float(category["share_point_difference"]),
                        "index": float(index),
                    }
                )
    traits.sort(
        key=lambda item: (
            -float(item["index"]),
            -float(item["share_point_difference"]),
            str(item["comparison"]),
            str(item["dimension"]),
            str(item["category"]).casefold(),
            str(item["category"]),
        )
    )
    return traits[:limit]


def _build_filter_predicates(
    *,
    normalized_filters: NormalizedAudienceFilters,
    boundaries: list[dict[str, Any]],
) -> tuple[list[str], list[Any]]:
    payload = normalized_filters.payload
    predicates: list[str] = []
    parameters: list[Any] = []

    if payload["score_min"] is not None:
        predicates.append("p.propensity_score >= ?")
        parameters.append(payload["score_min"])
    if payload["score_max"] is not None:
        predicates.append("p.propensity_score <= ?")
        parameters.append(payload["score_max"])

    if payload["age_min"] is not None:
        predicates.append("d.age >= ?")
        parameters.append(payload["age_min"])
    if payload["age_max"] is not None:
        predicates.append("d.age <= ?")
        parameters.append(payload["age_max"])

    if payload["individual_yearly_income_min"] is not None:
        predicates.append("d.individual_yearly_income >= ?")
        parameters.append(payload["individual_yearly_income_min"])
    if payload["individual_yearly_income_max"] is not None:
        predicates.append("d.individual_yearly_income <= ?")
        parameters.append(payload["individual_yearly_income_max"])

    if payload["family_member_count_min"] is not None:
        predicates.append("d.family_member_count >= ?")
        parameters.append(payload["family_member_count_min"])
    if payload["family_member_count_max"] is not None:
        predicates.append("d.family_member_count <= ?")
        parameters.append(payload["family_member_count_max"])

    if payload["top_percentile_max"] is not None:
        percentile_sql, percentile_params = _bucket_upper_inclusive_sql(
            bucket=int(payload["top_percentile_max"]),
            boundaries=boundaries,
        )
        predicates.append(percentile_sql)
        parameters.extend(percentile_params)

    deciles: list[int] = payload["deciles"]
    if deciles:
        decile_ranges = [(((decile - 1) * 10) + 1, decile * 10) for decile in deciles]
        decile_sql, decile_params = _or_ranges_sql(decile_ranges, boundaries=boundaries)
        predicates.append(decile_sql)
        parameters.extend(decile_params)

    rank_bands: list[str] = payload["rank_bands"]
    if rank_bands:
        band_ranges = [_RANK_BAND_RANGES[band] for band in rank_bands]
        band_sql, band_params = _or_ranges_sql(band_ranges, boundaries=boundaries)
        predicates.append(band_sql)
        parameters.extend(band_params)

    for field in _ALLOWED_CATEGORICAL_FILTERS:
        values: list[str] = payload[field]
        if not values:
            continue
        placeholders = ",".join("?" for _ in values)
        predicates.append(f"d.{field} IN ({placeholders})")
        parameters.extend(values)

    return predicates, parameters


def _require_prepared_canonical_context(
    database_path: str | Path,
    *,
    scoring_run_id: int,
) -> tuple[Path, dict[str, Any], list[dict[str, Any]]]:
    path = initialize_database(database_path)
    normalized_scoring_run_id = _require_positive_int(scoring_run_id, field_name="scoring_run_id")

    scoring_row = ScoringRepository(path).fetch_scoring_run(normalized_scoring_run_id)
    if scoring_row is None:
        raise AudienceQueryValidationError(SCORING_RUN_NOT_FOUND_MESSAGE)
    if scoring_row["status"] != "COMPLETED":
        raise AudienceQueryConflictError(SCORING_RUN_NOT_COMPLETED_MESSAGE)

    provenance = validate_completed_scoring_run_provenance(
        path,
        scoring_run_id=normalized_scoring_run_id,
        verify_current_source_match=True,
    )
    if not provenance["is_canonical"]:
        raise AudienceQueryConflictError(SCORING_RUN_NOT_CANONICAL_MESSAGE)

    canonical_row = find_current_canonical_run_for_model(
        path,
        model_run_id=int(scoring_row["model_run_id"]),
    )
    if canonical_row is None or int(canonical_row["scoring_run_id"]) != normalized_scoring_run_id:
        raise AudienceQueryConflictError(SCORING_RUN_NOT_CANONICAL_MESSAGE)

    boundaries = AudienceRankRepository(path).fetch_boundaries(normalized_scoring_run_id)
    if len(boundaries) != 100:
        raise AudienceQueryConflictError(RANK_BOUNDARIES_NOT_READY_MESSAGE)
    for index, row in enumerate(boundaries, start=1):
        if int(row["percentile_bucket"]) != index:
            raise AudienceQueryConflictError(RANK_BOUNDARIES_NOT_READY_MESSAGE)
        if str(row["rank_contract_version"]) != AUDIENCE_RANK_CONTRACT_VERSION:
            raise AudienceQueryConflictError(RANK_BOUNDARIES_NOT_READY_MESSAGE)

    return path, scoring_row, boundaries


def get_audience_filter_options(
    database_path: str | Path,
    *,
    scoring_run_id: int,
) -> dict[str, Any]:
    path, scoring_row, boundaries = _require_prepared_canonical_context(
        database_path,
        scoring_run_id=scoring_run_id,
    )

    with get_connection(path) as connection:
        numeric_row = connection.execute(
            """
            SELECT
                MIN(d.age) AS age_min,
                MAX(d.age) AS age_max,
                MIN(d.individual_yearly_income) AS individual_yearly_income_min,
                MAX(d.individual_yearly_income) AS individual_yearly_income_max,
                MIN(d.family_member_count) AS family_member_count_min,
                MAX(d.family_member_count) AS family_member_count_max
            FROM propensity_scores p
            INNER JOIN demographics d ON d.person_id = p.person_id
            WHERE p.scoring_run_id = ?
            """,
            (int(scoring_row["scoring_run_id"]),),
        ).fetchone()

        categorical_options: dict[str, list[dict[str, Any]]] = {}
        for field in _ALLOWED_CATEGORICAL_FILTERS:
            rows = connection.execute(
                f"""
                SELECT d.{field} AS option_value, COUNT(*) AS option_count
                FROM propensity_scores p
                INNER JOIN demographics d ON d.person_id = p.person_id
                WHERE p.scoring_run_id = ?
                    AND d.{field} IS NOT NULL
                    AND trim(CAST(d.{field} AS TEXT)) <> ''
                GROUP BY d.{field}
                ORDER BY d.{field} ASC
                """,
                (int(scoring_row["scoring_run_id"]),),
            ).fetchall()
            categorical_options[field] = [
                {
                    "value": str(row["option_value"]),
                    "count": int(row["option_count"]),
                }
                for row in rows
            ]

    return {
        "scoring_run_id": int(scoring_row["scoring_run_id"]),
        "filter_contract_version": AUDIENCE_FILTER_CONTRACT_VERSION,
        "rank_contract_version": AUDIENCE_RANK_CONTRACT_VERSION,
        "selection_contract_version": AUDIENCE_SELECTION_CONTRACT_VERSION,
        "source_verified": True,
        "population_count": int(scoring_row["scored_person_count"]),
        "score_summary": {
            "score_min": float(scoring_row["score_min"]),
            "score_max": float(scoring_row["score_max"]),
            "score_mean": float(scoring_row["score_mean"]),
        },
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
        "categorical_options": categorical_options,
        "rank_definitions": {
            "percentile_bucket_count": len(boundaries),
            "deciles": list(range(1, 11)),
            "rank_bands": {
                key: {"start_percentile_bucket": value[0], "end_percentile_bucket": value[1]}
                for key, value in _RANK_BAND_RANGES.items()
            },
            "top_percentile_semantics": "Top P percentile includes all rows ranked <= boundary(P).",
        },
        "pii_policy": _PII_POLICY,
        "score_semantics": _SCORE_SEMANTICS,
    }


def estimate_audience(
    database_path: str | Path,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(request_payload, dict):
        raise AudienceQueryValidationError("Estimate request must be a JSON object.")

    scoring_run_id = _require_positive_int(request_payload.get("scoring_run_id"), field_name="scoring_run_id")
    normalized_filters = normalize_audience_filters(request_payload.get("filters", {}))
    normalized_selection = normalize_selection(request_payload.get("selection", {}))

    path, scoring_row, boundaries = _require_prepared_canonical_context(
        database_path,
        scoring_run_id=scoring_run_id,
    )

    predicates, predicate_params = _build_filter_predicates(
        normalized_filters=normalized_filters,
        boundaries=boundaries,
    )
    where_sql = ""
    if predicates:
        where_sql = " AND " + " AND ".join(predicates)

    with get_connection(path) as connection:
        row = connection.execute(
            f"""
            SELECT
                COUNT(*) AS matching_count,
                MIN(p.propensity_score) AS score_min,
                AVG(p.propensity_score) AS score_mean,
                MAX(p.propensity_score) AS score_max
            FROM propensity_scores p
            INNER JOIN demographics d ON d.person_id = p.person_id
            WHERE p.scoring_run_id = ?
            {where_sql}
            """,
            [scoring_run_id, *predicate_params],
        ).fetchone()

    matching_count = int(row["matching_count"])
    mode = str(normalized_selection.payload["mode"])
    target_count = normalized_selection.payload["target_count"]
    if mode == SELECTION_MODE_TOP_N and target_count is not None:
        selected_count = min(target_count, matching_count)
    else:
        selected_count = matching_count

    return {
        "scoring_run_id": int(scoring_row["scoring_run_id"]),
        "filter_contract_version": AUDIENCE_FILTER_CONTRACT_VERSION,
        "selection_contract_version": AUDIENCE_SELECTION_CONTRACT_VERSION,
        "filter_hash": normalized_filters.filter_hash,
        "normalized_filters": normalized_filters.payload,
        "selection": normalized_selection.payload,
        "matching_count": matching_count,
        "selected_count": int(selected_count),
        "score_min": float(row["score_min"]) if row["score_min"] is not None else None,
        "score_mean": float(row["score_mean"]) if row["score_mean"] is not None else None,
        "score_max": float(row["score_max"]) if row["score_max"] is not None else None,
        "source_verified": True,
    }


def search_audience(
    database_path: str | Path,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(request_payload, dict):
        raise AudienceQueryValidationError("Search request must be a JSON object.")

    scoring_run_id = _require_positive_int(request_payload.get("scoring_run_id"), field_name="scoring_run_id")
    normalized_filters = normalize_audience_filters(request_payload.get("filters", {}))

    page_size = request_payload.get("page_size", DEFAULT_SEARCH_PAGE_SIZE)
    if isinstance(page_size, bool) or not isinstance(page_size, int):
        raise AudienceQueryValidationError("page_size must be an integer.")
    if not MINIMUM_SEARCH_PAGE_SIZE <= page_size <= MAXIMUM_SEARCH_PAGE_SIZE:
        raise AudienceQueryValidationError(
            f"page_size must be between {MINIMUM_SEARCH_PAGE_SIZE} and {MAXIMUM_SEARCH_PAGE_SIZE}."
        )

    raw_cursor = request_payload.get("cursor")
    decoded_cursor: DecodedCursor | None = None
    if raw_cursor is not None:
        decoded_cursor = _decode_cursor(raw_cursor)

    path, scoring_row, boundaries = _require_prepared_canonical_context(
        database_path,
        scoring_run_id=scoring_run_id,
    )

    if decoded_cursor is not None:
        if decoded_cursor.scoring_run_id != scoring_run_id:
            raise AudienceQueryConflictError(CURSOR_MISMATCH_MESSAGE)
        if decoded_cursor.filter_hash != normalized_filters.filter_hash:
            raise AudienceQueryConflictError(CURSOR_MISMATCH_MESSAGE)
        if decoded_cursor.rank_contract_version != AUDIENCE_RANK_CONTRACT_VERSION:
            raise AudienceQueryConflictError(CURSOR_MISMATCH_MESSAGE)

    predicates, predicate_params = _build_filter_predicates(
        normalized_filters=normalized_filters,
        boundaries=boundaries,
    )
    predicate_sql = ""
    if predicates:
        predicate_sql = " AND " + " AND ".join(predicates)

    query_parameters: list[Any]
    if decoded_cursor is None:
        query = SEARCH_QUERY_INITIAL.format(predicate_sql=predicate_sql)
        query_parameters = [scoring_run_id, *predicate_params, page_size + 1]
    else:
        query = SEARCH_QUERY_AFTER.format(predicate_sql=predicate_sql)
        query_parameters = [
            scoring_run_id,
            *predicate_params,
            decoded_cursor.last_score,
            decoded_cursor.last_score,
            decoded_cursor.last_person_id,
            page_size + 1,
        ]

    with get_connection(path) as connection:
        rows = [dict(row) for row in connection.execute(query, query_parameters).fetchall()]

    has_more = len(rows) > page_size
    page_rows = rows[:page_size]

    enriched_rows: list[dict[str, Any]] = []
    for row in page_rows:
        person_id = str(row["person_id"])
        score = float(row["propensity_score"])
        percentile_bucket = classify_percentile_bucket(score, person_id, boundaries)
        decile = classify_decile(percentile_bucket)
        rank_band = _rank_band_for_bucket(percentile_bucket)
        enriched_rows.append(
            {
                "person_id": person_id,
                "propensity_score": score,
                "age": int(row["age"]),
                "gender": row["gender"],
                "state": row["state"],
                "individual_yearly_income": float(row["individual_yearly_income"]),
                "marital_status": row["marital_status"],
                "education": row["education"],
                "employment_status": row["employment_status"],
                "resident_status": row["resident_status"],
                "resident_type": row["resident_type"],
                "family_member_count": int(row["family_member_count"]),
                "type_of_employment": row["type_of_employment"],
                "percentile_bucket": percentile_bucket,
                "decile": decile,
                "rank_band": rank_band,
            }
        )

    next_cursor: str | None = None
    if has_more and enriched_rows:
        last_row = enriched_rows[-1]
        next_cursor = _encode_cursor(
            scoring_run_id=scoring_run_id,
            last_score=float(last_row["propensity_score"]),
            last_person_id=str(last_row["person_id"]),
            filter_hash=normalized_filters.filter_hash,
            rank_contract_version=AUDIENCE_RANK_CONTRACT_VERSION,
        )

    return {
        "scoring_run_id": int(scoring_row["scoring_run_id"]),
        "rank_contract_version": AUDIENCE_RANK_CONTRACT_VERSION,
        "filter_hash": normalized_filters.filter_hash,
        "rows": enriched_rows,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "score_semantics": _SCORE_SEMANTICS,
    }


def profile_audience(
    database_path: str | Path,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(request_payload, dict):
        raise AudienceQueryValidationError("Profile request must be a JSON object.")

    scoring_run_id = _require_positive_int(request_payload.get("scoring_run_id"), field_name="scoring_run_id")
    normalized_filters = normalize_audience_filters(request_payload.get("filters", {}))
    normalized_selection = normalize_selection(request_payload.get("selection", {}))

    path, scoring_row, boundaries = _require_prepared_canonical_context(
        database_path,
        scoring_run_id=scoring_run_id,
    )

    prospect_summary, prospect_distributions = _fetch_prospect_profile_summaries_and_distributions(
        path=path,
        scoring_run_id=scoring_run_id,
        normalized_filters=normalized_filters,
        boundaries=boundaries,
        selection=normalized_selection,
    )

    historical_filters_payload, reference_date = _resolve_saved_historical_analysis_context(
        path=path,
        scoring_row=scoring_row,
    )
    historical_summary, historical_distributions = _fetch_historical_positive_summary_and_distributions(
        path=path,
        filters_payload=historical_filters_payload,
        reference_date=reference_date,
    )

    summaries = {
        PROFILE_GROUP_UNIVERSE: prospect_summary[PROFILE_GROUP_UNIVERSE],
        PROFILE_GROUP_MATCHING: prospect_summary[PROFILE_GROUP_MATCHING],
        PROFILE_GROUP_SELECTED: prospect_summary[PROFILE_GROUP_SELECTED],
        PROFILE_GROUP_HISTORICAL_POSITIVES: historical_summary,
    }

    distributions = {
        PROFILE_GROUP_UNIVERSE: prospect_distributions[PROFILE_GROUP_UNIVERSE],
        PROFILE_GROUP_MATCHING: prospect_distributions[PROFILE_GROUP_MATCHING],
        PROFILE_GROUP_SELECTED: prospect_distributions[PROFILE_GROUP_SELECTED],
        PROFILE_GROUP_HISTORICAL_POSITIVES: historical_distributions,
    }

    selected_vs_universe = _build_comparison_payload(
        selected_distributions=distributions[PROFILE_GROUP_SELECTED],
        reference_distributions=distributions[PROFILE_GROUP_UNIVERSE],
    )
    selected_vs_historical_positives = _build_comparison_payload(
        selected_distributions=distributions[PROFILE_GROUP_SELECTED],
        reference_distributions=distributions[PROFILE_GROUP_HISTORICAL_POSITIVES],
    )
    comparisons = {
        "selected_vs_universe": selected_vs_universe,
        "selected_vs_historical_positives": selected_vs_historical_positives,
    }

    return {
        "scoring_run_id": int(scoring_row["scoring_run_id"]),
        "filter_contract_version": AUDIENCE_FILTER_CONTRACT_VERSION,
        "selection_contract_version": AUDIENCE_SELECTION_CONTRACT_VERSION,
        "rank_contract_version": AUDIENCE_RANK_CONTRACT_VERSION,
        "filter_hash": normalized_filters.filter_hash,
        "selection": normalized_selection.payload,
        "source_verified": True,
        "historical_reference_date": reference_date,
        "summary": summaries,
        "distributions": distributions,
        "comparisons": comparisons,
        "top_overindexed_traits": _derive_top_overindexed_traits(comparisons),
    }


__all__ = (
    "AUDIENCE_FILTER_CONTRACT_VERSION",
    "AUDIENCE_RANK_CONTRACT_VERSION",
    "AUDIENCE_SELECTION_CONTRACT_VERSION",
    "CURSOR_INVALID_MESSAGE",
    "CURSOR_MISMATCH_MESSAGE",
    "RANK_BOUNDARIES_NOT_READY_MESSAGE",
    "SAVED_ANALYSIS_INVALID_MESSAGE",
    "SAVED_ANALYSIS_NOT_FOUND_MESSAGE",
    "SCORING_RUN_NOT_CANONICAL_MESSAGE",
    "SCORING_RUN_NOT_COMPLETED_MESSAGE",
    "SCORING_RUN_NOT_FOUND_MESSAGE",
    "SELECTED_ALL_MATCHING_CTE",
    "SELECTED_TOPN_CTE",
    "SEARCH_QUERY_AFTER",
    "SEARCH_QUERY_INITIAL",
    "AudienceQueryConflictError",
    "AudienceQueryServiceError",
    "AudienceQueryValidationError",
    "estimate_audience",
    "get_audience_filter_options",
    "normalize_audience_filters",
    "normalize_selection",
    "profile_audience",
    "search_audience",
)
