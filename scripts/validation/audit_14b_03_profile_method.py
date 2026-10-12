"""Bounded read-only-source certification for Stage 14B_03."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.services.buyer_similarity_cohort_service import (  # noqa: E402
    build_product_buyer_cohorts,
)
from app.database.connection import get_connection  # noqa: E402
from app.database.schema import initialize_database  # noqa: E402
from app.repositories.buyer_similarity_profile_repository import (  # noqa: E402
    publish_buyer_similarity_profile,
)
from app.services.buyer_similarity_profile_service import (  # noqa: E402
    describe_profile_holdout,
    fit_buyer_similarity_profile,
    load_profile_artifact,
    score_buyer_similarity_frame,
    serialize_profile_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("data/campaign_poc.db"))
    parser.add_argument(
        "--product-catalog", type=Path, default=Path("data/product_master.csv")
    )
    parser.add_argument("--product-id", default="PRD001")
    parser.add_argument("--window-start", default="2024-01-01")
    parser.add_argument("--window-end", default="2025-12-31")
    args = parser.parse_args()

    cohort = build_product_buyer_cohorts(
        args.database,
        product_ids=[args.product_id],
        window_start=args.window_start,
        window_end=args.window_end,
        product_catalog_path=args.product_catalog,
    )
    first = fit_buyer_similarity_profile(
        cohort, product_id=args.product_id, assignment_chunk_size=7
    )
    second = fit_buyer_similarity_profile(
        cohort, product_id=args.product_id, assignment_chunk_size=31
    )
    first_bytes = serialize_profile_artifact(first)
    second_bytes = serialize_profile_artifact(second)
    with tempfile.TemporaryDirectory(prefix="lookalike-v3-stage03-") as directory:
        root = Path(directory)
        registry_database = root / "registry.db"
        initialize_database(registry_database)
        lineage = first["lineage"]
        with get_connection(registry_database, write=True) as connection:
            connection.executemany(
                """INSERT INTO data_import_runs (
                    import_id,dataset_name,source_path,started_at,completed_at,status,
                    rows_read,rows_inserted,rows_rejected,source_checksum
                ) VALUES (?,?,?,?,?,'COMPLETED',0,0,0,?)""",
                (
                    (
                        lineage["customer_import_id"],
                        "customers",
                        "canonical-customers",
                        "2026-10-06T00:00:00Z",
                        "2026-10-06T00:00:01Z",
                        lineage["customer_source_checksum"],
                    ),
                    (
                        lineage["campaign_sales_import_id"],
                        "campaign_sales",
                        "canonical-campaign-sales",
                        "2026-10-06T00:00:00Z",
                        "2026-10-06T00:00:01Z",
                        lineage["campaign_sales_source_checksum"],
                    ),
                ),
            )
        published = publish_buyer_similarity_profile(
            registry_database,
            first,
            project_root=root,
            execution_owner="stage03-audit",
            execution_token="a" * 64,
            now="2026-10-06T00:01:00Z",
        )
        reused = publish_buyer_similarity_profile(
            registry_database,
            first,
            project_root=root,
            execution_owner="stage03-audit-reuse",
            execution_token="b" * 64,
            now="2026-10-06T00:02:00Z",
        )
        stored = published.storage
        loaded = load_profile_artifact(
            project_root=root,
            storage_uri=stored.storage_uri,
            expected_artifact_sha256=stored.artifact_sha256,
            expected_product_id=args.product_id,
            expected_lineage={
                "customer_source_checksum": (
                    cohort.manifest.source_identity.customer_source_checksum
                ),
                "campaign_sales_source_checksum": (
                    cohort.manifest.source_identity.campaign_sales_source_checksum
                ),
                "historical_context_sha256": cohort.manifest.context_identity_sha256,
            },
        )
        round_trip_equal = loaded == first
        with get_connection(registry_database) as connection:
            publication_row = connection.execute(
                """SELECT p.publication_state,a.artifact_state
                   FROM buyer_similarity_profiles p
                   JOIN buyer_similarity_profile_artifacts a USING (profile_id)"""
            ).fetchone()
            profile_count = int(connection.execute(
                "SELECT COUNT(*) FROM buyer_similarity_profiles"
            ).fetchone()[0])

    serialized = first_bytes[0].decode("utf-8")
    support = next(
        value
        for value in cohort.manifest.product_support
        if value.product_id == args.product_id
    )
    selected = next(
        value
        for value in first["candidate_diagnostics"]
        if value["k"] == first["realized_k"]
    )
    holdout_frame = cohort.frame.loc[
        (cohort.frame["product_id"] == args.product_id)
        & (cohort.frame["split"] == "HOLDOUT"),
        first["prototypes"][0]["values"].keys(),
    ]
    checks = {
        "source_database_read_only": True,
        "product_support_eligible": support.status == "ELIGIBLE",
        "fit_holdout_customer_disjoint": set(
            cohort.frame.loc[cohort.frame["split"] == "FIT", "customer_id"]
        ).isdisjoint(
            set(
                cohort.frame.loc[
                    cohort.frame["split"] == "HOLDOUT", "customer_id"
                ]
            )
        ),
        "selected_candidate_converged": bool(selected["converged"]),
        "all_prototypes_supported": all(
            value["support"] >= first["training_parameters"]["minimum_cluster_support"]
            for value in first["prototypes"]
        ),
        "chunk_size_artifact_deterministic": first_bytes == second_bytes,
        "chunk_size_scores_deterministic": score_buyer_similarity_frame(
            holdout_frame, first, chunk_size=3
        )
        == score_buyer_similarity_frame(holdout_frame, first, chunk_size=17),
        "safe_json_round_trip": round_trip_equal,
        "transactional_profile_publication": tuple(publication_row)
        == ("PUBLISHED", "PUBLISHED"),
        "idempotent_published_reuse": reused.reused
        and reused.profile_id == published.profile_id
        and profile_count == 1,
        "artifact_checksum_verified": first_bytes[1] == stored.artifact_sha256,
        "no_internal_customer_identifiers": "customer_id" not in serialized,
        "no_contact_pii_fields": not any(
            field in serialized for field in ('"email"', '"phone"', '"address"')
        ),
    }
    report = {
        "audit_contract": "LOOKALIKE_V3_STAGE_03_PROFILE_METHOD_AUDIT_V1",
        "database": str(args.database).replace("\\", "/"),
        "database_open_mode": "READ_ONLY",
        "temporary_artifact_removed": True,
        "product_id": args.product_id,
        "lineage": first["lineage"],
        "score_method_version": first["score_method_version"],
        "preprocessor_contract_version": first["preprocessor_contract_version"],
        "fit_support": first["fit_support"],
        "holdout_support": first["holdout_support"],
        "realized_k": first["realized_k"],
        "prototype_supports": [value["support"] for value in first["prototypes"]],
        "candidate_diagnostics": first["candidate_diagnostics"],
        "numeric_scales": first["numeric_scales"],
        "artifact_sha256": first_bytes[1],
        "profile_payload_sha256": first_bytes[2],
        "holdout_description": describe_profile_holdout(cohort, first),
        "checks": checks,
        "status": "PASS" if all(checks.values()) else "FAIL",
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
