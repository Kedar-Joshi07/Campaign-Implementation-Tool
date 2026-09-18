#!/usr/bin/env python3
"""Serve Step 20 against the canonical 5M database with real Phase 10 work."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8020)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    args = parser.parse_args()
    database_path = args.database.resolve()
    metrics_path = args.metrics.resolve()
    if not database_path.is_file():
        raise SystemExit(f"Canonical database does not exist: {database_path}")

    os.environ["DATABASE_PATH"] = str(database_path)
    os.environ["APP_ENV"] = "phase11-step20-full-5m-certification"

    from app.repositories.campaign_result_registry_repository import (
        CampaignResultRegistryRepository,
    )
    from app.services import (
        phase10_api_service,
        phase11_export_service,
        phase11_result_snapshot_service,
        phase11_search_orchestration_service,
        potential_customer_search_submission_service,
    )
    from app.services.phase11_result_snapshot_service import ResultSnapshotMaterializer

    phase10_api_service.DEFAULT_PROJECT_ROOT = PROJECT_ROOT
    phase11_export_service.DEFAULT_PROJECT_ROOT = PROJECT_ROOT
    phase11_result_snapshot_service.DEFAULT_PROJECT_ROOT = PROJECT_ROOT
    phase11_search_orchestration_service.DEFAULT_PROJECT_ROOT = PROJECT_ROOT

    metrics_lock = threading.Lock()
    workers: list[threading.Thread] = []
    metrics: dict[str, Any] = {
        "started_at": _utc_now(),
        "membership_source_calls": 0,
        "membership_rows_emitted": 0,
        "per_search": {},
    }

    def publish_metrics() -> None:
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = metrics_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(metrics_path)

    def counted_members(path: Path, run: dict[str, Any], generation: dict[str, Any]):
        run_id = str(run["search_run_id"])
        with metrics_lock:
            metrics["membership_source_calls"] += 1
            entry = metrics["per_search"].setdefault(run_id, {})
            entry["membership_source_called"] = True
            entry["membership_started_at"] = _utc_now()
            entry["membership_rows_emitted"] = 0
            publish_metrics()
        for member in phase11_search_orchestration_service.iter_selected_members(
            path, run, generation
        ):
            with metrics_lock:
                metrics["membership_rows_emitted"] += 1
                entry["membership_rows_emitted"] += 1
            yield member
        with metrics_lock:
            entry["membership_completed_at"] = _utc_now()
            publish_metrics()

    materializer = ResultSnapshotMaterializer(PROJECT_ROOT)

    def real_executor(database: Path, search_run_id: int) -> None:
        def worker() -> None:
            repository = CampaignResultRegistryRepository(database)
            run_key = str(search_run_id)
            with metrics_lock:
                metrics["per_search"][run_key] = {
                    "executor_started_at": _utc_now(),
                    "passes": 0,
                    "membership_source_called": False,
                    "membership_rows_emitted": 0,
                }
                publish_metrics()
            try:
                while True:
                    outcome = phase11_search_orchestration_service.execute_phase11_search_safely(
                        database,
                        search_run_id,
                        materializer=materializer,
                        project_root=PROJECT_ROOT,
                        membership_source=counted_members,
                    )
                    with metrics_lock:
                        entry = metrics["per_search"][run_key]
                        entry["passes"] += 1
                        entry["last_status"] = outcome.status
                        entry["last_waiting_on"] = outcome.waiting_on
                        entry["result_source"] = outcome.result_source
                        publish_metrics()
                    if outcome.status in {"COMPLETED", "BLOCKED", "FAILED"}:
                        break
                    time.sleep(max(1.0, args.poll_seconds))
            except Exception as exc:
                current = repository.fetch_search_run(search_run_id)
                if current and current["status"] in {"QUEUED", "PROCESSING"}:
                    repository.fail_search_run(search_run_id)
                with metrics_lock:
                    entry = metrics["per_search"][run_key]
                    entry["last_status"] = "FAILED"
                    entry["safe_exception_type"] = type(exc).__name__
                    publish_metrics()
                raise
            finally:
                with metrics_lock:
                    metrics["per_search"][run_key]["executor_completed_at"] = _utc_now()
                    publish_metrics()

        thread = threading.Thread(
            target=worker,
            name=f"phase11-step20-{search_run_id}",
            daemon=True,
        )
        workers.append(thread)
        thread.start()

    with metrics_lock:
        publish_metrics()
    potential_customer_search_submission_service.PHASE11_SEARCH_EXECUTOR = real_executor
    repository = CampaignResultRegistryRepository(database_path)
    resumable = repository.list_search_runs(status="PROCESSING", limit=100)
    resumable += repository.list_search_runs(
        status="QUEUED", limit=max(0, 100 - len(resumable))
    )
    for run in resumable:
        real_executor(database_path, int(run["search_run_id"]))

    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
