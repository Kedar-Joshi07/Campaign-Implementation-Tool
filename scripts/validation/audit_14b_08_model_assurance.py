"""Bounded Stage08 audit; SQLite source is opened in read-only mode."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ml.feature_contract import ORDERED_FEATURES  # noqa: E402
from app.services.buyer_similarity_assurance_service import (  # noqa: E402
    evaluate_bounded_similarity_assurance,
)
from app.services.buyer_similarity_cohort_service import (  # noqa: E402
    build_product_buyer_cohorts,
)
from app.services.buyer_similarity_profile_service import (  # noqa: E402
    fit_buyer_similarity_profile,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("data/campaign_poc.db"))
    parser.add_argument("--product-catalog", type=Path, default=Path("data/product_master.csv"))
    parser.add_argument("--product-id", default="PRD001")
    parser.add_argument("--control-product-id", default="PRD010")
    parser.add_argument("--window-start", default="2024-01-01")
    parser.add_argument("--window-end", default="2025-12-31")
    parser.add_argument("--sample-size", type=int, default=256)
    args = parser.parse_args()
    if not 1 <= args.sample_size <= 1000:
        parser.error("Sample size must be from 1 to 1000.")
    cohort = build_product_buyer_cohorts(
        args.database, product_ids=[args.product_id],
        window_start=args.window_start, window_end=args.window_end,
        product_catalog_path=args.product_catalog,
    )
    profile = fit_buyer_similarity_profile(cohort, product_id=args.product_id)
    control_cohort = build_product_buyer_cohorts(
        args.database, product_ids=[args.control_product_id],
        window_start=args.window_start, window_end=args.window_end,
        product_catalog_path=args.product_catalog,
    )
    control_profile = fit_buyer_similarity_profile(
        control_cohort, product_id=args.control_product_id,
    )
    connection = sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    try:
        imports = {str(row["dataset_name"]): dict(row) for row in connection.execute(
            """SELECT dataset_name,import_id,source_checksum FROM data_import_runs r
               WHERE status='COMPLETED' AND dataset_name IN ('customers','campaign_sales','demographics')
                 AND import_id=(SELECT MAX(import_id) FROM data_import_runs newer
                                WHERE newer.dataset_name=r.dataset_name
                                  AND newer.status='COMPLETED')""")}
        source = cohort.manifest.source_identity
        if (int(imports["customers"]["import_id"]) != source.customer_import_id
            or str(imports["customers"]["source_checksum"]) != source.customer_source_checksum
            or int(imports["campaign_sales"]["import_id"]) != source.campaign_sales_import_id
            or str(imports["campaign_sales"]["source_checksum"]) != source.campaign_sales_source_checksum):
            raise RuntimeError("Cohort sources were replaced during bounded assurance.")
        columns = ",".join(ORDERED_FEATURES[1:])
        age = """CASE WHEN DATE(date_of_birth) IS NULL THEN NULL ELSE
            CAST(STRFTIME('%Y', ?) AS INTEGER) - CAST(SUBSTR(date_of_birth,1,4) AS INTEGER)
            - CASE WHEN STRFTIME('%m-%d', ?) < SUBSTR(date_of_birth,6,5)
                   THEN 1 ELSE 0 END END AS age"""
        broad_source = pd.read_sql_query(
            f"SELECT customer_id,{age},{columns} FROM customers ORDER BY customer_id LIMIT ?",
            connection, params=(args.window_end, args.window_end, args.sample_size),
        )
        prospect_source = pd.read_sql_query(
            f"SELECT person_id,{','.join(ORDERED_FEATURES)} FROM demographics ORDER BY person_id LIMIT ?",
            connection, params=(args.sample_size,),
        )
        broad = broad_source.loc[:, ORDERED_FEATURES]
        prospect = prospect_source.loc[:, ORDERED_FEATURES]
        report = evaluate_bounded_similarity_assurance(
            broad_training=broad, prospects=prospect, cohort=cohort, artifact=profile,
            broad_training_source_checksum=source.customer_source_checksum,
            prospect_source_checksum=str(imports["demographics"]["source_checksum"]),
            expected_prospect_source_checksum=str(imports["demographics"]["source_checksum"]),
            current_sources=True,
            unrelated_product_artifact=control_profile,
        )
        def identity_hash(values):
            encoded = json.dumps(sorted(str(value) for value in values),
                                 separators=(",", ":")).encode("utf-8")
            return hashlib.sha256(encoded).hexdigest()
        report["bounded_sample_identity"] = {
            "sampling_rule": "FIRST_N_IN_ASCENDING_SOURCE_IDENTIFIER_ORDER",
            "broad_customer_ids_sha256": identity_hash(broad_source["customer_id"]),
            "prospect_person_ids_sha256": identity_hash(prospect_source["person_id"]),
        }
        for dataset in ("customers", "campaign_sales", "demographics"):
            latest = connection.execute(
                "SELECT import_id,source_checksum FROM data_import_runs WHERE dataset_name=? AND status='COMPLETED' ORDER BY import_id DESC LIMIT 1",
                (dataset,),
            ).fetchone()
            if (int(latest["import_id"]) != int(imports[dataset]["import_id"])
                or str(latest["source_checksum"]) != str(imports[dataset]["source_checksum"])):
                raise RuntimeError(f"{dataset} source was replaced during bounded assurance.")
    finally:
        connection.close()
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
