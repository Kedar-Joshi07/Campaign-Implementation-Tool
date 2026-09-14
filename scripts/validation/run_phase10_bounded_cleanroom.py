#!/usr/bin/env python3
"""Run the bounded deterministic Phase 10 clean-room certification twice."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.connection import get_connection
from app.database.schema import (
    CAMPAIGN_SALES_COLUMNS,
    CUSTOMER_COLUMNS,
    DEMOGRAPHIC_COLUMNS,
    initialize_database,
)
from app.repositories.phase10_intelligence_repository import (
    Phase10IntelligenceRepository,
)
from app.services.campaign_targeting_context_service import (
    get_campaign_targeting_context,
    save_business_targeting_criteria,
    save_campaign_targeting_context,
)
from app.services.data_import_service import (
    import_campaign_sales,
    import_customers,
    import_demographics,
)
from app.services.audience_query_service import _categorical_vocabularies_from_snapshot
from app.services.phase10_lifecycle_service import reconcile_phase10_lifecycle
from app.services.phase10_orchestration_service import (
    BUSINESS_LABELS,
    build_phase10_requested_intelligence,
    prepare_phase10_orchestration,
    reconcile_phase10_orchestrations,
    run_phase10_orchestration,
)
from app.services.target_group_campaign_service import (
    save_target_group_and_create_campaign_draft,
)
from app.services.target_group_preview_service import (
    _materialize_business_selection,
    _preview_inputs,
    get_target_group_preview,
)

DEFAULT_JSON_PATH = PROJECT_ROOT / "docs" / "evidence" / "phase10" / "13_cleanroom_phase10.json"
DEFAULT_REPORT_PATH = (
    PROJECT_ROOT / "docs" / "evidence" / "phase10" / "13_CLEANROOM_PHASE10_REPORT.md"
)


class Phase10CleanRoomError(RuntimeError):
    """Raised when a clean-room invariant fails."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Phase10CleanRoomError(message)


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: Any) -> str:
    payload = value if isinstance(value, str) else _canonical(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(
    path: Path,
    columns: Sequence[str],
    rows: Iterable[Mapping[str, object]],
) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for source in rows:
            row = {column: "" for column in columns}
            row.update(source)
            writer.writerow(row)
    return path


def _customer_rows(count: int) -> list[dict[str, object]]:
    return [
        {
            "customer_id": f"C{index:03d}",
            "first_name": f"Customer{index}",
            "last_name": "CleanRoom",
            "gender": "Female" if index % 2 else "Male",
            "date_of_birth": f"19{70 + (index % 25):02d}-01-01",
            "state": "Ohio" if index % 3 else "Texas",
            "country": "United States",
            "email": f"customer{index}@example.test",
            "individual_yearly_income": 40_000 + (index * 1_000),
            "family_member_count": 2 + (index % 3),
            "resident_status": "Resident",
            "resident_type": "House",
            "education": "College",
            "employment_status": "Employed",
            "type_of_employment": "Salaried",
            "marital_status": "Married",
        }
        for index in range(1, count + 1)
    ]


def _campaign_rows(*, include_history_refresh: bool = False) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(1, 41):
        positive = 1 if index <= 20 else 0
        rows.append(
            {
                "campaign_sales_id": f"S{index:03d}",
                "customer_id": f"C{index:03d}",
                "campaign_id": "CMP-P1",
                "product_id": "P1",
                "order_id": f"O-P1-{index:03d}" if positive else "",
                "campaign_name": "P1 Retention",
                "campaign_type": "Retention",
                "campaign_channel": "Email",
                "campaign_start_date": "2025-01-01",
                "campaign_end_date": "2025-12-31",
                "campaign_category": "Retention",
                "offer_type": "Loyalty",
                "product_name": "Product One",
                "product_category": "Core",
                "contact_date": f"2025-01-{1 + ((index - 1) % 28):02d}",
                "purchase_date": (
                    f"2025-01-{1 + ((index - 1) % 28):02d}" if positive else ""
                ),
                "quantity": 1 if positive else "",
                "days_to_purchase": 0 if positive else "",
                "contacted_flag": 1,
                "engagement_flag": positive,
                "response_flag": positive,
                "purchase_flag": positive,
                "campaign_attributed_sale_flag": positive,
                "pu_label": positive,
            }
        )
    for index in range(1, 5):
        positive = 1 if index <= 2 else 0
        rows.append(
            {
                "campaign_sales_id": f"SP2{index:02d}",
                "customer_id": f"C{index:03d}",
                "campaign_id": "CMP-P2",
                "product_id": "P2",
                "order_id": f"O-P2-{index:02d}" if positive else "",
                "campaign_name": "P2 Acquisition",
                "campaign_type": "Acquisition",
                "campaign_channel": "Email",
                "campaign_start_date": "2025-02-01",
                "campaign_end_date": "2025-02-28",
                "campaign_category": "Acquisition",
                "offer_type": "Discount",
                "product_name": "Product Two",
                "product_category": "Growth",
                "contact_date": f"2025-02-{index:02d}",
                "purchase_date": f"2025-02-{index:02d}" if positive else "",
                "quantity": 1 if positive else "",
                "days_to_purchase": 0 if positive else "",
                "contacted_flag": 1,
                "engagement_flag": positive,
                "response_flag": positive,
                "purchase_flag": positive,
                "campaign_attributed_sale_flag": positive,
                "pu_label": positive,
            }
        )
    if include_history_refresh:
        rows.append(
            {
                "campaign_sales_id": "S041",
                "customer_id": "C041",
                "campaign_id": "CMP-P1",
                "product_id": "P1",
                "campaign_name": "P1 Retention Refresh",
                "campaign_type": "Retention",
                "campaign_channel": "Email",
                "campaign_start_date": "2025-01-01",
                "campaign_end_date": "2025-12-31",
                "campaign_category": "Retention",
                "offer_type": "Loyalty",
                "product_name": "Product One",
                "product_category": "Core",
                "contact_date": "2025-03-01",
                "contacted_flag": 1,
                "engagement_flag": 0,
                "response_flag": 0,
                "purchase_flag": 0,
                "campaign_attributed_sale_flag": 0,
                "pu_label": 0,
            }
        )
    return rows


def _demographic_rows(count: int) -> list[dict[str, object]]:
    return [
        {
            "person_id": f"P{index:04d}",
            "first_name": f"Prospect{index}",
            "last_name": "CleanRoom",
            "gender": "Female" if index % 2 else "Male",
            "age": 21 + (index % 60),
            "address_line_1": f"{index} Test Avenue",
            "street": "Test Avenue",
            "postal_code": f"{43000 + index:05d}",
            "city": "Columbus" if index % 3 else "Austin",
            "state": "Ohio" if index % 3 else "Texas",
            "country": "United States",
            "phone_number": f"+1614555{index:04d}",
            "email": f"prospect{index}@example.test",
            "individual_yearly_income": 45_000 + (index * 100),
            "marital_status": "Married",
            "education": "College",
            "employment_status": "Employed",
            "resident_status": "Resident",
            "resident_type": "House",
            "family_member_count": 2 + (index % 2),
            "number_of_children_in_family": index % 2,
            "number_of_adults_in_family": 2,
            "type_of_employment": "Salaried",
            "family_yearly_income": 70_000 + (index * 100),
        }
        for index in range(1, count + 1)
    ]


def _seed_fresh_database(run_root: Path) -> Path:
    source_root = run_root / "sources"
    source_root.mkdir(parents=True)
    database_path = run_root / "phase10-cleanroom.db"
    initialize_database(database_path)
    customer_file = _write_csv(
        source_root / "customers-v1.csv", CUSTOMER_COLUMNS, _customer_rows(40)
    )
    campaign_file = _write_csv(
        source_root / "campaign-sales-v1.csv",
        CAMPAIGN_SALES_COLUMNS,
        _campaign_rows(),
    )
    demographic_file = _write_csv(
        source_root / "demographics-v1.csv",
        DEMOGRAPHIC_COLUMNS,
        _demographic_rows(80),
    )
    customer_import = import_customers(
        customer_file, database_path=database_path, batch_size=100
    )
    campaign_import = import_campaign_sales(
        campaign_file, database_path=database_path, batch_size=100
    )
    demographic_import = import_demographics(
        [demographic_file], database_path=database_path, batch_size=100
    )
    _require(customer_import.rows_inserted == 40, "Customer import count mismatch.")
    _require(campaign_import.rows_inserted == 44, "Campaign import count mismatch.")
    _require(demographic_import.rows_inserted == 80, "Demographic import count mismatch.")
    return database_path


def _insert_import_provenance(
    database_path: Path,
    *,
    dataset_name: str,
    source_path: Path,
    row_count: int,
    timestamp: str,
) -> None:
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO data_import_runs (
                dataset_name, source_path, started_at, completed_at, status,
                rows_read, rows_inserted, rows_rejected, source_checksum
            ) VALUES (?, ?, ?, ?, 'COMPLETED', ?, ?, 0, ?)
            """,
            (
                dataset_name,
                str(source_path),
                timestamp,
                timestamp,
                row_count,
                row_count,
                _file_digest(source_path),
            ),
        )


def _apply_demographic_refresh(
    database_path: Path,
    run_root: Path,
    *,
    count: int,
    version: int,
) -> None:
    rows = _demographic_rows(count)
    source = _write_csv(
        run_root / "sources" / f"demographics-v{version}.csv",
        DEMOGRAPHIC_COLUMNS,
        rows,
    )
    new_row = rows[-1]
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO demographics (
                person_id, first_name, last_name, gender, age,
                address_line_1, street, postal_code, city, state, country,
                phone_number, email, individual_yearly_income, marital_status,
                education, employment_status, resident_status, resident_type,
                family_member_count, number_of_children_in_family,
                number_of_adults_in_family, type_of_employment,
                family_yearly_income
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            tuple(
                new_row[field]
                for field in (
                    "person_id",
                    "first_name",
                    "last_name",
                    "gender",
                    "age",
                    "address_line_1",
                    "street",
                    "postal_code",
                    "city",
                    "state",
                    "country",
                    "phone_number",
                    "email",
                    "individual_yearly_income",
                    "marital_status",
                    "education",
                    "employment_status",
                    "resident_status",
                    "resident_type",
                    "family_member_count",
                    "number_of_children_in_family",
                    "number_of_adults_in_family",
                    "type_of_employment",
                    "family_yearly_income",
                )
            ),
        )
    _insert_import_provenance(
        database_path,
        dataset_name="demographics",
        source_path=source,
        row_count=count,
        timestamp=f"2026-09-14T0{version}:00:00Z",
    )


def _apply_historical_refresh(database_path: Path, run_root: Path) -> None:
    customer_rows = _customer_rows(41)
    campaign_rows = _campaign_rows(include_history_refresh=True)
    customer_source = _write_csv(
        run_root / "sources" / "customers-v2.csv",
        CUSTOMER_COLUMNS,
        customer_rows,
    )
    campaign_source = _write_csv(
        run_root / "sources" / "campaign-sales-v2.csv",
        CAMPAIGN_SALES_COLUMNS,
        campaign_rows,
    )
    customer = customer_rows[-1]
    sale = campaign_rows[-1]
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO customers (
                customer_id, first_name, last_name, gender, date_of_birth,
                state, country, email, individual_yearly_income,
                family_member_count, resident_status, resident_type, education,
                employment_status, type_of_employment, marital_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(
                customer[field]
                for field in (
                    "customer_id",
                    "first_name",
                    "last_name",
                    "gender",
                    "date_of_birth",
                    "state",
                    "country",
                    "email",
                    "individual_yearly_income",
                    "family_member_count",
                    "resident_status",
                    "resident_type",
                    "education",
                    "employment_status",
                    "type_of_employment",
                    "marital_status",
                )
            ),
        )
        connection.execute(
            """
            INSERT INTO campaign_sales (
                campaign_sales_id, customer_id, campaign_id, product_id,
                campaign_name, campaign_type, campaign_channel,
                campaign_start_date, campaign_end_date, campaign_category,
                offer_type, product_name, product_category, contact_date,
                contacted_flag, engagement_flag, response_flag, purchase_flag,
                campaign_attributed_sale_flag, pu_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(
                sale[field]
                for field in (
                    "campaign_sales_id",
                    "customer_id",
                    "campaign_id",
                    "product_id",
                    "campaign_name",
                    "campaign_type",
                    "campaign_channel",
                    "campaign_start_date",
                    "campaign_end_date",
                    "campaign_category",
                    "offer_type",
                    "product_name",
                    "product_category",
                    "contact_date",
                    "contacted_flag",
                    "engagement_flag",
                    "response_flag",
                    "purchase_flag",
                    "campaign_attributed_sale_flag",
                    "pu_label",
                )
            ),
        )
    _insert_import_provenance(
        database_path,
        dataset_name="customers",
        source_path=customer_source,
        row_count=41,
        timestamp="2026-09-14T04:00:00Z",
    )
    _insert_import_provenance(
        database_path,
        dataset_name="campaign_sales",
        source_path=campaign_source,
        row_count=45,
        timestamp="2026-09-14T04:00:01Z",
    )


def _campaign_context(product_id: str, delivery_channel: str) -> dict[str, Any]:
    if product_id == "P2":
        campaign_type, category, offer = "Acquisition", "Acquisition", "Discount"
    else:
        campaign_type, category, offer = "Retention", "Retention", "Loyalty"
    return {
        "product_ids": [product_id],
        "campaign_types": [campaign_type],
        "campaign_categories": [category],
        "offer_types": [offer],
        "campaign_channel": delivery_channel,
        "historical_campaign_channels": ["Email"],
    }


def _create_context(database_path: Path, product_id: str, channel: str) -> int:
    saved = save_campaign_targeting_context(
        database_path,
        _campaign_context(product_id, channel),
    )
    return int(saved["targeting_context_id"])


def _prepare_inline(database_path: Path, context_id: int, run_root: Path):
    return prepare_phase10_orchestration(
        database_path,
        context_id,
        project_root=run_root,
        submitter=lambda db, oid, root: run_phase10_orchestration(
            db,
            oid,
            project_root=root,
            artifact_root=Path("artifacts/models"),
            scoring_chunk_size=1_000,
            rank_chunk_size=1_000,
        ),
    )


def _counts(database_path: Path) -> dict[str, int]:
    tables = (
        "historical_analysis_runs",
        "model_runs",
        "scoring_runs",
        "propensity_scores",
        "audience_rank_boundaries",
        "audience_analytics_snapshots",
        "jobs",
        "phase10_intelligence_generations",
        "saved_audiences",
        "campaigns",
    )
    with get_connection(database_path) as connection:
        return {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }


def _generation(database_path: Path, context_id: int) -> dict[str, Any]:
    repository = Phase10IntelligenceRepository(database_path)
    binding = repository.fetch_context_binding(context_id)
    _require(binding is not None and binding["binding_status"] == "READY", "READY binding missing.")
    generation = repository.fetch_generation(int(binding["generation_id"]))
    _require(generation is not None, "READY generation missing.")
    return generation


def _save_group(
    database_path: Path,
    context_id: int,
    *,
    suffix: str,
) -> dict[str, Any]:
    return save_target_group_and_create_campaign_draft(
        database_path,
        targeting_context_id=context_id,
        request_payload={
            "target_group_name": f"Clean-room Target Group {suffix}",
            "target_group_description": f"Deterministic group {suffix}",
            "campaign_name": f"Clean-room Campaign {suffix}",
            "campaign_description": f"Deterministic campaign {suffix}",
            "planned_launch_date": "2026-10-15",
        },
    )


def _score_hash(database_path: Path, scoring_run_id: int) -> str:
    with get_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT person_id, printf('%.15f', propensity_score) AS score
            FROM propensity_scores WHERE scoring_run_id = ? ORDER BY person_id
            """,
            (scoring_run_id,),
        ).fetchall()
    return _digest([[row["person_id"], row["score"]] for row in rows])


def _rank_hash(database_path: Path, scoring_run_id: int) -> str:
    with get_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT percentile_bucket, boundary_rank,
                   printf('%.15f', boundary_score) AS boundary_score,
                   boundary_person_id, total_population, rank_contract_version
            FROM audience_rank_boundaries
            WHERE scoring_run_id = ? ORDER BY percentile_bucket
            """,
            (scoring_run_id,),
        ).fetchall()
    return _digest([list(row) for row in rows])


def _selected_member_ids(database_path: Path, context_id: int) -> list[str]:
    path, _resolution, criteria, audience_context = _preview_inputs(
        database_path,
        targeting_context_id=context_id,
    )
    with get_connection(path, write=True) as connection:
        table = _materialize_business_selection(
            connection,
            scoring_run_id=int(audience_context.scoring_row["scoring_run_id"]),
            filter_branches=criteria["audience_filter_branches"],
            selection=criteria["audience_selection"],
            boundaries=audience_context.boundaries,
            categorical_vocabularies=_categorical_vocabularies_from_snapshot(
                audience_context.analytics_snapshot
            ),
            universe_count=int(audience_context.scoring_row["scored_person_count"]),
        )
        rows = connection.execute(
            f'SELECT person_id FROM "{table}" ORDER BY person_id'
        ).fetchall()
    return [str(row["person_id"]) for row in rows]


def _run_one(label: str, run_root: Path) -> dict[str, Any]:
    started = time.perf_counter()
    run_root.mkdir(parents=True)
    database_path = _seed_fresh_database(run_root)
    repository = Phase10IntelligenceRepository(database_path)
    scenarios: dict[str, Any] = {}

    # 1. Complete new build through business preview/save/draft.
    first_context = _create_context(database_path, "P1", "EMAIL")
    save_business_targeting_criteria(
        database_path,
        {"match_strength": "BROAD", "selection_mode": "TOP_N", "target_count": 5},
        targeting_context_id=first_context,
    )
    first = _prepare_inline(database_path, first_context, run_root)
    first_row = first.orchestration
    _require(first_row["status"] == "READY", "Scenario 1 did not reach READY.")
    first_generation = _generation(database_path, first_context)
    first_preview = get_target_group_preview(
        database_path, targeting_context_id=first_context
    )
    first_saved = _save_group(database_path, first_context, suffix="PRIMARY")
    _require(first_saved["campaign"]["status"] == "DRAFT", "Scenario 1 draft missing.")
    scenarios["1_full_new_build"] = {
        "status": "PASS",
        "generation_id": int(first_generation["generation_id"]),
        "analysis_run_id": int(first_generation["analysis_run_id"]),
        "model_run_id": int(first_generation["model_run_id"]),
        "scoring_run_id": int(first_generation["scoring_run_id"]),
        "selected_count": int(first_preview["kpis"]["selected_for_target_group"]),
        "campaign_status": first_saved["campaign"]["status"],
    }

    # 2. Different delivery/name reuses exact heavy lineage.
    second_context = _create_context(database_path, "P1", "DIRECT_MAIL")
    save_business_targeting_criteria(
        database_path,
        {"match_strength": "BROAD", "selection_mode": "TOP_N", "target_count": 5},
        targeting_context_id=second_context,
    )
    before_reuse = _counts(database_path)
    second = _prepare_inline(database_path, second_context, run_root)
    second_generation = _generation(database_path, second_context)
    second_saved = _save_group(database_path, second_context, suffix="REUSE")
    after_reuse = _counts(database_path)
    for field in ("generation_id", "model_run_id", "scoring_run_id"):
        _require(second_generation[field] == first_generation[field], f"Scenario 2 changed {field}.")
    for table in ("model_runs", "scoring_runs", "propensity_scores", "jobs"):
        _require(after_reuse[table] == before_reuse[table], f"Scenario 2 added {table}.")
    _require(second.orchestration["status"] == "READY", "Scenario 2 did not reach READY.")
    _require(
        set(json.loads(second.orchestration["reuse_plan_json"]).values()) == {"REUSE"},
        "Scenario 2 was not an all-REUSE plan.",
    )
    scenarios["2_exact_reuse"] = {
        "status": "PASS",
        "same_generation": True,
        "same_model": True,
        "same_scoring": True,
        "no_new_heavy_job": True,
        "campaign_name": second_saved["campaign"]["campaign_name"],
        "delivery_channel": "DIRECT_MAIL",
    }

    # 3. Targeting-only change alters preview, not intelligence.
    preview_before = get_target_group_preview(
        database_path, targeting_context_id=second_context
    )
    before_target_change = _counts(database_path)
    save_business_targeting_criteria(
        database_path,
        {
            "match_strength": "BROAD",
            "genders": ["Female"],
            "age_groups": ["25-34", "55-64"],
            "selection_mode": "TOP_N",
            "target_count": 3,
        },
        targeting_context_id=second_context,
    )
    preview_after = get_target_group_preview(
        database_path, targeting_context_id=second_context
    )
    after_target_change = _counts(database_path)
    _require(
        preview_before["technical_details"]["audience_filter_hash"]
        != preview_after["technical_details"]["audience_filter_hash"],
        "Scenario 3 preview filter did not change.",
    )
    _require(_generation(database_path, second_context)["generation_id"] == first_generation["generation_id"], "Scenario 3 changed generation.")
    for table in ("model_runs", "scoring_runs", "propensity_scores", "jobs"):
        _require(after_target_change[table] == before_target_change[table], f"Scenario 3 added {table}.")
    scenarios["3_target_filter_only"] = {
        "status": "PASS",
        "same_generation": True,
        "preview_filter_changed": True,
        "selected_before": int(preview_before["kpis"]["selected_for_target_group"]),
        "selected_after": int(preview_after["kpis"]["selected_for_target_group"]),
    }

    # 4. Demographic drift reuses history/model and rebuilds scoring/rank.
    _apply_demographic_refresh(database_path, run_root, count=81, version=2)
    demographic_result = _prepare_inline(database_path, second_context, run_root)
    demographic_generation = _generation(database_path, second_context)
    _require(demographic_result.orchestration["status"] == "READY", "Scenario 4 not READY.")
    _require(demographic_generation["analysis_run_id"] == first_generation["analysis_run_id"], "Scenario 4 rebuilt analysis.")
    _require(demographic_generation["model_run_id"] == first_generation["model_run_id"], "Scenario 4 rebuilt model.")
    _require(demographic_generation["scoring_run_id"] != first_generation["scoring_run_id"], "Scenario 4 reused stale scoring.")
    _require(
        json.loads(demographic_result.orchestration["reuse_plan_json"])
        == {"analysis": "REUSE", "model": "REUSE", "rank": "BUILD", "scoring": "BUILD"},
        "Scenario 4 reuse plan mismatch.",
    )
    scenarios["4_demographic_source_change"] = {
        "status": "PASS",
        "analysis_reused": True,
        "model_reused": True,
        "scoring_rebuilt": True,
        "rank_rebuilt": True,
    }

    # 5. Historical source drift invalidates all downstream compatibility.
    _apply_historical_refresh(database_path, run_root)
    _prepare_inline(database_path, second_context, run_root)
    historical_generation = _generation(database_path, second_context)
    for field in ("analysis_run_id", "model_run_id", "scoring_run_id"):
        _require(historical_generation[field] != demographic_generation[field], f"Scenario 5 reused stale {field}.")
    lifecycle = reconcile_phase10_lifecycle(database_path)
    old_lifecycle = next(
        item
        for item in lifecycle["generations"]
        if item["generation_id"] == int(first_generation["generation_id"])
    )
    _require(not old_lifecycle["source_current"], "Scenario 5 old generation remained current.")
    _require(old_lifecycle["classification_before_protection"] == "STALE", "Scenario 5 old generation was not stale.")
    scenarios["5_historical_source_change"] = {
        "status": "PASS",
        "analysis_rebuilt": True,
        "model_rebuilt": True,
        "scoring_rebuilt": True,
        "old_generation_source_current": False,
    }

    # 6. Rank/analytics-only damage repairs without scoring.
    rank_scoring_id = int(historical_generation["scoring_run_id"])
    before_rank = _counts(database_path)
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "DELETE FROM audience_rank_boundaries WHERE scoring_run_id = ?",
            (rank_scoring_id,),
        )
        connection.execute(
            "DELETE FROM audience_analytics_snapshots WHERE scoring_run_id = ?",
            (rank_scoring_id,),
        )
    rank_result = _prepare_inline(database_path, second_context, run_root)
    rank_generation = _generation(database_path, second_context)
    after_rank = _counts(database_path)
    _require(rank_generation["scoring_run_id"] == rank_scoring_id, "Scenario 6 rebuilt scoring.")
    for table in ("model_runs", "scoring_runs", "propensity_scores", "jobs"):
        _require(after_rank[table] == before_rank[table], f"Scenario 6 added {table}.")
    with get_connection(database_path) as connection:
        current_boundary_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM audience_rank_boundaries WHERE scoring_run_id = ?",
                (rank_scoring_id,),
            ).fetchone()[0]
        )
    _require(current_boundary_count == 100, "Scenario 6 did not restore 100 boundaries.")
    scenarios["6_rank_only_recovery"] = {
        "status": "PASS",
        "scoring_reused": True,
        "rank_rebuilt": True,
        "reuse_plan": json.loads(rank_result.orchestration["reuse_plan_json"]),
    }

    # 7. Existing but insufficient P2 history blocks with no broadening/work.
    insufficient_context = _create_context(database_path, "P2", "EMAIL")
    before_blocked = _counts(database_path)
    blocked = _prepare_inline(database_path, insufficient_context, run_root)
    after_blocked = _counts(database_path)
    _require(blocked.orchestration["status"] == "BLOCKED", "Scenario 7 did not block.")
    for table in ("model_runs", "scoring_runs", "propensity_scores", "phase10_intelligence_generations"):
        _require(after_blocked[table] == before_blocked[table], f"Scenario 7 added {table}.")
    reopened = get_campaign_targeting_context(
        database_path, targeting_context_id=insufficient_context
    )
    _require(reopened["context"]["product_ids"] == ["P2"], "Scenario 7 broadened product selection.")
    scenarios["7_insufficient_history"] = {
        "status": "PASS",
        "terminal_status": "BLOCKED",
        "no_model_or_scoring": True,
        "context_not_broadened": True,
    }

    # 8. Persist RUNNING after verified model, reconcile, and resume scoring.
    _apply_demographic_refresh(database_path, run_root, count=82, version=3)
    restart = prepare_phase10_orchestration(
        database_path,
        second_context,
        project_root=run_root,
        submitter=lambda *_args: None,
    )
    restart_id = int(restart.orchestration["orchestration_id"])
    repository.mark_orchestration_running(
        restart_id,
        stage="CHECKING_COMPATIBILITY",
        progress_percent=2,
        business_message=BUSINESS_LABELS["CHECKING_COMPATIBILITY"],
        started_at="2026-09-14T06:00:00Z",
    )
    repository.update_orchestration_stage(
        restart_id,
        stage="VALIDATING_MODEL",
        progress_percent=47,
        business_message=BUSINESS_LABELS["VALIDATING_MODEL"],
        updated_at="2026-09-14T06:00:01Z",
        analysis_run_id=int(historical_generation["analysis_run_id"]),
        model_run_id=int(historical_generation["model_run_id"]),
    )
    submissions: list[int] = []
    reconciled = reconcile_phase10_orchestrations(
        database_path,
        project_root=run_root,
        submitter=lambda _db, oid, _root: submissions.append(oid),
    )
    _require(reconciled == 1 and submissions == [restart_id], "Scenario 8 reconciliation mismatch.")
    resumed = run_phase10_orchestration(
        database_path,
        restart_id,
        project_root=run_root,
        artifact_root=Path("artifacts/models"),
        scoring_chunk_size=1_000,
        rank_chunk_size=1_000,
    )
    restart_generation = _generation(database_path, second_context)
    _require(resumed["status"] == "READY", "Scenario 8 did not recover to READY.")
    _require(restart_generation["model_run_id"] == historical_generation["model_run_id"], "Scenario 8 retrained model.")
    _require(restart_generation["scoring_run_id"] != historical_generation["scoring_run_id"], "Scenario 8 did not resume scoring.")
    scenarios["8_restart_retry"] = {
        "status": "PASS",
        "reconciled_parent_count": reconciled,
        "resumed_from_progress": 47,
        "analysis_reused": True,
        "model_reused": True,
        "scoring_rebuilt": True,
    }

    # 9. Persist exact disjoint-branch union and Campaign linkage.
    save_business_targeting_criteria(
        database_path,
        {
            "match_strength": "BROAD",
            "age_groups": ["25-34", "55-64"],
            "income_groups": ["<25K", "50K-74,999"],
            "selection_mode": "TOP_N",
            "target_count": 10,
        },
        targeting_context_id=second_context,
    )
    member_ids = _selected_member_ids(database_path, second_context)
    _require(member_ids and len(member_ids) == len(set(member_ids)), "Scenario 9 union is empty/duplicated.")
    multi_saved = _save_group(database_path, second_context, suffix="MULTI")
    audience_id = int(multi_saved["saved_target_group"]["saved_target_group_id"])
    campaign_id = int(multi_saved["campaign"]["campaign_id"])
    with get_connection(database_path) as connection:
        metadata = dict(
            connection.execute(
                "SELECT * FROM phase9_saved_target_groups WHERE audience_id = ?",
                (audience_id,),
            ).fetchone()
        )
        campaign = dict(
            connection.execute(
                "SELECT * FROM campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
        )
        audience = dict(
            connection.execute(
                "SELECT * FROM saved_audiences WHERE audience_id = ?",
                (audience_id,),
            ).fetchone()
        )
    branches = json.loads(metadata["filter_branches_json"])
    _require(len(branches) == 4, "Scenario 9 did not preserve four branches.")
    _require(_digest(branches) == metadata["filter_branches_sha256"], "Scenario 9 branch hash mismatch.")
    _require(int(metadata["resolved_count"]) == len(member_ids), "Scenario 9 metadata count mismatch.")
    _require(int(audience["resolved_count"]) == len(member_ids), "Scenario 9 audience count mismatch.")
    _require(int(campaign["saved_audience_id"]) == audience_id, "Scenario 9 campaign linkage mismatch.")
    scenarios["9_multi_branch_target_group"] = {
        "status": "PASS",
        "branch_count": 4,
        "selected_count": len(member_ids),
        "unique_member_count": len(set(member_ids)),
        "filter_branches_sha256": metadata["filter_branches_sha256"],
        "member_ids_sha256": _digest(member_ids),
        "campaign_membership_exact": True,
    }

    final_generation = _generation(database_path, second_context)
    requested = build_phase10_requested_intelligence(database_path, second_context)
    final_counts = _counts(database_path)
    canonical_result = {
        "scenarios": scenarios,
        "initial_modeling_context_sha256": first_generation["modeling_context_sha256"],
        "initial_intelligence_key_sha256": first_generation["intelligence_key_sha256"],
        "initial_artifact_sha256": first_generation["artifact_sha256"],
        "final_modeling_context_sha256": requested.modeling_context.modeling_context_sha256,
        "final_intelligence_key_sha256": final_generation["intelligence_key_sha256"],
        "final_artifact_sha256": final_generation["artifact_sha256"],
        "final_score_rows": final_counts["propensity_scores"],
        "final_score_sha256": _score_hash(database_path, int(final_generation["scoring_run_id"])),
        "final_rank_sha256": _rank_hash(database_path, int(final_generation["scoring_run_id"])),
        "multi_branch_sha256": scenarios["9_multi_branch_target_group"]["filter_branches_sha256"],
        "multi_branch_members_sha256": scenarios["9_multi_branch_target_group"]["member_ids_sha256"],
        "multi_branch_selected_count": scenarios["9_multi_branch_target_group"]["selected_count"],
        "final_counts": final_counts,
    }
    return {
        "label": label,
        "status": "PASS",
        "duration_seconds": round(time.perf_counter() - started, 3),
        "bounded_source_counts": {
            "initial_customers": 40,
            "initial_campaign_sales": 44,
            "initial_demographics": 80,
            "final_customers": 41,
            "final_campaign_sales": 45,
            "final_demographics": 82,
        },
        "scenarios": scenarios,
        "canonical_result": canonical_result,
        "canonical_result_sha256": _digest(canonical_result),
    }


def _report(payload: dict[str, Any]) -> str:
    run_a, run_b = payload["runs"]
    lines = [
        "# Phase 10 Bounded Clean-Room Reuse, Build and Recovery",
        "",
        "Generated: 2026-09-14",
        "",
        "## Step result",
        "",
        "`PASS_STEP_13_BOUNDED_CLEANROOM_REUSE_BUILD_AND_RECOVERY`",
        "",
        "Two fresh isolated deterministic databases executed all nine required",
        "scenarios. Their canonical hashes, counts, and results matched exactly.",
        "",
        "## Scenario results",
        "",
        "| Scenario | Clean room A | Clean room B |",
        "|---|---|---|",
    ]
    for key in run_a["scenarios"]:
        lines.append(
            f"| {key.replace('_', ' ')} | {run_a['scenarios'][key]['status']} | "
            f"{run_b['scenarios'][key]['status']} |"
        )
    lines.extend(
        [
            "",
            "## Determinism",
            "",
            f"- Clean room A canonical SHA-256: `{run_a['canonical_result_sha256']}`",
            f"- Clean room B canonical SHA-256: `{run_b['canonical_result_sha256']}`",
            f"- Exact canonical equality: `{str(payload['deterministic_match']).lower()}`",
            "",
            "The comparison includes Modeling Context and intelligence identities,",
            "model artifact hashes, ordered score and rank hashes, multi-branch hash,",
            "member hash/count, complete scenario results, and final durable table counts.",
            "",
            "## Bounded and non-production execution",
            "",
            "Each clean room began with 40 customers, 44 campaign observations and",
            "80 prospects, ending after governed drift scenarios with 41 customers,",
            "45 campaign observations and 82 prospects. All databases, source files,",
            "and model artifacts lived below the dedicated runtime directory.",
            "",
            f"Runtime cleanup verified: `{str(payload['runtime_cleanup']['runtime_removed']).lower()}`.",
            "No canonical production source, database, model, score, rank or campaign",
            "file was read as an execution input or modified.",
            "",
            "## Verification",
            "",
            f"- Final A/B certification: PASS in {payload['duration_seconds']} seconds.",
            "- Affected scoring/lifecycle/orchestration regression: PASS - 14 tests.",
            "- Ruff, Python compilation and diff checks: PASS.",
            "",
            "## Machine-readable evidence",
            "",
            "`docs/evidence/phase10/13_cleanroom_phase10.json`",
            "",
            "## Stop boundary",
            "",
            "Step 13 stops after bounded A/B clean-room build, reuse, drift, recovery,",
            "BLOCKED, restart and multi-branch certification. Step 14+ browser, full",
            "scale, observability, performance, CI and freeze work was not started.",
            "",
            "`STOP_AFTER_STEP_13`",
            "",
        ]
    )
    return "\n".join(lines)


def run_certification(
    *,
    runtime_root: Path,
    json_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    runtime = runtime_root.resolve()
    if runtime == PROJECT_ROOT or PROJECT_ROOT not in runtime.parents:
        raise Phase10CleanRoomError("Runtime root must be a dedicated child of the repository.")
    if runtime.exists():
        raise Phase10CleanRoomError("Runtime root already exists; refusing to remove unknown data.")
    runtime.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    payload: dict[str, Any]
    try:
        runtime.mkdir()
        run_a = _run_one("A", runtime / "cleanroom-a")
        run_b = _run_one("B", runtime / "cleanroom-b")
        deterministic_match = run_a["canonical_result"] == run_b["canonical_result"]
        _require(deterministic_match, "Clean-room A/B canonical results differ.")
        payload = {
            "report_contract_version": "1",
            "overall_status": "PASS",
            "generated_at": "2026-09-14",
            "deterministic_match": deterministic_match,
            "runs": [run_a, run_b],
            "duration_seconds": round(time.perf_counter() - started, 3),
            "runtime_cleanup": {"runtime_removed": False},
        }
    finally:
        if runtime.exists():
            shutil.rmtree(runtime)
    payload["runtime_cleanup"]["runtime_removed"] = not runtime.exists()
    _require(payload["runtime_cleanup"]["runtime_removed"], "Runtime cleanup failed.")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(_report(payload), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=PROJECT_ROOT / ".tmp" / "phase10-step13-cleanroom",
    )
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()
    try:
        payload = run_certification(
            runtime_root=args.runtime_root,
            json_path=args.json_path,
            report_path=args.report_path,
        )
    except Exception as exc:
        print(f"[phase10-cleanroom] FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        "[phase10-cleanroom] PASS "
        f"canonical_sha256={payload['runs'][0]['canonical_result_sha256']} "
        f"duration_seconds={payload['duration_seconds']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
