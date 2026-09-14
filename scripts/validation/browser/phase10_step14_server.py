#!/usr/bin/env python3
"""Serve the app against the isolated Step 14 fixture with bounded controls."""

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
    parser.add_argument("--port", type=int, default=8014)
    args = parser.parse_args()
    runtime_root = args.root.resolve()
    database_path = runtime_root / "phase10-cleanroom.db"
    if not database_path.is_file():
        raise SystemExit(f"Fixture database does not exist: {database_path}")

    os.environ["DATABASE_PATH"] = str(database_path)
    os.environ["APP_ENV"] = "phase10-step14-certification"

    from app.services import phase10_api_service
    from app.services.phase10_orchestration_service import run_phase10_orchestration

    phase10_api_service.DEFAULT_PROJECT_ROOT = runtime_root
    workers: list[threading.Thread] = []

    def controlled_submitter(database: str | Path, orchestration_id: int, root: str | Path | None):
        failure_marker = runtime_root / "fail-next-submission"
        if failure_marker.exists():
            failure_marker.unlink()
            raise RuntimeError("Step14ControlledSubmissionFailure")

        def worker() -> None:
            # Keep QUEUED observable long enough for browser progress and reconnect checks.
            time.sleep(2.0)
            run_phase10_orchestration(
                database,
                orchestration_id,
                project_root=runtime_root,
                artifact_root=Path("artifacts/models"),
                scoring_chunk_size=1_000,
                rank_chunk_size=1_000,
            )

        thread = threading.Thread(target=worker, name=f"phase10-step14-{orchestration_id}", daemon=True)
        workers.append(thread)
        thread.start()
        return thread

    phase10_api_service.PHASE10_API_SUBMITTER = controlled_submitter

    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
