#!/usr/bin/env python3
"""Serve Phase 11 against an isolated bounded Step 19 runtime."""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8019)
    parser.add_argument("--delay-seconds", type=float, default=1.25)
    args = parser.parse_args()
    runtime_root = args.root.resolve()
    database_path = runtime_root / "phase11-cleanroom.db"
    if not database_path.is_file():
        raise SystemExit(f"Fixture database does not exist: {database_path}")

    os.environ["DATABASE_PATH"] = str(database_path)
    os.environ["APP_ENV"] = "phase11-step19-certification"

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
    from scripts.validation.run_phase11_bounded_cleanroom import _Executor

    # All artifacts and validation reads remain inside the disposable runtime.
    phase10_api_service.DEFAULT_PROJECT_ROOT = runtime_root
    phase11_export_service.DEFAULT_PROJECT_ROOT = runtime_root
    phase11_result_snapshot_service.DEFAULT_PROJECT_ROOT = runtime_root
    phase11_search_orchestration_service.DEFAULT_PROJECT_ROOT = runtime_root

    executor = _Executor(runtime_root)
    workers: list[threading.Thread] = []

    def controlled_executor(database: Path, search_run_id: int) -> None:
        def worker() -> None:
            time.sleep(max(0.0, args.delay_seconds))
            try:
                executor(database, search_run_id)
            except Exception:
                repository = CampaignResultRegistryRepository(database)
                current = repository.fetch_search_run(search_run_id)
                if current and current["status"] in {"QUEUED", "PROCESSING"}:
                    repository.fail_search_run(search_run_id)

        thread = threading.Thread(
            target=worker,
            name=f"phase11-step19-{search_run_id}",
            daemon=True,
        )
        workers.append(thread)
        thread.start()

    potential_customer_search_submission_service.PHASE11_SEARCH_EXECUTOR = (
        controlled_executor
    )

    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
