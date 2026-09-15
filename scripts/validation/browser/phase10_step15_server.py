#!/usr/bin/env python3
"""Serve Step 15 against its isolated full-scale runtime without mocked jobs."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8015)
    args = parser.parse_args()
    runtime_root = args.root.resolve()
    database_path = runtime_root / "runtime.db"
    if not database_path.is_file():
        raise SystemExit(f"Step 15 database does not exist: {database_path}")

    os.environ["DATABASE_PATH"] = str(database_path)
    os.environ["APP_ENV"] = "phase10-step15-certification"

    from app.services import phase10_api_service

    phase10_api_service.DEFAULT_PROJECT_ROOT = runtime_root

    import app.main

    app.main.PROJECT_ROOT = runtime_root

    import uvicorn

    uvicorn.run(app.main.app, host="127.0.0.1", port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
