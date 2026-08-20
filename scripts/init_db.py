#!/usr/bin/env python3
"""Initialize or inspect the configured Phase 1 SQLite database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.schema import (  # noqa: E402
    format_inspection_report,
    initialize_database,
    inspect_database,
)
from app.logging_config import configure_logging  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or verify the Campaign Implementation POC SQLite schema."
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        help="Optional SQLite path; defaults to DATABASE_PATH configuration.",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Print tables, columns, indexes, and row counts after initialization.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()
    database_path = initialize_database(args.database_path)
    report = inspect_database(database_path)
    table_names = ", ".join(table["name"] for table in report["tables"])
    print(f"SQLite schema created/verified: {database_path}")
    print(f"Tables: {table_names}")

    if args.inspect:
        print()
        print(format_inspection_report(report))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

