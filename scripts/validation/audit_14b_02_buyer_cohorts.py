"""Read-only Stage 14B_02 source and exact product-support audit."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.services.buyer_similarity_cohort_service import (  # noqa: E402
    audit_buyer_similarity_sources,
    build_product_buyer_cohorts,
)


def _product_ids(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return sorted(
            {
                str(row["product_id"]).strip()
                for row in csv.DictReader(handle)
                if str(row.get("product_id") or "").strip()
            }
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("data/campaign_poc.db"))
    parser.add_argument("--product-catalog", type=Path, default=Path("data/product_master.csv"))
    parser.add_argument("--window-start", default="2024-01-01")
    parser.add_argument("--window-end", default="2025-12-31")
    args = parser.parse_args()

    source_audit = audit_buyer_similarity_sources(
        args.database,
        product_catalog_path=args.product_catalog,
    )
    build = build_product_buyer_cohorts(
        args.database,
        product_ids=_product_ids(args.product_catalog),
        window_start=args.window_start,
        window_end=args.window_end,
        product_catalog_path=args.product_catalog,
    )
    split_counts = build.frame.groupby("customer_id")["split"].nunique()
    fit = set(build.frame.loc[build.frame["split"] == "FIT", "customer_id"])
    holdout = set(
        build.frame.loc[build.frame["split"] == "HOLDOUT", "customer_id"]
    )
    checks = {
        "source_audit_passed": source_audit["status"] == "PASS",
        "product_customer_rows_unique": not build.frame.duplicated(
            subset=["product_id", "customer_id"]
        ).any(),
        "one_union_split_per_customer": bool((split_counts <= 1).all()),
        "fit_holdout_disjoint": fit.isdisjoint(holdout),
        "support_rows_reconcile": len(build.frame)
        == sum(
            value.distinct_attributed_buyers
            for value in build.manifest.product_support
        ),
        "no_customer_ids_in_public_manifest": "customer_id" not in json.dumps(
            build.manifest.public_payload(), sort_keys=True
        ),
    }
    report = {
        "audit_contract": "LOOKALIKE_V3_STAGE_02_CANONICAL_AUDIT_V1",
        "database": str(args.database).replace("\\", "/"),
        "database_open_mode": "READ_ONLY",
        "window_start": args.window_start,
        "window_end": args.window_end,
        "source_audit": source_audit,
        "cohort_manifest": build.manifest.public_payload(),
        "checks": checks,
        "status": "PASS" if all(checks.values()) else "FAIL",
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
