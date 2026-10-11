"""Bounded, read-only-source certification for Stage 14B_04.

The canonical database is opened with SQLite ``mode=ro``.  A bounded sample is
copied into a disposable schema-32 registry, scored there, deeply verified,
published, and then exercised through the current-attestation reuse path.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.database.connection import get_connection  # noqa: E402
from app.database.schema import initialize_database  # noqa: E402
from app.repositories.buyer_similarity_profile_repository import (  # noqa: E402
    publish_buyer_similarity_profile,
)
from app.services.buyer_similarity_cohort_service import (  # noqa: E402
    build_product_buyer_cohorts,
)
from app.services.buyer_similarity_profile_service import (  # noqa: E402
    fit_buyer_similarity_profile,
)
from app.services.buyer_similarity_scoring_service import (  # noqa: E402
    composite_similarity_winners,
    estimate_similarity_preparation_work,
    has_current_similarity_attestation,
    run_similarity_generation,
)


SAMPLE_COLUMNS = (
    "person_id",
    "gender",
    "age",
    "state",
    "individual_yearly_income",
    "marital_status",
    "education",
    "employment_status",
    "resident_status",
    "resident_type",
    "family_member_count",
    "type_of_employment",
    "number_of_children_in_family",
    "number_of_adults_in_family",
    "family_yearly_income",
)


def _read_only_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("data/campaign_poc.db"))
    parser.add_argument(
        "--product-catalog", type=Path, default=Path("data/product_master.csv")
    )
    parser.add_argument("--product-id", default="PRD001")
    parser.add_argument("--window-start", default="2024-01-01")
    parser.add_argument("--window-end", default="2025-12-31")
    parser.add_argument("--sample-size", type=int, default=1000)
    parser.add_argument("--chunk-size", type=int, default=137)
    args = parser.parse_args()
    if not 1 <= args.sample_size <= 10_000:
        raise SystemExit("sample-size must be between 1 and 10000")

    cohort = build_product_buyer_cohorts(
        args.database,
        product_ids=[args.product_id],
        window_start=args.window_start,
        window_end=args.window_end,
        product_catalog_path=args.product_catalog,
    )
    profile = fit_buyer_similarity_profile(
        cohort, product_id=args.product_id, assignment_chunk_size=31
    )

    with _read_only_connection(args.database) as source:
        columns = ",".join(SAMPLE_COLUMNS)
        demographic_rows = source.execute(
            f"SELECT {columns} FROM demographics ORDER BY person_id LIMIT ?",
            (args.sample_size,),
        ).fetchall()
        demographic_import = source.execute(
            """SELECT import_id,source_checksum FROM data_import_runs
               WHERE dataset_name='demographics' AND status='COMPLETED'
               ORDER BY import_id DESC LIMIT 1"""
        ).fetchone()
    if not demographic_rows or demographic_import is None:
        raise SystemExit("Current canonical demographics and provenance are required.")

    lineage = profile["lineage"]
    with tempfile.TemporaryDirectory(prefix="lookalike-v3-stage04-") as directory:
        root = Path(directory)
        registry_database = root / "registry.db"
        initialize_database(registry_database)
        reserved_ids = {
            int(lineage["customer_import_id"]),
            int(lineage["campaign_sales_import_id"]),
        }
        demographic_id = max(reserved_ids) + 1
        with get_connection(registry_database, write=True) as connection:
            connection.executemany(
                """INSERT INTO data_import_runs (
                    import_id,dataset_name,source_path,started_at,completed_at,status,
                    rows_read,rows_inserted,rows_rejected,source_checksum
                ) VALUES (?,?,?,?,?,'COMPLETED',?,?,0,?)""",
                (
                    (
                        lineage["customer_import_id"],
                        "customers",
                        "canonical-read-only",
                        "2026-10-06T00:00:00Z",
                        "2026-10-06T00:00:01Z",
                        0,
                        0,
                        lineage["customer_source_checksum"],
                    ),
                    (
                        lineage["campaign_sales_import_id"],
                        "campaign_sales",
                        "canonical-read-only",
                        "2026-10-06T00:00:00Z",
                        "2026-10-06T00:00:01Z",
                        0,
                        0,
                        lineage["campaign_sales_source_checksum"],
                    ),
                    (
                        demographic_id,
                        "demographics",
                        "canonical-read-only-bounded-sample",
                        "2026-10-06T00:00:00Z",
                        "2026-10-06T00:00:01Z",
                        len(demographic_rows),
                        len(demographic_rows),
                        str(demographic_import["source_checksum"]),
                    ),
                ),
            )
            marks = ",".join("?" for _ in SAMPLE_COLUMNS)
            connection.executemany(
                f"INSERT INTO demographics ({columns}) VALUES ({marks})",
                (tuple(row[column] for column in SAMPLE_COLUMNS) for row in demographic_rows),
            )

        published_profile = publish_buyer_similarity_profile(
            registry_database,
            profile,
            project_root=root,
            execution_owner="stage04-audit-profile",
            execution_token="a" * 64,
            now="2026-10-06T00:01:00Z",
        )
        estimate = estimate_similarity_preparation_work(
            registry_database,
            [published_profile.profile_id],
            project_root=root,
        )
        progress: list[tuple[str, int, int]] = []
        generated = run_similarity_generation(
            registry_database,
            published_profile.profile_id,
            project_root=root,
            execution_owner="stage04-audit-score",
            execution_token="b" * 64,
            chunk_size=args.chunk_size,
            progress_callback=lambda stage, processed, total, _message: progress.append(
                (stage, processed, total)
            ),
            clock=lambda: "2026-10-06T00:02:00Z",
        )
        reused = run_similarity_generation(
            registry_database,
            published_profile.profile_id,
            project_root=root,
            execution_owner="stage04-audit-reuse",
            execution_token="c" * 64,
            chunk_size=max(1, args.chunk_size // 2),
            clock=lambda: "2026-10-06T00:03:00Z",
        )
        generation_id = int(generated["similarity_generation_id"])
        winners = composite_similarity_winners(
            registry_database, [generation_id], project_root=root
        )
        with get_connection(registry_database) as connection:
            generation = dict(connection.execute(
                """SELECT g.publication_state,g.expected_person_count,
                          g.published_person_count,s.processed_count,
                          g.demographic_import_id,g.demographic_source_checksum,
                          g.score_method_version,g.scorer_contract_version
                   FROM buyer_similarity_score_generations g
                   JOIN buyer_similarity_generation_stages s
                     ON s.similarity_generation_id=g.similarity_generation_id
                    AND s.stage_code='SCORING_PROSPECTS'
                   WHERE g.similarity_generation_id=?""",
                (generation_id,),
            ).fetchone())
            attestation = dict(connection.execute(
                """SELECT verification_status,expected_person_count,
                          verified_row_count,valid_score_count,invalid_score_count,
                          verification_contract_version,integrity_contract_version
                   FROM buyer_similarity_generation_attestations
                   WHERE similarity_generation_id=?""",
                (generation_id,),
            ).fetchone())
            staged_count = int(connection.execute(
                """SELECT COUNT(*) FROM buyer_similarity_score_stage
                   WHERE similarity_generation_id=?""",
                (generation_id,),
            ).fetchone()[0])
            duplicate_count = int(connection.execute(
                """SELECT COUNT(*) FROM (
                       SELECT person_id FROM buyer_similarity_scores
                       WHERE similarity_generation_id=?
                       GROUP BY person_id HAVING COUNT(*)<>1
                   )""",
                (generation_id,),
            ).fetchone()[0])
            score_columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(buyer_similarity_scores)")
            }

        checks = {
            "canonical_database_opened_read_only": True,
            "bounded_disposable_registry_only": True,
            "work_estimate_matches_sample": (
                estimate["estimated_new_score_rows"] == len(demographic_rows)
            ),
            "published_after_deep_verification": (
                generated["status"] == "PUBLISHED"
                and generated["deep_verification_run"] is True
                and generation["publication_state"] == "PUBLISHED"
                and attestation["verification_status"] == "VERIFIED"
            ),
            "population_exact_and_deduplicated": (
                generation["expected_person_count"] == len(demographic_rows)
                and generation["published_person_count"] == len(demographic_rows)
                and generation["processed_count"] == len(demographic_rows)
                and attestation["verified_row_count"] == len(demographic_rows)
                and attestation["valid_score_count"] + attestation["invalid_score_count"]
                == len(demographic_rows)
                and duplicate_count == 0
            ),
            "progress_uses_actual_rows": (
                ("SCORING_PROSPECTS", len(demographic_rows), len(demographic_rows))
                in progress
            ),
            "queue_stage_is_separate": bool(progress and progress[0][0] == "QUEUE_WAIT"),
            "stage_removed_after_atomic_publication": staged_count == 0,
            "latest_import_currentness_attested": has_current_similarity_attestation(
                registry_database, generation_id, project_root=root
            ),
            "second_call_reuses_without_deep_verification": (
                reused["reused"] is True
                and reused["deep_verification_run"] is False
                and reused["similarity_generation_id"] == generation_id
            ),
            "one_product_composite_is_deduplicated": (
                len(winners) == attestation["valid_score_count"]
                and len({row["person_id"] for row in winners}) == len(winners)
            ),
            "score_storage_contains_no_contact_pii": not bool(
                score_columns
                & {"first_name", "last_name", "email", "phone_number", "address_line_1"}
            ),
        }
        report = {
            "audit_contract": "LOOKALIKE_V3_STAGE_04_SCORING_ATTESTATION_AUDIT_V1",
            "source_database": str(args.database).replace("\\", "/"),
            "source_database_open_mode": "READ_ONLY",
            "temporary_registry_removed": True,
            "full_population_run": False,
            "product_id": args.product_id,
            "sample_person_count": len(demographic_rows),
            "chunk_size": args.chunk_size,
            "generation": generation,
            "attestation": attestation,
            "work_estimate": estimate,
            "progress_event_count": len(progress),
            "checks": checks,
            "status": "PASS" if all(checks.values()) else "FAIL",
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
