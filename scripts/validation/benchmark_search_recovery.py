"""Read-only canonical performance certification for search recovery reads.

Submission acknowledgement and new materialization intentionally remain outside
this read-only benchmark because the approved scenario gate forbids creating a
nonqualifying search merely to obtain a timing sample.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.connection import get_connection  # noqa: E402
from app.repositories.campaign_result_registry_repository import (  # noqa: E402
    CampaignResultRegistryRepository,
)
from app.repositories.phase10_intelligence_repository import (  # noqa: E402
    Phase10IntelligenceRepository,
)
from app.services.phase11_result_snapshot_service import (  # noqa: E402
    validate_result_snapshot,
)
from app.services.phase11_results_service import (  # noqa: E402
    get_result_detail,
    list_result_history,
)
from app.services.potential_customer_search_submission_service import (  # noqa: E402
    search_form_options,
)


DEFAULT_DATABASE = PROJECT_ROOT / "data" / "campaign_poc.db"
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "demo_readiness"
    / "POTENTIAL_CUSTOMER_SEARCH_RECOVERY_PERFORMANCE.json"
)


def _measure(function: Callable[[], Any], repetitions: int) -> tuple[Any, dict[str, float]]:
    samples: list[float] = []
    value: Any = None
    for _ in range(repetitions):
        started = time.perf_counter()
        value = function()
        samples.append(time.perf_counter() - started)
    return value, {
        "minimum_seconds": min(samples),
        "median_seconds": statistics.median(samples),
        "maximum_seconds": max(samples),
    }


def _current_snapshot(database_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    with get_connection(database_path) as connection:
        row = connection.execute(
            """SELECT r.search_run_id,r.result_snapshot_id,r.generation_id
               FROM campaign_search_runs AS r
               JOIN campaign_result_snapshots AS s
                 ON s.result_snapshot_id=r.result_snapshot_id
               WHERE r.status='COMPLETED' AND s.currentness_state='CURRENT'
               ORDER BY r.search_run_id DESC LIMIT 1"""
        ).fetchone()
    if row is None:
        raise RuntimeError("No completed current result snapshot is available.")
    run = CampaignResultRegistryRepository(database_path).fetch_search_run(
        int(row["search_run_id"])
    )
    snapshot = CampaignResultRegistryRepository(database_path).fetch_snapshot(
        int(row["result_snapshot_id"])
    )
    generation = Phase10IntelligenceRepository(database_path).fetch_generation(
        int(row["generation_id"])
    )
    if run is None or snapshot is None or generation is None:
        raise RuntimeError("Current result lineage is incomplete.")
    return run, snapshot, generation


def benchmark(database_path: Path, *, repetitions: int) -> dict[str, Any]:
    if repetitions < 1:
        raise ValueError("repetitions must be positive")

    # Warm catalog/schema and projection paths before measuring warm responses.
    search_form_options(database_path)
    history = list_result_history(database_path, limit=20)
    if not history:
        raise RuntimeError("Search history is empty.")
    detail_run_id = int(history[0]["search_run_id"])
    get_result_detail(database_path, detail_run_id, project_root=PROJECT_ROOT)

    options, options_timing = _measure(
        lambda: search_form_options(database_path), repetitions
    )
    history, history_timing = _measure(
        lambda: list_result_history(database_path, limit=20), repetitions
    )
    detail, detail_timing = _measure(
        lambda: get_result_detail(
            database_path, detail_run_id, project_root=PROJECT_ROOT
        ),
        repetitions,
    )

    run, snapshot, generation = _current_snapshot(database_path)
    cache_key = str(snapshot["result_cache_key_sha256"])
    repository = CampaignResultRegistryRepository(database_path)
    reuse, reuse_timing = _measure(
        lambda: repository.find_snapshot_by_cache_key(cache_key), repetitions
    )
    validation, validation_timing = _measure(
        lambda: validate_result_snapshot(
            snapshot,
            run,
            generation,
            cache_key,
            project_root=PROJECT_ROOT,
        ),
        repetitions,
    )

    budgets = {
        "targeting_options": 2.0,
        "results_history": 2.0,
        "status_detail": 0.5,
        "exact_reuse_lookup": 0.5,
        "snapshot_validation": 2.0,
    }
    measurements = {
        "targeting_options": options_timing,
        "results_history": history_timing,
        "status_detail": detail_timing,
        "exact_reuse_lookup": reuse_timing,
        "snapshot_validation": validation_timing,
    }
    checks = {
        name: measurement["maximum_seconds"] < budgets[name]
        for name, measurement in measurements.items()
    }
    return {
        "database": str(database_path),
        "repetitions": repetitions,
        "read_only": True,
        "measurements": measurements,
        "budgets_seconds": budgets,
        "checks": checks,
        "all_executed_checks_passed": all(checks.values()),
        "observed": {
            "catalog_version": options["catalog_version"],
            "history_count": len(history),
            "detail_search_run_id": detail["search_run_id"],
            "reuse_snapshot_id": reuse["result_snapshot_id"] if reuse else None,
            "snapshot_valid": validation.is_valid,
            "snapshot_row_count": validation.row_count,
        },
        "not_executed": {
            "search_creation_acknowledgement": (
                "Requires creating a search; blocked while zero scenarios meet the "
                "approved 10,000-customer qualification gate."
            ),
            "new_result_materialization": (
                "Requires executing a qualifying new search; exact reuse lookup and "
                "immutable snapshot validation were measured instead."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()

    payload = benchmark(args.database.resolve(), repetitions=args.repetitions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["all_executed_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
