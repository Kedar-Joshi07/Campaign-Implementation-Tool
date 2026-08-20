#!/usr/bin/env python3
"""Import campaign-sales history into SQLite."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.logging_config import configure_logging  # noqa: E402
from app.services.data_import_service import (  # noqa: E402
    DataImportError,
    import_campaign_sales,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import campaign-sales CSV/CSV.GZ data")
    parser.add_argument("--file", type=Path, required=True, help="Campaign-sales CSV or CSV.GZ file")
    parser.add_argument("--database-path", type=Path, help="Optional SQLite database path")
    parser.add_argument("--replace", action="store_true", help="Explicitly replace campaign rows")
    parser.add_argument("--batch-size", type=int, default=10_000)
    parser.add_argument("--progress-every", type=int, default=50_000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()
    try:
        result = import_campaign_sales(
            args.file,
            database_path=args.database_path,
            replace=args.replace,
            batch_size=args.batch_size,
            progress_every=args.progress_every,
        )
    except DataImportError as exc:
        print(f"Campaign-sales import failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"Campaign-sales import completed | import_id={result.import_id} "
        f"rows={result.rows_inserted:,} rejected={result.rows_rejected:,} "
        f"seconds={result.duration_seconds:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

