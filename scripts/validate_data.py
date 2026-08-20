"""Create required indexes and reconcile imported Phase 1 data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.schema import initialize_required_indexes, verify_required_indexes
from app.logging_config import configure_logging
from app.services.data_reconciliation_service import (
    STATUS_ERROR,
    format_reconciliation_report,
    run_reconciliation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create required indexes and reconcile the Phase 1 SQLite datasets."
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=None,
        help="SQLite database path (defaults to DATABASE_PATH).",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging()
    index_timings = initialize_required_indexes(args.database_path)
    result = run_reconciliation(args.database_path)
    index_status = verify_required_indexes(args.database_path)
    result["indexes"] = {
        name: {"exists": exists, "creation_seconds": round(index_timings[name], 6)}
        for name, exists in index_status.items()
    }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_reconciliation_report(result))
        print(f"Required indexes: {sum(index_status.values())}/{len(index_status)} present")

    return 1 if result["overall_status"] == STATUS_ERROR else 0


if __name__ == "__main__":
    raise SystemExit(main())
