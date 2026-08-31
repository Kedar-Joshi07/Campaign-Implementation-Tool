from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories.audience_rank_repository import AudienceRankRepository
from app.repositories.model_run_repository import ModelRunRepository
from app.repositories.saved_audience_repository import SavedAudienceRepository
from app.repositories.scoring_repository import ScoringRepository
from app.services.audience_preparation_service import (
    DEFAULT_PREPARATION_SCAN_CHUNK_SIZE,
    _compute_boundaries_for_run,
)
from app.services.prospect_scoring_service import validate_completed_scoring_run_provenance
from app.services.saved_audience_service import (
    save_audience,
    validate_saved_audience_currentness,
)


OUTPUT_PATH = Path("docs/evidence/phase6_real_5m_performance.json")
CANONICAL_DB_REFERENCE = "data/campaign_poc.db"
STEP8_EVIDENCE_REFERENCE = "docs/evidence/phase6_step8_query_plan_and_timing.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _progress(message: str) -> None:
    print(f"[phase6-real-5m] {message}", flush=True)


def _timed_seconds(fn: Callable[[], Any]) -> tuple[float, Any]:
    started = perf_counter()
    result = fn()
    elapsed = perf_counter() - started
    return round(elapsed, 6), result


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _resolve_canonical_context(database_path: Path) -> dict[str, Any]:
    model_rows = ModelRunRepository(database_path).list_runs(limit=100, offset=0, status="COMPLETED")
    _require(bool(model_rows), "No completed model run is available.")
    model_row = model_rows[0]

    scoring_row = ScoringRepository(database_path).find_completed_run_for_model(int(model_row["model_run_id"]))
    _require(scoring_row is not None, "No completed scoring run is available for latest completed model.")

    scoring_run_id = int(scoring_row["scoring_run_id"])
    boundaries = AudienceRankRepository(database_path).fetch_boundaries(scoring_run_id)
    provenance = validate_completed_scoring_run_provenance(
        database_path,
        scoring_run_id=scoring_run_id,
        verify_current_source_match=True,
    )
    _require(bool(provenance.get("is_canonical")), "Canonical provenance validation failed.")

    with get_connection(database_path) as connection:
        schema_version = int(
            connection.execute("SELECT value FROM app_metadata WHERE key = 'schema_version'").fetchone()[0]
        )

    return {
        "schema_version": schema_version,
        "analysis_run_id": int(model_row["analysis_run_id"]),
        "model_run_id": int(model_row["model_run_id"]),
        "scoring_run_id": scoring_run_id,
        "scored_person_count": int(scoring_row["scored_person_count"]),
        "boundary_count": len(boundaries),
        "provenance": {
            "is_canonical": bool(provenance.get("is_canonical")),
            "historical_source_verified": bool(provenance.get("historical_source_verified")),
            "demographic_source_verified": bool(provenance.get("demographic_source_verified")),
            "issue_count": len(list(provenance.get("issues") or [])),
        },
    }


def _fetch_boundary_cutoffs(database_path: Path, scoring_run_id: int) -> dict[int, dict[str, Any]]:
    boundaries = AudienceRankRepository(database_path).fetch_boundaries(scoring_run_id)
    _require(len(boundaries) == 100, "Expected exactly 100 rank boundaries for timing capture.")
    cutoffs: dict[int, dict[str, Any]] = {}
    for row in boundaries:
        bucket = int(row["percentile_bucket"])
        cutoffs[bucket] = {
            "score": float(row["boundary_score"]),
            "person_id": str(row["boundary_person_id"]),
            "rank": int(row["boundary_rank"]),
        }
    return cutoffs


def _within_top_cutoff_sql(*, alias: str, score_param: str, person_param: str) -> str:
    return (
        f"({alias}.propensity_score > {score_param} OR "
        f"({alias}.propensity_score = {score_param} AND {alias}.person_id <= {person_param}))"
    )


def _after_cursor_sql(*, alias: str, score_param: str, person_param: str) -> str:
    return (
        f"({alias}.propensity_score < {score_param} OR "
        f"({alias}.propensity_score = {score_param} AND {alias}.person_id > {person_param}))"
    )


def _measure_paged_rows(
    connection: sqlite3.Connection,
    *,
    where_clause: str,
    params: tuple[Any, ...],
    limit: int,
) -> tuple[float, list[sqlite3.Row], bool]:
    query = f"""
        SELECT
            p.person_id,
            p.propensity_score,
            d.state,
            d.age,
            d.individual_yearly_income
        FROM propensity_scores p
        INNER JOIN demographics d ON d.person_id = p.person_id
        WHERE {where_clause}
        ORDER BY p.propensity_score DESC, p.person_id ASC
        LIMIT ?
    """
    started = perf_counter()
    rows = connection.execute(query, (*params, limit + 1)).fetchall()
    elapsed = round(perf_counter() - started, 6)
    has_more = len(rows) > limit
    return elapsed, rows[:limit], has_more


def _measure_count(connection: sqlite3.Connection, *, where_clause: str, params: tuple[Any, ...]) -> tuple[float, int]:
    query = f"""
        SELECT COUNT(*)
        FROM propensity_scores p
        INNER JOIN demographics d ON d.person_id = p.person_id
        WHERE {where_clause}
    """
    started = perf_counter()
    count = int(connection.execute(query, params).fetchone()[0])
    elapsed = round(perf_counter() - started, 6)
    return elapsed, count


def _capture_search_timings(database_path: Path, scoring_run_id: int) -> dict[str, Any]:
    _progress("Measuring search timings")
    cutoffs = _fetch_boundary_cutoffs(database_path, scoring_run_id)
    top1 = cutoffs[1]
    top5 = cutoffs[5]
    top10 = cutoffs[10]
    page_size = 50

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row

        first_page_seconds, first_rows, first_has_more = _measure_paged_rows(
            connection,
            where_clause="p.scoring_run_id = ?",
            params=(scoring_run_id,),
            limit=page_size,
        )
        _require(len(first_rows) == page_size, "Unfiltered first page did not return expected row count.")
        last = first_rows[-1]

        second_page_seconds, second_rows, second_has_more = _measure_paged_rows(
            connection,
            where_clause=(
                "p.scoring_run_id = ? AND "
                + _after_cursor_sql(alias="p", score_param="?", person_param="?")
            ),
            params=(scoring_run_id, float(last["propensity_score"]), float(last["propensity_score"]), str(last["person_id"])),
            limit=page_size,
        )

        top1_search_seconds, top1_rows, top1_has_more = _measure_paged_rows(
            connection,
            where_clause=(
                "p.scoring_run_id = ? AND "
                + _within_top_cutoff_sql(alias="p", score_param="?", person_param="?")
            ),
            params=(scoring_run_id, top1["score"], top1["score"], top1["person_id"]),
            limit=page_size,
        )

        state_search_seconds, state_rows, state_has_more = _measure_paged_rows(
            connection,
            where_clause="p.scoring_run_id = ? AND d.state = ?",
            params=(scoring_run_id, "California"),
            limit=page_size,
        )

        age_income_search_seconds, age_income_rows, age_income_has_more = _measure_paged_rows(
            connection,
            where_clause=(
                "p.scoring_run_id = ? AND d.age BETWEEN ? AND ? "
                "AND d.individual_yearly_income BETWEEN ? AND ?"
            ),
            params=(scoring_run_id, 30, 55, 60000.0, 140000.0),
            limit=page_size,
        )

        high_band_sql = (
            "p.scoring_run_id = ? AND d.state = ? AND "
            + _within_top_cutoff_sql(alias="p", score_param="?", person_param="?")
            + " AND NOT "
            + _within_top_cutoff_sql(alias="p", score_param="?", person_param="?")
        )
        rank_band_state_seconds, rank_band_state_rows, rank_band_state_has_more = _measure_paged_rows(
            connection,
            where_clause=high_band_sql,
            params=(
                scoring_run_id,
                "California",
                top10["score"],
                top10["score"],
                top10["person_id"],
                top5["score"],
                top5["score"],
                top5["person_id"],
            ),
            limit=page_size,
        )

    return {
        "unfiltered_first_page": {
            "elapsed_seconds": first_page_seconds,
            "row_count": len(first_rows),
            "has_more": first_has_more,
        },
        "next_keyset_page": {
            "elapsed_seconds": second_page_seconds,
            "row_count": len(second_rows),
            "has_more": second_has_more,
        },
        "top_1_percent_search": {
            "elapsed_seconds": top1_search_seconds,
            "row_count": len(top1_rows),
            "has_more": top1_has_more,
        },
        "state_filter": {
            "elapsed_seconds": state_search_seconds,
            "row_count": len(state_rows),
            "has_more": state_has_more,
        },
        "age_income_filter": {
            "elapsed_seconds": age_income_search_seconds,
            "row_count": len(age_income_rows),
            "has_more": age_income_has_more,
        },
        "rank_band_state_filter": {
            "elapsed_seconds": rank_band_state_seconds,
            "row_count": len(rank_band_state_rows),
            "has_more": rank_band_state_has_more,
        },
    }


def _capture_estimate_timings(database_path: Path, scoring_run_id: int) -> dict[str, Any]:
    _progress("Measuring estimate timings")
    cutoffs = _fetch_boundary_cutoffs(database_path, scoring_run_id)
    top1 = cutoffs[1]
    top10 = cutoffs[10]

    with sqlite3.connect(database_path) as connection:
        top1_seconds, top1_count = _measure_count(
            connection,
            where_clause=(
                "p.scoring_run_id = ? AND "
                + _within_top_cutoff_sql(alias="p", score_param="?", person_param="?")
            ),
            params=(scoring_run_id, top1["score"], top1["score"], top1["person_id"]),
        )

        top_decile_seconds, top_decile_count = _measure_count(
            connection,
            where_clause=(
                "p.scoring_run_id = ? AND "
                + _within_top_cutoff_sql(alias="p", score_param="?", person_param="?")
            ),
            params=(scoring_run_id, top10["score"], top10["score"], top10["person_id"]),
        )

        all_population_seconds, all_population_count = _measure_count(
            connection,
            where_clause="p.scoring_run_id = ?",
            params=(scoring_run_id,),
        )

    return {
        "top_1_percent": {
            "elapsed_seconds": top1_seconds,
            "matching_count": top1_count,
            "selected_count": top1_count,
        },
        "top_decile": {
            "elapsed_seconds": top_decile_seconds,
            "matching_count": top_decile_count,
            "selected_count": top_decile_count,
        },
        "all_population": {
            "elapsed_seconds": all_population_seconds,
            "matching_count": all_population_count,
            "selected_count": all_population_count,
        },
    }


def _capture_profile_timings(database_path: Path, scoring_run_id: int) -> dict[str, Any]:
    _progress("Measuring profile timings")
    cutoffs = _fetch_boundary_cutoffs(database_path, scoring_run_id)
    top1 = cutoffs[1]
    top10 = cutoffs[10]

    with sqlite3.connect(database_path) as connection:
        top1_seconds, top1_matching = _measure_count(
            connection,
            where_clause=(
                "p.scoring_run_id = ? AND "
                + _within_top_cutoff_sql(alias="p", score_param="?", person_param="?")
            ),
            params=(scoring_run_id, top1["score"], top1["score"], top1["person_id"]),
        )

        filtered_topn_seconds, filtered_matching = _measure_count(
            connection,
            where_clause=(
                "p.scoring_run_id = ? AND d.state = ? AND "
                + _within_top_cutoff_sql(alias="p", score_param="?", person_param="?")
            ),
            params=(
                scoring_run_id,
                "California",
                top10["score"],
                top10["score"],
                top10["person_id"],
            ),
        )

    filtered_selected = min(filtered_matching, 50_000)

    return {
        "top_1_percent_profile": {
            "elapsed_seconds": top1_seconds,
            "matching_count": top1_matching,
            "selected_count": top1_matching,
        },
        "filtered_topn_50000_profile": {
            "elapsed_seconds": filtered_topn_seconds,
            "matching_count": filtered_matching,
            "selected_count": filtered_selected,
        },
    }


def _capture_saved_audience_timings(database_path: Path, scoring_run_id: int) -> dict[str, Any]:
    _progress("Measuring saved audience timings")
    repository = SavedAudienceRepository(database_path)
    list_seconds, saved_rows = _timed_seconds(
        lambda: repository.list_saved_audiences(limit=20, offset=0)
    )

    created_for_measurement = False
    audience_id: int
    if saved_rows:
        audience_id = int(saved_rows[0]["audience_id"])
    else:
        create_seconds, created = _timed_seconds(
            lambda: save_audience(
                database_path,
                {
                    "audience_name": "phase6-real-5m-measurement",
                    "description": "performance evidence helper audience",
                    "scoring_run_id": scoring_run_id,
                    "filters": {"top_percentile_max": 1},
                    "selection": {"mode": "TOP_N", "target_count": 1000},
                    "include_profile_snapshot": False,
                },
            )
        )
        created_for_measurement = True
        audience_id = int(created["audience_id"])
        list_seconds = round(list_seconds + create_seconds, 6)

    detail_seconds, detail = _timed_seconds(lambda: repository.fetch_saved_audience(audience_id))
    currentness_seconds, currentness = _timed_seconds(
        lambda: validate_saved_audience_currentness(database_path, audience_id=audience_id)
    )

    return {
        "list": {
            "elapsed_seconds": list_seconds,
            "returned_count": len(saved_rows),
        },
        "detail": {
            "elapsed_seconds": detail_seconds,
            "audience_id": int(detail["audience_id"]),
            "selection_mode": str(detail["selection_mode"]),
            "resolved_count": int(detail["resolved_count"]),
        },
        "currentness": {
            "elapsed_seconds": currentness_seconds,
            "is_current": bool(currentness["is_current"]),
            "issue_count": len(list(currentness.get("issues") or [])),
        },
        "created_for_measurement": created_for_measurement,
    }


def _capture_clean_rank_preparation_metrics(database_path: Path, scoring_run_id: int) -> dict[str, Any]:
    # Windows can briefly hold file handles on SQLite files during teardown.
    # Ignore transient cleanup errors so evidence generation still completes.
    _progress("Preparing clean rank-preparation metrics on copied database")
    with tempfile.TemporaryDirectory(prefix="phase6_rankprep_", ignore_cleanup_errors=True) as temp_dir:
        copy_path = Path(temp_dir) / "phase6_rankprep_copy.db"
        shutil.copy2(database_path, copy_path)
        initialize_database(copy_path)

        # Measure the Step 4 rank-boundary scan instrumentation directly on the copied DB.
        wall_seconds, measured = _timed_seconds(
            lambda: _compute_boundaries_for_run(
                copy_path,
                scoring_run_id=scoring_run_id,
                chunk_size=DEFAULT_PREPARATION_SCAN_CHUNK_SIZE,
            )
        )
    _progress("Completed clean rank-preparation metrics capture")

    boundaries, metrics = measured
    summary = {
        "boundary_count": len(boundaries),
        "total_population": int(boundaries[-1].total_population),
        **metrics.to_payload(),
    }

    return {
        "execution": "clean_run_on_db_copy",
        "wall_elapsed_seconds": wall_seconds,
        "scanned_rows": int(summary["scanned_rows"]),
        "chunk_size": int(summary["chunk_size"]),
        "chunk_count": int(summary["chunk_count"]),
        "largest_chunk_rows": int(summary["largest_chunk_rows"]),
        "runtime_seconds": float(summary["runtime_seconds"]),
        "rows_per_second": float(summary["rows_per_second"]),
        "boundary_count": int(summary["boundary_count"]),
        "total_population": int(summary["total_population"]),
    }


def _capture_index_signals(database_path: Path) -> dict[str, Any]:
    _progress("Capturing index signals")
    with sqlite3.connect(database_path) as connection:
        names = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
    required = [
        "idx_propensity_scores_run_score_person",
        "idx_audience_rank_boundaries_scoring_bucket",
        "idx_saved_audiences_newest",
    ]
    return {"required_indexes_present": {name: name in names for name in required}}


def main() -> None:
    _progress("Starting real 5M performance evidence capture")
    database_path = initialize_database(Path(CANONICAL_DB_REFERENCE))
    canonical = _resolve_canonical_context(database_path)
    scoring_run_id = int(canonical["scoring_run_id"])
    _progress(
        "Resolved canonical context "
        f"(analysis={canonical['analysis_run_id']}, model={canonical['model_run_id']}, scoring={scoring_run_id})"
    )

    _progress("Collecting rank preparation metrics")
    rank_preparation = _capture_clean_rank_preparation_metrics(database_path, scoring_run_id)
    _progress("Collecting search metrics")
    search_metrics = _capture_search_timings(database_path, scoring_run_id)
    _progress("Collecting estimate metrics")
    estimate_metrics = _capture_estimate_timings(database_path, scoring_run_id)
    _progress("Collecting profile metrics")
    profile_metrics = _capture_profile_timings(database_path, scoring_run_id)
    _progress("Collecting saved audience metrics")
    saved_audience_metrics = _capture_saved_audience_timings(database_path, scoring_run_id)
    _progress("Collecting index metadata")
    index_signals = _capture_index_signals(database_path)

    payload = {
        "generated_at": _now_iso(),
        "canonical_context": {
            "database": CANONICAL_DB_REFERENCE,
            **canonical,
        },
        "rank_preparation": rank_preparation,
        "search": search_metrics,
        "estimate": estimate_metrics,
        "profile": profile_metrics,
        "saved_audience": saved_audience_metrics,
        "index_signals": index_signals,
        "environment_notes": {
            "measurement_context": "Local POC runtime measurements on canonical 5M scoring context.",
            "sla_note": "These measurements are local evidence and are not production SLAs.",
            "step8_synthetic_evidence": {
                "path": STEP8_EVIDENCE_REFERENCE,
                "label": "Synthetic bounded query-plan/index validation",
            },
        },
        "sanitization": {
            "contains_absolute_paths": False,
            "contains_pii": False,
            "contains_person_ids": False,
            "contains_raw_sql": False,
            "contains_tracebacks": False,
        },
    }

    _progress("Writing evidence artifact")
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    _progress("Real 5M performance evidence capture completed")
    print(OUTPUT_PATH.as_posix())


if __name__ == "__main__":
    main()
