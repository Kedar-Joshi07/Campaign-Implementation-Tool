"""Publish a governed calibrated probability generation for an existing score run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.schema import initialize_database  # noqa: E402
from app.services.propensity_calibration_service import (  # noqa: E402
    publish_calibrated_generation,
)
from app.services.targeting_option_catalog_service import (  # noqa: E402
    get_or_build_targeting_catalog,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="data/campaign_poc.db")
    parser.add_argument("--scoring-run-id", type=int, required=True)
    parser.add_argument("--batch-size", type=int, default=50_000)
    args = parser.parse_args()

    database_path = (ROOT / args.database).resolve()
    print(f"[1/3] Migrating {database_path} to the current schema...", flush=True)
    initialize_database(database_path)
    print("[2/3] Building or reusing the targeting-option catalog...", flush=True)
    catalog = get_or_build_targeting_catalog(database_path)
    print(
        json.dumps(
            {
                "catalog_version": catalog["catalog_version"],
                "catalog_created_at": catalog["catalog_created_at"],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    print(
        f"[3/3] Publishing calibrated scores for scoring run "
        f"{args.scoring_run_id}...",
        flush=True,
    )
    result = publish_calibrated_generation(
        database_path,
        args.scoring_run_id,
        batch_size=args.batch_size,
    )
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
