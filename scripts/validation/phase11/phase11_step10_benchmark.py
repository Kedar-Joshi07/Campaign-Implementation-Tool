"""Read-only Phase 11 Step 10 benchmark of the current Phase 6 Audience Engine.

The helper never prepares intelligence, creates indexes, or writes application
rows.  It refuses stale/non-canonical generations and records repeated local
service timings without asserting an invented SLA.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.audience_query_service import (  # noqa: E402
    AudienceQueryServiceError,
    estimate_audience,
    get_audience_filter_options,
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_only_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _candidates(path: Path) -> list[dict[str, Any]]:
    with _read_only_connection(path) as connection:
        rows = connection.execute(
            """
            SELECT g.generation_id, g.scoring_run_id, g.generation_status,
                   g.lifecycle_state, g.modeling_context_sha256,
                   g.intelligence_key_sha256, g.created_at, g.last_verified_at,
                   s.status AS scoring_status, s.scored_person_count
            FROM phase10_intelligence_generations g
            JOIN scoring_runs s ON s.scoring_run_id = g.scoring_run_id
            WHERE g.generation_status = 'READY'
              AND g.lifecycle_state IN ('CURRENT', 'REUSABLE', 'PROTECTED')
              AND s.status = 'COMPLETED'
            ORDER BY CASE g.lifecycle_state WHEN 'CURRENT' THEN 0 WHEN 'PROTECTED' THEN 1 ELSE 2 END,
                     g.created_at DESC, g.generation_id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _database_state(path: Path) -> dict[str, Any]:
    with _read_only_connection(path) as connection:
        scalar = lambda sql: connection.execute(sql).fetchone()[0]
        active_jobs = [dict(row) for row in connection.execute(
            "SELECT job_id,job_type,status,stage FROM jobs WHERE status IN ('QUEUED','RUNNING') ORDER BY job_id"
        )]
        active_orchestrations = [dict(row) for row in connection.execute(
            "SELECT orchestration_id,status,stage FROM phase10_orchestration_runs WHERE status IN ('QUEUED','RUNNING') ORDER BY orchestration_id"
        )]
        indexes = [dict(row) for row in connection.execute(
            """
            SELECT name, tbl_name, sql FROM sqlite_master
            WHERE type='index' AND (tbl_name='demographics' OR tbl_name='propensity_scores')
            ORDER BY tbl_name,name
            """
        )]
        return {
            "schema_version": str(scalar("SELECT value FROM app_metadata WHERE key='schema_version'")),
            "database_bytes": path.stat().st_size,
            "sqlite_page_size": int(scalar("PRAGMA page_size")),
            "sqlite_page_count": int(scalar("PRAGMA page_count")),
            "demographic_rows": int(scalar("SELECT COUNT(*) FROM demographics")),
            "propensity_score_rows": int(scalar("SELECT COUNT(*) FROM propensity_scores")),
            "active_jobs": active_jobs,
            "active_phase10_orchestrations": active_orchestrations,
            "relevant_indexes": indexes,
        }


def _values(options: dict[str, Any], field: str) -> list[str]:
    raw = options["categorical_options"].get(field, [])
    values = []
    for item in raw:
        value = item.get("value") if isinstance(item, dict) else item
        if isinstance(value, str) and value and value != "Unknown/Other":
            values.append(value)
    return values


def _timed(repetitions: int, operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    samples = []
    result = None
    signature = None
    for repetition in range(1, repetitions + 1):
        started = time.perf_counter()
        result = operation()
        elapsed = time.perf_counter() - started
        samples.append(elapsed)
        current = {
            key: result.get(key)
            for key in ("matching_count", "selected_count", "has_more")
            if key in result
        }
        current["row_count"] = len(result.get("rows", []))
        if signature is None:
            signature = current
        elif current != signature:
            raise RuntimeError("Repeated benchmark output changed.")
        print(f"  repetition {repetition}/{repetitions}: {elapsed:.6f}s", flush=True)
    assert result is not None and signature is not None
    return {
        "repetitions": repetitions,
        "seconds": [round(value, 6) for value in samples],
        "p50_like_median_seconds": round(statistics.median(samples), 6),
        "minimum_seconds": round(min(samples), 6),
        "maximum_seconds": round(max(samples), 6),
        "stable_result": signature,
    }


def _cases(
    database_path: Path,
    scoring_run_id: int,
    options: dict[str, Any],
) -> list[tuple[str, Callable[[], dict[str, Any]], dict[str, Any]]]:
    states = _values(options, "state")
    if len(states) < 5:
        raise RuntimeError("Current snapshot does not expose five States for representative benchmarking.")
    advanced = {}
    for field in ("marital_status", "education", "employment_status", "resident_status", "resident_type", "type_of_employment"):
        values = _values(options, field)
        if values:
            advanced[field] = [values[0]]
    score_minimum = max(
        float(options["score_summary"]["score_min"]),
        min(0.7, float(options["score_summary"]["score_max"])),
    )
    definitions = [
        ("score_threshold_no_demographics", {"score_min": score_minimum}, "ALL_MATCHING", None),
        ("one_state", {"state": states[:1]}, "ALL_MATCHING", None),
        ("five_states", {"state": states[:5]}, "ALL_MATCHING", None),
        ("age_income_bucket", {"age_min": 25, "age_max": 34, "individual_yearly_income_min": 50000, "individual_yearly_income_max": 74999}, "ALL_MATCHING", None),
        ("multi_age_multi_income_states", {"age_min": 18, "age_max": 44, "individual_yearly_income_min": 25000, "individual_yearly_income_max": 99999, "state": states[:5]}, "ALL_MATCHING", None),
        ("advanced_demographics", advanced, "ALL_MATCHING", None),
    ]
    cases = []
    for name, filters, mode, target in definitions:
        request = {"scoring_run_id": scoring_run_id, "filters": filters,
                   "selection": {"mode": mode, "target_count": target}}
        cases.append((name, lambda request=request: estimate_audience(database_path, request), request))
    top_request = {
        "scoring_run_id": scoring_run_id,
        "filters": {"state": states[:5]},
        "selection": {"mode": "TOP_N", "target_count": 100},
    }
    cases.append(
        (
            "top_n_100",
            lambda: estimate_audience(database_path, top_request),
            top_request,
        )
    )
    return cases


def main() -> int:
    path = (PROJECT_ROOT / ARGS.database).resolve()
    output = (PROJECT_ROOT / ARGS.output).resolve()
    report: dict[str, Any] = {
        "contract": "phase11-step10-atomic-segment-benchmark-v1",
        "generated_at": _timestamp(),
        "database": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "repetitions": ARGS.repetitions,
        "database_state": _database_state(path),
        "candidate_generations": _candidates(path),
        "benchmark_status": "NOT_STARTED",
        "timings": {},
    }
    if report["database_state"]["active_jobs"] or report["database_state"]["active_phase10_orchestrations"]:
        report.update(benchmark_status="REFUSED_ACTIVE_WORK", reason="Active canonical work was detected.")
    else:
        chosen = None
        rejected = []
        for candidate in report["candidate_generations"]:
            try:
                options = get_audience_filter_options(path, scoring_run_id=int(candidate["scoring_run_id"]))
            except AudienceQueryServiceError as exc:
                rejected.append({"generation_id": candidate["generation_id"], "reason": str(exc)})
                continue
            if int(options["population_count"]) != int(candidate["scored_person_count"]):
                rejected.append({"generation_id": candidate["generation_id"], "reason": "Population count mismatch."})
                continue
            chosen = (candidate, options)
            break
        report["rejected_candidates"] = rejected
        if chosen is None:
            report.update(
                benchmark_status="REFUSED_NO_CURRENT_GENERATION",
                reason="No READY generation passed the existing Audience Engine currentness gates.",
            )
        else:
            candidate, options = chosen
            report["selected_generation"] = candidate
            report["benchmark_status"] = "RUNNING"
            for name, operation, request in _cases(
                path,
                int(candidate["scoring_run_id"]),
                options,
            ):
                print(f"Benchmarking {name}", flush=True)
                report["timings"][name] = {"request": request, **_timed(ARGS.repetitions, operation)}
            report["benchmark_status"] = "COMPLETED"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {output.relative_to(PROJECT_ROOT)}", flush=True)
    print(f"Status: {report['benchmark_status']}", flush=True)
    return 0 if report["benchmark_status"] == "COMPLETED" else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="data/campaign_poc.db")
    parser.add_argument("--output", default="docs/evidence/phase11/10_atomic_segment_benchmark.json")
    parser.add_argument("--repetitions", type=int, default=3, choices=range(3, 11))
    ARGS = parser.parse_args()
    raise SystemExit(main())
