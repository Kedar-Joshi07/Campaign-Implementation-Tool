#!/usr/bin/env python3
"""Import one or more demographic CSV/CSV.GZ parts into SQLite."""

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
    import_demographics,
    resolve_demographic_sources,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import demographic CSV/CSV.GZ data")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--file",
        dest="files",
        type=Path,
        action="append",
        help="Demographic file; repeat for multiple parts",
    )
    source_group.add_argument("--input-dir", type=Path, help="Directory containing demographic parts")
    parser.add_argument("--pattern", default="*.csv.gz", help="Pattern used with --input-dir")
    parser.add_argument("--database-path", type=Path, help="Optional SQLite database path")
    parser.add_argument("--replace", action="store_true", help="Explicitly replace demographic rows")
    parser.add_argument("--batch-size", type=int, default=10_000)
    parser.add_argument("--progress-every", type=int, default=50_000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()
    try:
        source_files = resolve_demographic_sources(
            files=args.files,
            input_dir=args.input_dir,
            pattern=args.pattern,
        )
        result = import_demographics(
            source_files,
            database_path=args.database_path,
            replace=args.replace,
            batch_size=args.batch_size,
            progress_every=args.progress_every,
        )
    except DataImportError as exc:
        print(f"Demographic import failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"Demographic import completed | import_id={result.import_id} "
        f"files={len(result.source_paths)} rows={result.rows_inserted:,} "
        f"rejected={result.rows_rejected:,} seconds={result.duration_seconds:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

