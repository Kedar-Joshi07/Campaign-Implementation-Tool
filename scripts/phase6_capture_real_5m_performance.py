from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.schema import initialize_database
from app.repositories.audience_rank_repository import AudienceRankRepository
from app.repositories.model_run_repository import ModelRunRepository
from app.repositories.scoring_repository import ScoringRepository
from app.services.audience_preparation_service import (
    DEFAULT_PREPARATION_SCAN_CHUNK_SIZE,
    get_audience_preparation_status,
    list_audience_preparation_runs,
    _compute_boundaries_for_run,
)
from app.services.audience_query_service import (
    estimate_audience,
    get_audience_filter_options,
    profile_audience,
    search_audience,
)
from app.services.prospect_scoring_service import (
    find_current_canonical_run_for_model_lightweight,
    validate_completed_scoring_run_integrity_deep,
)
from app.services.saved_audience_service import (
    get_saved_audience_detail,
    list_saved_audiences,
    save_audience,
    validate_saved_audience_currentness,
)
from app.services.model_api_service import (
    get_scoring_status,
    get_scoring_run_detail,
)


OUTPUT_PATH = Path("docs/evidence/phase6_final_analytics_performance.json")
CANONICAL_DB_REFERENCE = "data/campaign_poc.db"
BASELINE_EVIDENCE_REFERENCE = "docs/evidence/phase6_real_5m_performance.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _progress(message: str) -> None:
    print(f"[phase6-real-5m-service] {message}", flush=True)


def _timed_call(fn: Callable[[], Any]) -> tuple[float, Any]:
    started = perf_counter()
    value = fn()
    elapsed = perf_counter() - started
    return round(elapsed, 6), value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _resolve_canonical_context(database_path: Path) -> dict[str, Any]:
    with sqlite3.connect(database_path) as connection:
        schema_version = int(
            connection.execute("SELECT value FROM app_metadata WHERE key = 'schema_version'").fetchone()[0]
        )

    model_rows = ModelRunRepository(database_path).list_runs(limit=100, offset=0, status="COMPLETED")
    _require(bool(model_rows), "No completed model run is available.")

    model_row = model_rows[0]
    model_run_id = int(model_row["model_run_id"])
    analysis_run_id = int(model_row["analysis_run_id"])

    canonical_row = find_current_canonical_run_for_model_lightweight(
        database_path,
        model_run_id=model_run_id,
    )
    _require(canonical_row is not None, "No canonical completed scoring run is available.")

    scoring_run_id = int(canonical_row["scoring_run_id"])
    scoring_row = ScoringRepository(database_path).fetch_scoring_run(scoring_run_id)
    _require(scoring_row is not None, "Canonical scoring run could not be loaded.")

    deep_provenance = validate_completed_scoring_run_integrity_deep(
        database_path,
        scoring_run_id=scoring_run_id,
        verify_current_source_match=True,
    )
    _require(bool(deep_provenance.get("is_canonical")), "Deep canonical integrity validation failed.")

    boundaries = AudienceRankRepository(database_path).fetch_boundaries(scoring_run_id)
    _require(len(boundaries) == 100, "Expected exactly 100 prepared rank boundaries.")

    return {
        "schema_version": schema_version,
        "analysis_run_id": analysis_run_id,
        "model_run_id": model_run_id,
        "scoring_run_id": scoring_run_id,
        "scored_person_count": int(scoring_row["scored_person_count"]),
        "boundary_count": len(boundaries),
    }


def _ensure_measurement_audience_id(database_path: Path, scoring_run_id: int) -> int:
    existing = list_saved_audiences(
        database_path,
        limit=20,
        offset=0,
        scoring_run_id=scoring_run_id,
    )
    if existing:
        return int(existing[0]["audience_id"])

    created = save_audience(
        database_path,
        {
            "audience_name": "phase6-service-measurement",
            "description": "performance evidence helper audience",
            "scoring_run_id": scoring_run_id,
            "filters": {"top_percentile_max": 1},
            "selection": {"mode": "TOP_N", "target_count": 1000},
            "include_profile_snapshot": False,
        },
    )
    return int(created["audience_id"])


def _capture_service_timings(database_path: Path, scoring_run_id: int) -> dict[str, Any]:
    _progress("Capturing service timings")
    timings: dict[str, Any] = {}

    def capture(label: str, fn: Callable[[], Any]) -> tuple[float, Any]:
        _progress(f"service start: {label}")
        stop_event = threading.Event()

        def _heartbeat() -> None:
            waited = 0
            while not stop_event.wait(15.0):
                waited += 15
                _progress(f"service heartbeat: {label} (+{waited}s)")

        thread = threading.Thread(target=_heartbeat, daemon=True)
        thread.start()
        try:
            elapsed_seconds, payload = _timed_call(fn)
        finally:
            stop_event.set()
            thread.join(timeout=0.2)
        _progress(f"service done: {label} ({elapsed_seconds:.3f}s)")
        return elapsed_seconds, payload

    audience_id = _ensure_measurement_audience_id(database_path, scoring_run_id)

    elapsed, payload = capture(
        "audience_preparation_status",
        lambda: get_audience_preparation_status(database_path, scoring_run_id=scoring_run_id)
    )
    timings["audience_preparation_status"] = {
        "elapsed_seconds": elapsed,
        "ready_for_current_audience_actions": bool(payload["ready_for_current_audience_actions"]),
        "is_canonical": bool(payload["is_canonical"]),
        "source_verified": bool(payload["source_verified"]),
        "boundary_count": int(payload["boundary_count"]),
    }

    elapsed, payload = capture(
        "audience_run_list",
        lambda: list_audience_preparation_runs(database_path, limit=20, offset=0)
    )
    timings["audience_run_list"] = {
        "elapsed_seconds": elapsed,
        "row_count": len(payload),
    }

    elapsed, payload = capture(
        "get_audience_filter_options",
        lambda: get_audience_filter_options(database_path, scoring_run_id=scoring_run_id)
    )
    timings["get_audience_filter_options"] = {
        "elapsed_seconds": elapsed,
        "population_count": int(payload["population_count"]),
    }

    elapsed, payload = capture(
        "estimate_all",
        lambda: estimate_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {},
                "selection": {"mode": "ALL_MATCHING"},
            },
        )
    )
    timings["estimate_all"] = {
        "elapsed_seconds": elapsed,
        "matching_count": int(payload["matching_count"]),
        "selected_count": int(payload["selected_count"]),
    }

    elapsed, payload = capture(
        "estimate_top_1_percent",
        lambda: estimate_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {"top_percentile_max": 1},
                "selection": {"mode": "ALL_MATCHING"},
            },
        )
    )
    timings["estimate_top_1_percent"] = {
        "elapsed_seconds": elapsed,
        "matching_count": int(payload["matching_count"]),
        "selected_count": int(payload["selected_count"]),
    }

    elapsed, payload = capture(
        "estimate_top_decile",
        lambda: estimate_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {"deciles": [1]},
                "selection": {"mode": "ALL_MATCHING"},
            },
        )
    )
    timings["estimate_top_decile"] = {
        "elapsed_seconds": elapsed,
        "matching_count": int(payload["matching_count"]),
        "selected_count": int(payload["selected_count"]),
    }

    elapsed, payload = capture(
        "estimate_state_filter",
        lambda: estimate_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {"state": ["California"]},
                "selection": {"mode": "ALL_MATCHING"},
            },
        )
    )
    timings["estimate_state_filter"] = {
        "elapsed_seconds": elapsed,
        "matching_count": int(payload["matching_count"]),
        "selected_count": int(payload["selected_count"]),
    }

    elapsed, payload = capture(
        "estimate_age_income_filter",
        lambda: estimate_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {
                    "age_min": 30,
                    "age_max": 55,
                    "individual_yearly_income_min": 60000,
                    "individual_yearly_income_max": 140000,
                },
                "selection": {"mode": "ALL_MATCHING"},
            },
        )
    )
    timings["estimate_age_income_filter"] = {
        "elapsed_seconds": elapsed,
        "matching_count": int(payload["matching_count"]),
        "selected_count": int(payload["selected_count"]),
    }

    elapsed, payload = capture(
        "estimate_rank_and_state_filter",
        lambda: estimate_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {"top_percentile_max": 10, "state": ["California"]},
                "selection": {"mode": "ALL_MATCHING"},
            },
        )
    )
    timings["estimate_rank_and_state_filter"] = {
        "elapsed_seconds": elapsed,
        "matching_count": int(payload["matching_count"]),
        "selected_count": int(payload["selected_count"]),
    }
    elapsed, payload = capture(
        "profile_no_filter_all_matching",
        lambda: profile_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {},
                "selection": {"mode": "ALL_MATCHING"},
            },
        )
    )
    timings["profile_no_filter_all_matching"] = {
        "elapsed_seconds": elapsed,
        "selected_count": int(payload["summary"]["selected"]["count"]),
    }


    elapsed, first_page = capture(
        "search_first_page_unfiltered",
        lambda: search_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {},
                "page_size": 50,
            },
        )
    )
    timings["search_first_page_unfiltered"] = {
        "elapsed_seconds": elapsed,
        "row_count": len(first_page["rows"]),
        "has_more": bool(first_page["has_more"]),
    }

    if first_page.get("next_cursor"):
        elapsed, second_page = capture(
            "search_next_keyset_page",
            lambda: search_audience(
                database_path,
                {
                    "scoring_run_id": scoring_run_id,
                    "filters": {},
                    "page_size": 50,
                    "cursor": first_page["next_cursor"],
                },
            )
        )
        timings["search_next_keyset_page"] = {
            "elapsed_seconds": elapsed,
            "row_count": len(second_page["rows"]),
            "has_more": bool(second_page["has_more"]),
        }

    elapsed, payload = capture(
        "search_state_filter",
        lambda: search_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {"state": ["California"]},
                "page_size": 50,
            },
        )
    )
    timings["search_state_filter"] = {
        "elapsed_seconds": elapsed,
        "row_count": len(payload["rows"]),
        "has_more": bool(payload["has_more"]),
    }

    elapsed, payload = capture(
        "search_age_income_filter",
        lambda: search_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {
                    "age_min": 30,
                    "age_max": 55,
                    "individual_yearly_income_min": 60000,
                    "individual_yearly_income_max": 140000,
                },
                "page_size": 50,
            },
        )
    )
    timings["search_age_income_filter"] = {
        "elapsed_seconds": elapsed,
        "row_count": len(payload["rows"]),
        "has_more": bool(payload["has_more"]),
    }

    elapsed, payload = capture(
        "search_top_1_percent",
        lambda: search_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {"top_percentile_max": 1},
                "page_size": 50,
            },
        )
    )
    timings["search_top_1_percent"] = {
        "elapsed_seconds": elapsed,
        "row_count": len(payload["rows"]),
        "has_more": bool(payload["has_more"]),
    }

    elapsed, payload = capture(
        "profile_top_1_percent",
        lambda: profile_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {"top_percentile_max": 1},
                "selection": {"mode": "ALL_MATCHING"},
            },
        )
    )
    timings["profile_top_1_percent"] = {
        "elapsed_seconds": elapsed,
        "selected_count": int(payload["summary"]["selected"]["count"]),
    }

    elapsed, payload = capture(
        "profile_filtered_top_n_50000",
        lambda: profile_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {"state": ["California"]},
                "selection": {"mode": "TOP_N", "target_count": 50000},
            },
        )
    )
    timings["profile_filtered_top_n_50000"] = {
        "elapsed_seconds": elapsed,
        "selected_count": int(payload["summary"]["selected"]["count"]),
    }

    elapsed, payload = capture(
        "profile_filtered_all_matching",
        lambda: profile_audience(
            database_path,
            {
                "scoring_run_id": scoring_run_id,
                "filters": {"state": ["California"]},
                "selection": {"mode": "ALL_MATCHING"},
            },
        )
    )
    timings["profile_filtered_all_matching"] = {
        "elapsed_seconds": elapsed,
        "selected_count": int(payload["summary"]["selected"]["count"]),
    }

    elapsed, payload = capture(
        "save_audience_without_profile",
        lambda: save_audience(
            database_path,
            {
                "audience_name": "phase6-benchmark-save-no-profile",
                "description": "step10 timing no profile",
                "scoring_run_id": scoring_run_id,
                "filters": {"top_percentile_max": 1},
                "selection": {"mode": "TOP_N", "target_count": 1000},
                "include_profile_snapshot": False,
            },
        )
    )
    timings["save_audience_without_profile"] = {
        "elapsed_seconds": elapsed,
        "audience_id": int(payload["audience_id"]),
        "resolved_count": int(payload["definition"]["resolved_count"]),
    }

    elapsed, payload = capture(
        "save_audience_with_profile",
        lambda: save_audience(
            database_path,
            {
                "audience_name": "phase6-benchmark-save-with-profile",
                "description": "step10 timing with profile",
                "scoring_run_id": scoring_run_id,
                "filters": {"state": ["California"]},
                "selection": {"mode": "TOP_N", "target_count": 50000},
                "include_profile_snapshot": True,
            },
        )
    )
    timings["save_audience_with_profile"] = {
        "elapsed_seconds": elapsed,
        "audience_id": int(payload["audience_id"]),
        "resolved_count": int(payload["definition"]["resolved_count"]),
    }

    elapsed, payload = capture(
        "list_saved_audiences",
        lambda: list_saved_audiences(database_path, limit=20, offset=0)
    )
    timings["list_saved_audiences"] = {
        "elapsed_seconds": elapsed,
        "row_count": len(payload),
    }

    elapsed, payload = capture(
        "get_saved_audience_detail",
        lambda: get_saved_audience_detail(database_path, audience_id=audience_id)
    )
    timings["get_saved_audience_detail"] = {
        "elapsed_seconds": elapsed,
        "audience_id": int(payload["audience_id"]),
        "is_current": bool(payload["currentness"]["is_current"]),
    }

    elapsed, payload = capture(
        "validate_saved_audience_currentness",
        lambda: validate_saved_audience_currentness(database_path, audience_id=audience_id)
    )
    timings["validate_saved_audience_currentness"] = {
        "elapsed_seconds": elapsed,
        "audience_id": int(payload["audience_id"]),
        "is_current": bool(payload["is_current"]),
        "issue_count": len(payload["issues"]),
    }

    model_row = ModelRunRepository(database_path).list_runs(limit=1, offset=0, status="COMPLETED")[0]
    model_run_id = int(model_row["model_run_id"])

    elapsed, payload = capture(
        "get_scoring_status",
        lambda: get_scoring_status(database_path, model_run_id),
    )
    timings["get_scoring_status"] = {
        "elapsed_seconds": elapsed,
        "model_run_id": model_run_id,
        "scoring_run_id": payload.get("scoring_run_id"),
        "eligible": bool(payload.get("eligible")),
    }

    elapsed, payload = capture(
        "get_scoring_run_detail",
        lambda: get_scoring_run_detail(database_path, scoring_run_id),
    )
    score_summary = payload.get("score_summary") if isinstance(payload, dict) else {}
    timings["get_scoring_run_detail"] = {
        "elapsed_seconds": elapsed,
        "scoring_run_id": int(payload.get("scoring_run_id", scoring_run_id)),
        "demographic_source_verified": bool(
            isinstance(score_summary, dict) and score_summary.get("demographic_source_verified")
        ),
    }

    return timings


def _capture_sql_query_timings(database_path: Path, scoring_run_id: int) -> dict[str, Any]:
    _progress("Capturing SQL query timings")
    timings: dict[str, Any] = {}

    with sqlite3.connect(database_path) as connection:
        boundaries = connection.execute(
            """
            SELECT percentile_bucket, boundary_score, boundary_person_id
            FROM audience_rank_boundaries
            WHERE scoring_run_id = ?
            ORDER BY percentile_bucket ASC
            """,
            (scoring_run_id,),
        ).fetchall()
        top1_score, top1_person = boundaries[0][1], boundaries[0][2]

        started = perf_counter()
        run_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM propensity_scores WHERE scoring_run_id = ?",
                (scoring_run_id,),
            ).fetchone()[0]
        )
        timings["run_score_count"] = {
            "elapsed_seconds": round(perf_counter() - started, 6),
            "count": run_count,
        }

        started = perf_counter()
        joined_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM propensity_scores p
                INNER JOIN demographics d ON d.person_id = p.person_id
                WHERE p.scoring_run_id = ?
                """,
                (scoring_run_id,),
            ).fetchone()[0]
        )
        timings["run_demographics_join_count"] = {
            "elapsed_seconds": round(perf_counter() - started, 6),
            "count": joined_count,
        }

        started = perf_counter()
        top1_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM propensity_scores
                WHERE scoring_run_id = ?
                  AND (
                    propensity_score > ?
                    OR (propensity_score = ? AND person_id <= ?)
                  )
                """,
                (scoring_run_id, top1_score, top1_score, top1_person),
            ).fetchone()[0]
        )
        timings["run_top_1_percent_count"] = {
            "elapsed_seconds": round(perf_counter() - started, 6),
            "count": top1_count,
        }

    return timings


def _capture_rank_preparation_metrics(database_path: Path, scoring_run_id: int) -> dict[str, Any]:
    _progress("Capturing rank preparation metrics on copied DB")
    with tempfile.TemporaryDirectory(prefix="phase6_rankprep_", ignore_cleanup_errors=True) as temp_dir:
        copy_path = Path(temp_dir) / "phase6_rankprep_copy.db"
        shutil.copy2(database_path, copy_path)
        initialize_database(copy_path)

        elapsed, measured = _timed_call(
            lambda: _compute_boundaries_for_run(
                copy_path,
                scoring_run_id=scoring_run_id,
                chunk_size=DEFAULT_PREPARATION_SCAN_CHUNK_SIZE,
            )
        )

    boundaries, metrics, _bucket_payload = measured
    return {
        "execution": "clean_run_on_db_copy",
        "wall_elapsed_seconds": elapsed,
        "scanned_rows": int(metrics.scanned_rows),
        "chunk_size": int(metrics.chunk_size),
        "chunk_count": int(metrics.chunk_count),
        "largest_chunk_rows": int(metrics.largest_chunk_rows),
        "runtime_seconds": float(metrics.runtime_seconds),
        "rows_per_second": float(metrics.rows_per_second),
        "boundary_count": int(len(boundaries)),
        "total_population": int(boundaries[-1].total_population),
    }


def main() -> None:
    _progress("Starting Phase 6 real service performance capture")
    database_path = initialize_database(Path(CANONICAL_DB_REFERENCE))
    canonical = _resolve_canonical_context(database_path)
    scoring_run_id = int(canonical["scoring_run_id"])

    _progress(
        "Resolved canonical context "
        f"(analysis={canonical['analysis_run_id']}, model={canonical['model_run_id']}, scoring={scoring_run_id})"
    )

    service_timings = _capture_service_timings(database_path, scoring_run_id)
    sql_query_timings = _capture_sql_query_timings(database_path, scoring_run_id)
    rank_preparation_metrics = _capture_rank_preparation_metrics(database_path, scoring_run_id)

    payload = {
        "generated_at": _now_iso(),
        "canonical_context": {
            "database": CANONICAL_DB_REFERENCE,
            **canonical,
        },
        "service_timings": service_timings,
        "sql_query_timings": sql_query_timings,
        "rank_preparation_metrics": rank_preparation_metrics,
        "evidence_references": {
            "baseline_pre_fix": BASELINE_EVIDENCE_REFERENCE,
        },
        "sanitization": {
            "contains_absolute_paths": False,
            "contains_pii": False,
            "contains_person_ids": False,
            "contains_raw_sql": False,
            "contains_tracebacks": False,
        },
    }

    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    _progress("Wrote service performance evidence")
    print(OUTPUT_PATH.as_posix())


if __name__ == "__main__":
    main()
