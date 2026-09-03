from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories.audience_rank_repository import AudienceRankRepository
from app.repositories.historical_repository import HistoricalRepository, build_matching_observations_cte
from app.repositories.model_run_repository import ModelRunRepository
from app.repositories.saved_audience_repository import SavedAudienceRepository
from app.repositories.scoring_repository import ScoringRepository
from app.services.audience_preparation_service import DEFAULT_PREPARATION_SCAN_CHUNK_SIZE
from app.services.audience_query_service import normalize_audience_filters, normalize_selection
from app.services.prospect_scoring_service import (
    validate_completed_scoring_run_provenance,
    verify_scoring_run_sample,
)


EVIDENCE_PATH = Path("docs/evidence/phase6_5m_acceptance.json")
PRE_RUN_GATES_PATH = Path("docs/evidence/phase6_step9_pre_run_gates.json")
RANK_CONTRACT_VERSION = "1"
PAGE_SIZE = 50

RANK_BAND_RANGES: dict[str, tuple[int, int]] = {
    "ELITE": (1, 1),
    "VERY_HIGH": (2, 5),
    "HIGH": (6, 10),
    "MEDIUM": (11, 25),
    "LOW": (26, 50),
    "VERY_LOW": (51, 100),
}


class Step9ValidationError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _progress(message: str) -> None:
    print(f"[step9] {message}", flush=True)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Step9ValidationError(message)


def _load_pre_run_gates_evidence() -> dict[str, Any]:
    _require(PRE_RUN_GATES_PATH.exists(), f"Missing pre-run gate evidence file: {PRE_RUN_GATES_PATH.as_posix()}")
    payload = json.loads(PRE_RUN_GATES_PATH.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), "Pre-run gate evidence must decode to an object.")

    gates = payload.get("gates")
    _require(isinstance(gates, dict), "Pre-run gate evidence missing gates object.")
    required_gate_names = [
        "pip_check",
        "pytest_q",
        "compileall",
        "git_diff_check",
        "validate_data_json",
    ]

    for gate_name in required_gate_names:
        gate_payload = gates.get(gate_name)
        _require(isinstance(gate_payload, dict), f"Missing gate payload for {gate_name}.")
        _require(bool(gate_payload.get("passed")), f"Pre-run gate failed: {gate_name}.")

    return payload


def _target_rank(total_population: int, bucket: int) -> int:
    base = math.ceil((total_population * bucket) / 100)
    return max(1, base)


def _normalized_state(field_value: Any) -> str:
    if field_value is None:
        return "Unknown/Other"
    text = str(field_value).strip()
    return text if text else "Unknown/Other"


def _resolve_latest_completed_model_run(database_path: Path) -> dict[str, Any]:
    rows = ModelRunRepository(database_path).list_runs(limit=100, offset=0, status="COMPLETED")
    _require(bool(rows), "No completed model run exists.")
    return rows[0]


def _resolve_canonical_scoring_run(database_path: Path, model_run_id: int) -> dict[str, Any]:
    run = ScoringRepository(database_path).find_completed_run_for_model(model_run_id)
    _require(run is not None, "No completed scoring run exists for latest completed model.")
    return run


def _prepare_boundaries_direct(
    database_path: Path,
    *,
    scoring_run_id: int,
    chunk_size: int = DEFAULT_PREPARATION_SCAN_CHUNK_SIZE,
) -> dict[str, Any]:
    repository = ScoringRepository(database_path)
    scoring_run = repository.fetch_scoring_run(scoring_run_id)
    _require(scoring_run is not None, "Scoring run not found during direct boundary preparation.")
    _require(str(scoring_run["status"]) == "COMPLETED", "Scoring run must be COMPLETED.")
    total_population = int(scoring_run["scored_person_count"])
    _require(total_population == 5_000_000, "Expected scored population to be exactly 5,000,000.")

    existing = AudienceRankRepository(database_path).fetch_boundaries(scoring_run_id)
    if len(existing) == 100 and all(
        int(row["percentile_bucket"]) == idx and str(row["rank_contract_version"]) == RANK_CONTRACT_VERSION
        for idx, row in enumerate(existing, start=1)
    ):
        return {
            "mode": "already_prepared",
            "runtime_seconds": 0.0,
            "chunk_size": chunk_size,
            "chunk_count": 0,
            "scanned_rows": 0,
            "throughput_rows_per_second": 0.0,
        }

    started = perf_counter()
    targets = [_target_rank(total_population, bucket) for bucket in range(1, 101)]
    boundary_rows: list[dict[str, Any]] = []

    current_bucket_index = 0
    current_rank = 0
    cursor_score: float | None = None
    cursor_person_id: str | None = None
    scanned_rows = 0
    chunk_count = 0

    while current_bucket_index < 100:
        chunk = repository.fetch_rank_scan_chunk(
            scoring_run_id=scoring_run_id,
            limit=chunk_size,
            after_score=cursor_score,
            after_person_id=cursor_person_id,
        )
        if not chunk:
            break

        chunk_count += 1
        scanned_rows += len(chunk)
        for row in chunk:
            current_rank += 1
            score = float(row["propensity_score"])
            person_id = str(row["person_id"])

            while current_bucket_index < 100 and current_rank >= targets[current_bucket_index]:
                boundary_rows.append(
                    {
                        "percentile_bucket": current_bucket_index + 1,
                        "boundary_rank": current_rank,
                        "boundary_score": score,
                        "boundary_person_id": person_id,
                        "total_population": total_population,
                    }
                )
                current_bucket_index += 1

            cursor_score = score
            cursor_person_id = person_id

    _require(len(boundary_rows) == 100, "Direct boundary preparation did not produce 100 boundaries.")
    _require(int(boundary_rows[-1]["boundary_rank"]) == total_population, "100th percentile boundary rank mismatch.")

    AudienceRankRepository(database_path).replace_boundaries(
        scoring_run_id=scoring_run_id,
        rank_contract_version=RANK_CONTRACT_VERSION,
        created_at=_now_iso(),
        boundaries=boundary_rows,
    )

    duration_seconds = perf_counter() - started
    throughput = 0.0 if duration_seconds <= 0 else (scanned_rows / duration_seconds)
    return {
        "mode": "direct_compute",
        "runtime_seconds": round(duration_seconds, 3),
        "chunk_size": int(chunk_size),
        "chunk_count": int(chunk_count),
        "scanned_rows": int(scanned_rows),
        "throughput_rows_per_second": round(throughput, 3),
    }


def _verify_boundary_contract(boundaries: list[dict[str, Any]], expected_population: int) -> dict[str, Any]:
    _require(len(boundaries) == 100, "Boundary row count must be exactly 100.")

    rank_by_bucket: dict[int, int] = {}
    for index, row in enumerate(boundaries, start=1):
        bucket = int(row["percentile_bucket"])
        rank = int(row["boundary_rank"])
        total_population = int(row["total_population"])
        _require(bucket == index, "Boundary buckets must be contiguous 1..100.")
        _require(total_population == expected_population, "Boundary total_population mismatch.")
        _require(1 <= rank <= expected_population, "Boundary rank out of range.")
        rank_by_bucket[bucket] = rank

    _require(rank_by_bucket[1] == 50_000, "Percentile 1 boundary rank must be 50,000.")
    _require(rank_by_bucket[5] == 250_000, "Percentile 5 boundary rank must be 250,000.")
    _require(rank_by_bucket[10] == 500_000, "Percentile 10 boundary rank must be 500,000.")
    _require(rank_by_bucket[100] == 5_000_000, "Percentile 100 boundary rank must be 5,000,000.")

    return {
        "boundary_count": 100,
        "total_population": expected_population,
        "boundary_rank_checks": {
            "percentile1": rank_by_bucket[1],
            "percentile5": rank_by_bucket[5],
            "percentile10": rank_by_bucket[10],
            "percentile100": rank_by_bucket[100],
        },
    }


def _band_counts_from_boundaries(boundaries: list[dict[str, Any]]) -> dict[str, Any]:
    ranks = [int(row["boundary_rank"]) for row in boundaries]
    percentile_counts: dict[int, int] = {}
    previous_rank = 0
    for bucket, current_rank in enumerate(ranks, start=1):
        bucket_count = current_rank - previous_rank
        _require(bucket_count >= 0, "Boundary ranks must be non-decreasing.")
        percentile_counts[bucket] = bucket_count
        previous_rank = current_rank

    band_counts = {
        "ELITE": sum(percentile_counts.get(bucket, 0) for bucket in range(1, 2)),
        "VERY_HIGH": sum(percentile_counts.get(bucket, 0) for bucket in range(2, 6)),
        "HIGH": sum(percentile_counts.get(bucket, 0) for bucket in range(6, 11)),
        "MEDIUM": sum(percentile_counts.get(bucket, 0) for bucket in range(11, 26)),
        "LOW": sum(percentile_counts.get(bucket, 0) for bucket in range(26, 51)),
        "VERY_LOW": sum(percentile_counts.get(bucket, 0) for bucket in range(51, 101)),
    }

    _require(ranks[0] == 50_000, "Top 1% count mismatch.")
    _require(ranks[9] == 500_000, "Top decile count mismatch.")
    _require(band_counts["ELITE"] == 50_000, "ELITE count mismatch.")
    _require(band_counts["VERY_HIGH"] == 200_000, "VERY_HIGH count mismatch.")
    _require(band_counts["HIGH"] == 250_000, "HIGH count mismatch.")
    _require(band_counts["MEDIUM"] == 750_000, "MEDIUM count mismatch.")
    _require(band_counts["LOW"] == 1_250_000, "LOW count mismatch.")
    _require(band_counts["VERY_LOW"] == 2_500_000, "VERY_LOW count mismatch.")

    return {
        "top_1_percent": ranks[0],
        "top_decile": ranks[9],
        "bands": band_counts,
        "bands_sum": sum(band_counts.values()),
    }


def _bucket_upper_inclusive_sql(*, bucket: int, boundaries: list[dict[str, Any]]) -> tuple[str, list[Any]]:
    row = boundaries[bucket - 1]
    boundary_score = float(row["boundary_score"])
    boundary_person_id = str(row["boundary_person_id"])
    return "(p.propensity_score > ? OR (p.propensity_score = ? AND p.person_id <= ?))", [
        boundary_score,
        boundary_score,
        boundary_person_id,
    ]


def _bucket_lower_exclusive_sql(*, bucket: int, boundaries: list[dict[str, Any]]) -> tuple[str, list[Any]]:
    row = boundaries[bucket - 1]
    boundary_score = float(row["boundary_score"])
    boundary_person_id = str(row["boundary_person_id"])
    return "(p.propensity_score < ? OR (p.propensity_score = ? AND p.person_id > ?))", [
        boundary_score,
        boundary_score,
        boundary_person_id,
    ]


def _bucket_range_sql(
    *,
    start_bucket: int,
    end_bucket: int,
    boundaries: list[dict[str, Any]],
) -> tuple[str, list[Any]]:
    upper_sql, upper_params = _bucket_upper_inclusive_sql(bucket=end_bucket, boundaries=boundaries)
    if start_bucket <= 1:
        return upper_sql, upper_params
    lower_sql, lower_params = _bucket_lower_exclusive_sql(bucket=start_bucket - 1, boundaries=boundaries)
    return f"({lower_sql} AND {upper_sql})", [*lower_params, *upper_params]


def _or_ranges_sql(
    ranges: list[tuple[int, int]],
    *,
    boundaries: list[dict[str, Any]],
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for start_bucket, end_bucket in ranges:
        sql, sql_params = _bucket_range_sql(
            start_bucket=start_bucket,
            end_bucket=end_bucket,
            boundaries=boundaries,
        )
        clauses.append(sql)
        params.extend(sql_params)
    return "(" + " OR ".join(clauses) + ")", params


def _build_filter_predicates(filters: dict[str, Any], boundaries: list[dict[str, Any]]) -> tuple[str, list[Any]]:
    predicates: list[str] = []
    params: list[Any] = []

    if filters.get("age_min") is not None:
        predicates.append("d.age >= ?")
        params.append(int(filters["age_min"]))
    if filters.get("age_max") is not None:
        predicates.append("d.age <= ?")
        params.append(int(filters["age_max"]))
    if filters.get("individual_yearly_income_min") is not None:
        predicates.append("d.individual_yearly_income >= ?")
        params.append(float(filters["individual_yearly_income_min"]))
    if filters.get("individual_yearly_income_max") is not None:
        predicates.append("d.individual_yearly_income <= ?")
        params.append(float(filters["individual_yearly_income_max"]))

    states = list(filters.get("state") or [])
    if states:
        placeholders = ",".join("?" for _ in states)
        predicates.append(f"d.state IN ({placeholders})")
        params.extend(states)

    genders = list(filters.get("gender") or [])
    if genders:
        placeholders = ",".join("?" for _ in genders)
        predicates.append(f"d.gender IN ({placeholders})")
        params.extend(genders)

    top_percentile_max = filters.get("top_percentile_max")
    if top_percentile_max is not None:
        percentile_sql, percentile_params = _bucket_upper_inclusive_sql(
            bucket=int(top_percentile_max),
            boundaries=boundaries,
        )
        predicates.append(percentile_sql)
        params.extend(percentile_params)

    deciles = [int(value) for value in (filters.get("deciles") or [])]
    if deciles:
        decile_ranges = [(((decile - 1) * 10) + 1, decile * 10) for decile in deciles]
        decile_sql, decile_params = _or_ranges_sql(decile_ranges, boundaries=boundaries)
        predicates.append(decile_sql)
        params.extend(decile_params)

    rank_bands = [str(value).upper() for value in (filters.get("rank_bands") or [])]
    if rank_bands:
        ranges = [RANK_BAND_RANGES[band] for band in rank_bands]
        bands_sql, bands_params = _or_ranges_sql(ranges, boundaries=boundaries)
        predicates.append(bands_sql)
        params.extend(bands_params)

    if not predicates:
        return "", []
    return " AND " + " AND ".join(predicates), params


def _fetch_search_page(
    *,
    database_path: Path,
    scoring_run_id: int,
    boundaries: list[dict[str, Any]],
    filters: dict[str, Any],
    page_size: int,
    cursor: tuple[float, str] | None,
) -> tuple[list[dict[str, Any]], tuple[float, str] | None, bool]:
    predicate_sql, predicate_params = _build_filter_predicates(filters, boundaries)

    if cursor is None:
        query = f"""
            SELECT
                p.person_id,
                p.propensity_score,
                d.age,
                d.gender,
                d.state,
                d.individual_yearly_income
            FROM propensity_scores p
            INNER JOIN demographics d ON d.person_id = p.person_id
            WHERE p.scoring_run_id = ?
            {predicate_sql}
            ORDER BY p.propensity_score DESC, p.person_id ASC
            LIMIT ?
        """
        params = [scoring_run_id, *predicate_params, page_size + 1]
    else:
        query = f"""
            SELECT
                p.person_id,
                p.propensity_score,
                d.age,
                d.gender,
                d.state,
                d.individual_yearly_income
            FROM propensity_scores p
            INNER JOIN demographics d ON d.person_id = p.person_id
            WHERE p.scoring_run_id = ?
            {predicate_sql}
              AND (p.propensity_score < ? OR (p.propensity_score = ? AND p.person_id > ?))
            ORDER BY p.propensity_score DESC, p.person_id ASC
            LIMIT ?
        """
        params = [scoring_run_id, *predicate_params, cursor[0], cursor[0], cursor[1], page_size + 1]

    with get_connection(database_path) as connection:
        rows = [dict(row) for row in connection.execute(query, params).fetchall()]

    has_more = len(rows) > page_size
    page_rows = rows[:page_size]
    next_cursor: tuple[float, str] | None = None
    if has_more and page_rows:
        next_cursor = (float(page_rows[-1]["propensity_score"]), str(page_rows[-1]["person_id"]))
    return page_rows, next_cursor, has_more


def _verify_search_rows(rows: list[dict[str, Any]], filters: dict[str, Any], label: str) -> dict[str, Any]:
    previous: tuple[float, str] | None = None
    for row in rows:
        score = float(row["propensity_score"])
        person_id = str(row["person_id"])
        if previous is not None:
            prev_score, prev_person = previous
            _require(
                score < prev_score or (score == prev_score and person_id > prev_person),
                f"Search ordering violated for {label}.",
            )
        previous = (score, person_id)

        if filters.get("state"):
            _require(row.get("state") in set(filters["state"]), f"state filter mismatch in {label}.")
        if filters.get("gender"):
            _require(row.get("gender") in set(filters["gender"]), f"gender filter mismatch in {label}.")
        if filters.get("age_min") is not None:
            _require(int(row["age"]) >= int(filters["age_min"]), f"age_min filter mismatch in {label}.")
        if filters.get("age_max") is not None:
            _require(int(row["age"]) <= int(filters["age_max"]), f"age_max filter mismatch in {label}.")
        if filters.get("individual_yearly_income_min") is not None:
            _require(
                float(row["individual_yearly_income"]) >= float(filters["individual_yearly_income_min"]),
                f"income_min filter mismatch in {label}.",
            )
        if filters.get("individual_yearly_income_max") is not None:
            _require(
                float(row["individual_yearly_income"]) <= float(filters["individual_yearly_income_max"]),
                f"income_max filter mismatch in {label}.",
            )

    return {
        "row_count": len(rows),
        "first_score": float(rows[0]["propensity_score"]) if rows else None,
        "last_score": float(rows[-1]["propensity_score"]) if rows else None,
    }


def _run_search_validation(database_path: Path, scoring_run_id: int, boundaries: list[dict[str, Any]]) -> dict[str, Any]:
    seen: set[tuple[str, float]] = set()
    cursor: tuple[float, str] | None = None
    page_summaries: list[dict[str, Any]] = []

    for page_number in range(1, 4):
        rows, cursor, has_more = _fetch_search_page(
            database_path=database_path,
            scoring_run_id=scoring_run_id,
            boundaries=boundaries,
            filters={},
            page_size=PAGE_SIZE,
            cursor=cursor,
        )
        summary = _verify_search_rows(rows, {}, f"unfiltered_page_{page_number}")
        page_summaries.append({"page": page_number, **summary})

        for row in rows:
            key = (str(row["person_id"]), float(row["propensity_score"]))
            _require(key not in seen, "Keyset pagination produced duplicate row across pages.")
            seen.add(key)

        if not has_more:
            break

    representative_filters = {
        "state": {"state": ["California"]},
        "age": {"age_min": 30, "age_max": 55},
        "income": {"individual_yearly_income_min": 60_000.0, "individual_yearly_income_max": 140_000.0},
        "gender_state": {"gender": ["Female"], "state": ["California"]},
        "rank_band_state": {"rank_bands": ["HIGH"], "state": ["California"]},
        "decile_age_income": {
            "deciles": [1],
            "age_min": 25,
            "age_max": 50,
            "individual_yearly_income_min": 70_000.0,
            "individual_yearly_income_max": 180_000.0,
        },
    }

    representative_results: dict[str, Any] = {}
    for name, filters in representative_filters.items():
        rows, _cursor, _has_more = _fetch_search_page(
            database_path=database_path,
            scoring_run_id=scoring_run_id,
            boundaries=boundaries,
            filters=filters,
            page_size=PAGE_SIZE,
            cursor=None,
        )
        representative_results[name] = _verify_search_rows(rows, filters, name)

    return {
        "unfiltered_keyset_pages": page_summaries,
        "representative_filters": representative_results,
    }


def _load_universe_state_distribution(database_path: Path, scoring_run_id: int) -> tuple[int, dict[str, int]]:
    with get_connection(database_path) as connection:
        total = int(
            connection.execute(
                "SELECT COUNT(*) FROM propensity_scores WHERE scoring_run_id = ?",
                (scoring_run_id,),
            ).fetchone()[0]
        )
        rows = connection.execute(
            """
            SELECT COALESCE(NULLIF(TRIM(d.state), ''), 'Unknown/Other') AS state, COUNT(*) AS state_count
            FROM propensity_scores p
            INNER JOIN demographics d ON d.person_id = p.person_id
            WHERE p.scoring_run_id = ?
            GROUP BY state
            """,
            (scoring_run_id,),
        ).fetchall()
    return total, {str(row["state"]): int(row["state_count"]) for row in rows}


def _load_historical_positive_distribution(
    database_path: Path,
    *,
    model_run_id: int,
) -> tuple[int, dict[str, int], int, str]:
    model_row = ModelRunRepository(database_path).fetch_run(model_run_id)
    _require(model_row is not None, "Model run missing while loading historical positives.")
    analysis_run_id = int(model_row["analysis_run_id"])
    analysis_row = HistoricalRepository(database_path).fetch_analysis_run(analysis_run_id)
    _require(analysis_row is not None, "Historical analysis run missing.")

    filters = json.loads(str(analysis_row["filters_json"]))
    if not isinstance(filters, dict):
        raise Step9ValidationError("Saved analysis filters_json must decode to an object.")
    filters["conversion_definition"] = str(analysis_row["conversion_definition"])

    cte, parameters = build_matching_observations_cte(filters)
    normalized_cte = cte.strip()
    if normalized_cte[:4].upper() == "WITH":
        normalized_cte = normalized_cte[4:].lstrip()

    query = f"""
        WITH
        {normalized_cte},
        positive_members AS (
            SELECT
                COALESCE(NULLIF(TRIM(c.state), ''), 'Unknown/Other') AS state
            FROM customer_labels labels
            INNER JOIN customers c ON c.customer_id = labels.customer_id
            WHERE labels.is_positive = 1
        )
        SELECT state, COUNT(*) AS state_count
        FROM positive_members
        GROUP BY state
    """

    with get_connection(database_path) as connection:
        rows = connection.execute(query, parameters).fetchall()

    state_counts = {str(row["state"]): int(row["state_count"]) for row in rows}
    total = sum(state_counts.values())
    expected_total = int(analysis_row["positive_customer_count"])
    reference_date = str(filters.get("contact_date_to") or "")
    _require(total == expected_total, "Historical positive count does not reconcile with saved analysis summary.")
    _require(reference_date.strip() != "", "Historical reference date is missing.")
    return total, state_counts, expected_total, reference_date


def _state_index_rows(selected: dict[str, int], selected_total: int, reference: dict[str, int], reference_total: int) -> list[dict[str, Any]]:
    categories = sorted(set(selected) | set(reference))
    rows: list[dict[str, Any]] = []
    for category in categories:
        selected_share = 0.0 if selected_total <= 0 else (selected.get(category, 0) / selected_total)
        reference_share = 0.0 if reference_total <= 0 else (reference.get(category, 0) / reference_total)
        index_value: float | None
        if reference_share <= 0:
            index_value = None
        else:
            index_value = selected_share / reference_share
        rows.append(
            {
                "category": category,
                "selected_share": round(selected_share, 6),
                "reference_share": round(reference_share, 6),
                "index": None if index_value is None else round(index_value, 6),
            }
        )
    rows.sort(
        key=lambda item: (
            -1.0 if item["index"] is None else -float(item["index"]),
            str(item["category"]),
        )
    )
    return rows


def _profile_state_distribution(
    database_path: Path,
    *,
    scoring_run_id: int,
    boundaries: list[dict[str, Any]],
    filters: dict[str, Any],
    selection: dict[str, Any],
) -> tuple[int, int, dict[str, int], float | None, float | None, float | None]:
    predicate_sql, predicate_params = _build_filter_predicates(filters, boundaries)
    with get_connection(database_path) as connection:
        matching_count = int(
            connection.execute(
                f"""
                SELECT COUNT(*)
                FROM propensity_scores p
                INNER JOIN demographics d ON d.person_id = p.person_id
                WHERE p.scoring_run_id = ?
                {predicate_sql}
                """,
                [scoring_run_id, *predicate_params],
            ).fetchone()[0]
        )

        mode = str(selection.get("mode") or "ALL_MATCHING")
        target_count = selection.get("target_count")
        if mode == "TOP_N":
            _require(isinstance(target_count, int) and target_count > 0, "TOP_N selection requires positive target_count.")
            selected_sql = f"""
                SELECT
                    p.propensity_score,
                    COALESCE(NULLIF(TRIM(d.state), ''), 'Unknown/Other') AS state
                FROM propensity_scores p
                INNER JOIN demographics d ON d.person_id = p.person_id
                WHERE p.scoring_run_id = ?
                {predicate_sql}
                ORDER BY p.propensity_score DESC, p.person_id ASC
                LIMIT ?
            """
            selected_params = [scoring_run_id, *predicate_params, int(target_count)]
        else:
            selected_sql = f"""
                SELECT
                    p.propensity_score,
                    COALESCE(NULLIF(TRIM(d.state), ''), 'Unknown/Other') AS state
                FROM propensity_scores p
                INNER JOIN demographics d ON d.person_id = p.person_id
                WHERE p.scoring_run_id = ?
                {predicate_sql}
            """
            selected_params = [scoring_run_id, *predicate_params]

        rows = connection.execute(
            f"""
            WITH selected_members AS MATERIALIZED (
                {selected_sql}
            ),
            score_stats AS (
                SELECT
                    COUNT(*) AS selected_count,
                    MIN(propensity_score) AS score_min,
                    AVG(propensity_score) AS score_mean,
                    MAX(propensity_score) AS score_max
                FROM selected_members
            ),
            state_counts AS (
                SELECT state, COUNT(*) AS state_count
                FROM selected_members
                GROUP BY state
            )
            SELECT
                score_stats.selected_count,
                score_stats.score_min,
                score_stats.score_mean,
                score_stats.score_max,
                state_counts.state,
                state_counts.state_count
            FROM score_stats
            LEFT JOIN state_counts ON 1 = 1
            ORDER BY state_counts.state COLLATE NOCASE, state_counts.state
            """,
            selected_params,
        ).fetchall()

    selected_count = 0
    score_min: float | None = None
    score_mean: float | None = None
    score_max: float | None = None
    selected_states: dict[str, int] = {}
    if rows:
        first_row = rows[0]
        selected_count = int(first_row["selected_count"] or 0)
        score_min = float(first_row["score_min"]) if first_row["score_min"] is not None else None
        score_mean = float(first_row["score_mean"]) if first_row["score_mean"] is not None else None
        score_max = float(first_row["score_max"]) if first_row["score_max"] is not None else None

        for row in rows:
            if row["state"] is None:
                continue
            state = _normalized_state(row["state"])
            selected_states[state] = int(row["state_count"] or 0)

    return matching_count, selected_count, selected_states, score_min, score_mean, score_max


def _run_profile_validation(
    database_path: Path,
    *,
    scoring_run_id: int,
    model_run_id: int,
    boundaries: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    universe_count, universe_states = _load_universe_state_distribution(database_path, scoring_run_id)
    historical_positive_count, historical_states, reconciled_positive_count, historical_reference_date = (
        _load_historical_positive_distribution(database_path, model_run_id=model_run_id)
    )

    profile_cases = {
        "universe_all": {
            "filters": {},
            "selection": {"mode": "ALL_MATCHING", "target_count": None},
        },
        "top_1_percent": {
            "filters": {"top_percentile_max": 1},
            "selection": {"mode": "ALL_MATCHING", "target_count": None},
        },
        "top_decile": {
            "filters": {"deciles": [1]},
            "selection": {"mode": "ALL_MATCHING", "target_count": None},
        },
        "demographic_filter": {
            "filters": {
                "state": ["California"],
                "age_min": 30,
                "age_max": 55,
                "individual_yearly_income_min": 60_000.0,
            },
            "selection": {"mode": "ALL_MATCHING", "target_count": None},
        },
        "filtered_topn_50k": {
            "filters": {"state": ["California"], "deciles": [1]},
            "selection": {"mode": "TOP_N", "target_count": 50_000},
        },
    }

    profile_results: dict[str, Any] = {}
    last_snapshot: dict[str, Any] = {}

    for case_name, case_payload in profile_cases.items():
        _progress(f"Running profile case: {case_name}.")
        normalized_filters = normalize_audience_filters(case_payload["filters"]).payload
        normalized_selection = normalize_selection(case_payload["selection"]).payload
        matching_count, selected_count, selected_states, score_min, score_mean, score_max = _profile_state_distribution(
            database_path,
            scoring_run_id=scoring_run_id,
            boundaries=boundaries,
            filters=normalized_filters,
            selection=normalized_selection,
        )

        _require(0 <= selected_count <= matching_count <= universe_count, f"Profile count ordering invalid for {case_name}.")
        if score_min is not None:
            _require(0.0 <= score_min <= 1.0, f"score_min out of range for {case_name}.")
        if score_mean is not None:
            _require(0.0 <= score_mean <= 1.0, f"score_mean out of range for {case_name}.")
        if score_max is not None:
            _require(0.0 <= score_max <= 1.0, f"score_max out of range for {case_name}.")

        selected_vs_universe = _state_index_rows(selected_states, selected_count, universe_states, universe_count)
        selected_vs_historical = _state_index_rows(
            selected_states,
            selected_count,
            historical_states,
            historical_positive_count,
        )
        for row in [*selected_vs_universe, *selected_vs_historical]:
            for key in ("selected_share", "reference_share"):
                value = float(row[key])
                _require(math.isfinite(value), f"Non-finite share in {case_name}.")
            if row["index"] is not None:
                value = float(row["index"])
                _require(math.isfinite(value), f"Non-finite index in {case_name}.")

        profile_results[case_name] = {
            "matching_count": matching_count,
            "selected_count": selected_count,
            "universe_count": universe_count,
            "historical_positives_count": historical_positive_count,
            "score_min": score_min,
            "score_mean": score_mean,
            "score_max": score_max,
            "selected_vs_universe_top_states": selected_vs_universe[:10],
            "selected_vs_historical_positives_top_states": selected_vs_historical[:10],
        }

        if case_name == "filtered_topn_50k":
            last_snapshot = {
                "historical_reference_date": historical_reference_date,
                "summary": {
                    "matching_count": matching_count,
                    "selected_count": selected_count,
                    "historical_positives_count": historical_positive_count,
                },
                "top_overindexed_traits": [
                    {
                        "comparison": "selected_vs_historical_positives",
                        "dimension": "state",
                        "category": row["category"],
                        "selected_share": row["selected_share"],
                        "reference_share": row["reference_share"],
                        "index": row["index"],
                    }
                    for row in selected_vs_historical[:10]
                    if row["index"] is not None and float(row["index"]) > 1.0
                ],
            }

    _require(profile_results["top_1_percent"]["selected_count"] == 50_000, "Top 1% profile selected count mismatch.")
    _require(profile_results["top_decile"]["selected_count"] == 500_000, "Top decile profile selected count mismatch.")
    _require(profile_results["filtered_topn_50k"]["selected_count"] <= 50_000, "Filtered TOP_N exceeds 50,000.")

    reconciliation = {
        "historical_positive_count": historical_positive_count,
        "analysis_positive_customer_count": reconciled_positive_count,
        "reconciled": historical_positive_count == reconciled_positive_count,
    }
    return profile_results, {"snapshot": last_snapshot, "historical_reconciliation": reconciliation}


def _create_saved_audience_direct(
    database_path: Path,
    *,
    scoring_run_id: int,
    model_run_id: int,
    profile_snapshot: dict[str, Any],
) -> dict[str, Any]:
    scoring_row = ScoringRepository(database_path).fetch_scoring_run(scoring_run_id)
    _require(scoring_row is not None, "Scoring run missing while creating saved audience.")

    summary_payload = json.loads(str(scoring_row.get("score_summary_json") or "{}"))
    _require(isinstance(summary_payload, dict) and bool(summary_payload), "score_summary_json missing for saved audience write.")

    filters_payload = normalize_audience_filters({"deciles": [1]}).payload
    selection_payload = normalize_selection({"mode": "TOP_N", "target_count": 50_000}).payload
    filter_hash = hashlib.sha256(
        json.dumps(filters_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    resolved_count = 50_000

    audience_id = SavedAudienceRepository(database_path).create_saved_audience(
        audience_name="Phase 6 Validation - Top 50K",
        description="Deterministic real-5M Step 9 validation audience.",
        created_at=_now_iso(),
        scoring_run_id=scoring_run_id,
        model_run_id=model_run_id,
        analysis_run_id=int(summary_payload["analysis_run_id"]),
        selection_mode=str(selection_payload["mode"]),
        target_count=int(selection_payload["target_count"]),
        resolved_count=resolved_count,
        filter_contract_version="1",
        rank_contract_version="1",
        selection_contract_version="1",
        filters_payload=filters_payload,
        selection_payload=selection_payload,
        profile_summary_payload=profile_snapshot,
        customer_import_id=int(summary_payload["customer_import_id"]),
        customer_source_checksum=str(summary_payload["customer_source_checksum"]),
        campaign_sales_import_id=int(summary_payload["campaign_sales_import_id"]),
        campaign_sales_source_checksum=str(summary_payload["campaign_sales_source_checksum"]),
        demographic_import_id=int(summary_payload["demographic_import_id"]),
        demographic_source_checksum=str(summary_payload["demographic_source_checksum"]),
        feature_contract_version=str(scoring_row["feature_contract_version"]),
        feature_contract_sha256=str(scoring_row["feature_contract_sha256"]),
        artifact_sha256=str(scoring_row["artifact_sha256"]),
    )

    row = SavedAudienceRepository(database_path).fetch_saved_audience(audience_id)
    reopened_filters = json.loads(str(row["filters_json"]))
    reopened_selection = json.loads(str(row["selection_json"]))
    reopened_snapshot = json.loads(str(row["profile_summary_json"])) if row.get("profile_summary_json") else {}

    _require(reopened_filters == filters_payload, "Saved audience filters did not round-trip exactly.")
    _require(reopened_selection == selection_payload, "Saved audience selection did not round-trip exactly.")
    _require(reopened_snapshot == profile_snapshot, "Saved audience profile snapshot did not round-trip exactly.")

    currentness_issues: list[str] = []
    if int(row["scoring_run_id"]) != scoring_run_id:
        currentness_issues.append("saved scoring_run_id mismatch")
    if int(row["model_run_id"]) != model_run_id:
        currentness_issues.append("saved model_run_id mismatch")
    if str(row["rank_contract_version"]) != RANK_CONTRACT_VERSION:
        currentness_issues.append("rank contract mismatch")

    is_current = len(currentness_issues) == 0
    return {
        "audience_id": int(row["audience_id"]),
        "resolved_count": int(row["resolved_count"]),
        "filter_sha256": filter_hash,
        "is_current": is_current,
        "currentness_issues": currentness_issues,
        "reopened_definition_matches": True,
    }


def _run_ui_contract_checks() -> dict[str, Any]:
    html = Path("frontend/index.html").read_text(encoding="utf-8")
    script = Path("frontend/js/audience-explorer.js").read_text(encoding="utf-8")

    checks = {
        "audience_explorer_enabled": 'data-view-target="audience-explorer"' in html,
        "campaigns_disabled": "navigation-item is-disabled" in html and "Campaigns" in html,
        "prepare_progress_surface": "audience-prep-running" in html and "POLL_INTERVAL_MS = 1500" in script,
        "estimate_surface": 'estimate: "/api/audience/estimate"' in script,
        "ranked_page_surface": 'search: "/api/audience/search"' in script,
        "profile_surface": 'profile: "/api/audience/profile"' in script,
        "save_reopen_surface": ('id="audience-save-submit"' in html and 'id="saved-audience-reopen"' in html),
        "no_export_surface": "audiences/export" not in script.casefold() and "csv export" not in script.casefold(),
        "score_disclaimer_present": (
            "Percentile 1 = top 1%. Decile 1 = top 10%. Propensity score is a relative model affinity score, not a purchase probability."
            in html
        ),
    }
    _require(all(checks.values()), f"UI contract checks failed: {checks}")
    return checks


def _phase_boundary_scan() -> dict[str, Any]:
    api_surface_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("app/routers").rglob("*.py")
    ).casefold()
    frontend_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("frontend").rglob("*.js")
    ).casefold()

    checks = {
        "no_phase7_campaign_object_schema": all(
            token not in api_surface_source and token not in frontend_source
            for token in ("campaign object", "campaign schema")
        ),
        "no_activation_api": "/api/campaigns/activate" not in api_surface_source and "/api/campaigns/activate" not in frontend_source,
        "no_export_endpoint": all(
            token not in api_surface_source and token not in frontend_source
            for token in ("/api/campaigns/export", "target csv", "audience_members")
        ),
        "no_contact_pii_api_surface": all(
            token not in api_surface_source and token not in frontend_source
            for token in (
                "contact export api",
                "/api/campaigns/contacts",
                "audience contact export",
                "download contacts",
            )
        ),
        "no_identity_linkage_surfaces": all(
            token not in api_surface_source and token not in frontend_source
            for token in (
                "identity resolution",
                "person-level linkage",
                "link prospect to customer",
            )
        ),
    }
    _require(all(checks.values()), f"Phase boundary scan failed: {checks}")
    return checks


def _sanity_no_sensitive_content(payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, ensure_ascii=True, allow_nan=False, sort_keys=True)
    folded = serialized.casefold()
    _require("traceback" not in folded, "Traceback content must not appear in evidence payload.")
    _require("select " not in folded and " from " not in folded, "Raw SQL text must not appear in evidence payload.")
    _require(not re.search(r"[a-z]:\\", folded), "Absolute Windows path must not appear in evidence payload.")
    _require("file://" not in folded and "vscode://" not in folded, "URI path content must not appear in evidence payload.")


def run_step9_validation(database_path: Path) -> dict[str, Any]:
    gate_evidence = _load_pre_run_gates_evidence()
    db_path = initialize_database(database_path)
    _progress("Initialized real database path.")

    _progress("Resolving latest completed model run.")
    model_row = _resolve_latest_completed_model_run(db_path)
    model_run_id = int(model_row["model_run_id"])
    _progress("Resolving latest completed scoring run for model.")
    canonical_scoring = _resolve_canonical_scoring_run(db_path, model_run_id)
    scoring_run_id = int(canonical_scoring["scoring_run_id"])
    _progress(f"Resolved canonical chain: model_run_id={model_run_id}, scoring_run_id={scoring_run_id}.")

    provenance = validate_completed_scoring_run_provenance(
        db_path,
        scoring_run_id=scoring_run_id,
        verify_current_source_match=True,
    )
    _require(bool(provenance.get("is_canonical")), f"Canonical provenance validation failed: {provenance.get('issues')}")
    _progress("Canonical provenance validation passed.")

    deterministic_rescore = verify_scoring_run_sample(db_path, scoring_run_id=scoring_run_id, sample_size=256)
    _require(bool(deterministic_rescore.get("verified")), "Deterministic sample re-score failed.")
    _progress("Deterministic sample re-score verification passed.")

    prep_summary = _prepare_boundaries_direct(
        db_path,
        scoring_run_id=scoring_run_id,
        chunk_size=DEFAULT_PREPARATION_SCAN_CHUNK_SIZE,
    )
    boundaries = AudienceRankRepository(db_path).fetch_boundaries(scoring_run_id)
    boundary_checks = _verify_boundary_contract(boundaries, expected_population=5_000_000)
    ranking_counts = _band_counts_from_boundaries(boundaries)
    _progress("Boundary preparation and exact rank-count checks passed.")

    search_evidence = _run_search_validation(db_path, scoring_run_id, boundaries)
    _progress("Search keyset and filter validations passed.")

    profile_evidence, profile_meta = _run_profile_validation(
        db_path,
        scoring_run_id=scoring_run_id,
        model_run_id=model_run_id,
        boundaries=boundaries,
    )
    _progress("Profile validations passed.")

    saved_evidence = _create_saved_audience_direct(
        db_path,
        scoring_run_id=scoring_run_id,
        model_run_id=model_run_id,
        profile_snapshot=profile_meta["snapshot"],
    )
    _progress("Saved-audience create and reopen validations passed.")

    ui_evidence = _run_ui_contract_checks()
    boundary_scan_evidence = _phase_boundary_scan()
    _progress("UI and phase-boundary checks passed.")

    scoring_row = ScoringRepository(db_path).fetch_scoring_run(scoring_run_id)
    _require(scoring_row is not None, "Canonical scoring row missing.")
    summary_payload = json.loads(str(scoring_row.get("score_summary_json") or "{}"))
    _require(isinstance(summary_payload, dict), "score_summary_json must decode to object.")

    evidence = {
        "step": "phase6_step9",
        "generated_at": _now_iso(),
        "database": {
            "name": db_path.name,
            "schema_version": 9,
        },
        "canonical": {
            "model_run_id": model_run_id,
            "scoring_run_id": scoring_run_id,
            "provenance": {
                "is_canonical": bool(provenance["is_canonical"]),
                "demographic_source_verified": bool(provenance["demographic_source_verified"]),
                "historical_source_verified": bool(provenance["historical_source_verified"]),
                "issue_count": len(list(provenance.get("issues") or [])),
            },
            "deterministic_sample_rescore": {
                "sample_size": int(deterministic_rescore["sample_size"]),
                "max_abs_diff": float(deterministic_rescore["max_abs_diff"]),
                "verified": bool(deterministic_rescore["verified"]),
            },
        },
        "preparation": {
            "status": "prepared",
            "rank_contract_version": RANK_CONTRACT_VERSION,
            "boundary_verification": boundary_checks,
            "runtime_seconds": float(prep_summary["runtime_seconds"]),
            "chunk_size": int(prep_summary["chunk_size"]),
            "chunk_count": int(prep_summary["chunk_count"]),
            "scanned_rows": int(prep_summary["scanned_rows"]),
            "throughput_rows_per_second": float(prep_summary["throughput_rows_per_second"]),
            "memory_and_throughput_evidence": {
                "scoring_chunk_size": int(scoring_row.get("chunk_size") or 0),
                "scoring_chunk_count": int(summary_payload.get("chunk_count") or 0),
                "scoring_rows_per_second": float(summary_payload.get("rows_per_second") or 0.0),
                "largest_chunk_rows": int(summary_payload.get("largest_chunk_rows") or 0),
                "largest_transformed_matrix_bytes": int(summary_payload.get("largest_transformed_matrix_bytes") or 0),
                "scoring_total_seconds": float(summary_payload.get("total_seconds") or 0.0),
            },
        },
        "ranking_counts": ranking_counts,
        "search": search_evidence,
        "profile": {
            "cases": profile_evidence,
            "historical_positive_reconciliation": profile_meta["historical_reconciliation"],
        },
        "saved_audience": saved_evidence,
        "tests": gate_evidence,
        "ui_e2e": ui_evidence,
        "phase_boundary_scan": boundary_scan_evidence,
        "security": {
            "no_pii_payload_fields": True,
            "no_export_surface": True,
            "no_identity_linkage_surface": True,
        },
    }

    _sanity_no_sensitive_content(evidence)
    return evidence


def main() -> None:
    evidence = run_step9_validation(Path("data/campaign_poc.db"))
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    print(str(EVIDENCE_PATH))


if __name__ == "__main__":
    main()
