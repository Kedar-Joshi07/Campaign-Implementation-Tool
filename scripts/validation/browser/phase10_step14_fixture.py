#!/usr/bin/env python3
"""Create and control the isolated Phase 10 system-browser certification fixture."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.connection import get_connection
from scripts.validation.run_phase10_bounded_cleanroom import (
    _apply_demographic_refresh,
    _create_context,
    _prepare_inline,
    _seed_fresh_database,
)


def _paths(root: Path) -> tuple[Path, Path]:
    return root, root / "phase10-cleanroom.db"


def initialize(root: Path) -> dict[str, object]:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    database_path = _seed_fresh_database(root)
    seed_context_id = _create_context(database_path, "P1", "EMAIL")
    start = _prepare_inline(database_path, seed_context_id, root)
    if start.orchestration["status"] != "READY":
        raise RuntimeError("The reusable READY seed generation was not created.")
    return snapshot(root) | {
        "seed_context_id": seed_context_id,
        "seed_generation_id": int(start.orchestration["generation_id"]),
    }


def refresh_demographics(root: Path) -> dict[str, object]:
    _, database_path = _paths(root)
    with get_connection(database_path) as connection:
        current_count = int(connection.execute("SELECT COUNT(*) FROM demographics").fetchone()[0])
    _apply_demographic_refresh(
        database_path,
        root,
        count=current_count + 1,
        version=8,
    )
    return snapshot(root)


def arm_failure(root: Path) -> dict[str, object]:
    marker = root / "fail-next-submission"
    marker.touch(exist_ok=True)
    return {"failure_armed": True, "marker": str(marker)}


def snapshot(root: Path) -> dict[str, object]:
    _, database_path = _paths(root)
    with get_connection(database_path) as connection:
        counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "campaign_targeting_contexts",
                "historical_analysis_runs",
                "model_runs",
                "scoring_runs",
                "phase10_intelligence_generations",
                "phase10_orchestration_runs",
            )
        }
        latest = [
            dict(row)
            for row in connection.execute(
                """
                SELECT orchestration_id, targeting_context_id, status, stage,
                       progress_percent, reuse_plan_json, analysis_run_id,
                       model_run_id, scoring_run_id, generation_id,
                       technical_message, safe_error_message
                FROM phase10_orchestration_runs
                ORDER BY orchestration_id
                """
            ).fetchall()
        ]
    return {
        "database_path": str(database_path),
        "counts": counts,
        "orchestrations": latest,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("init", "refresh-demographics", "arm-failure", "snapshot"))
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "init":
        result = initialize(args.root)
    elif args.action == "refresh-demographics":
        result = refresh_demographics(args.root)
    elif args.action == "arm-failure":
        result = arm_failure(args.root)
    else:
        result = snapshot(args.root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
