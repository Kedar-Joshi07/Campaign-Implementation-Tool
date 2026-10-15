"""Run real app/main lifespan from a prepared isolated source copy."""

from __future__ import annotations

import csv
import os
import json
from pathlib import Path

import uvicorn
from fastapi.responses import FileResponse


def main() -> None:
    # The environment is set by the parent launcher before any app import.
    root = Path(os.environ["POST14B_QA_ROOT"]).resolve()
    source_root = root / "source"
    if Path(__file__).resolve().parents[3] != source_root:
        raise RuntimeError("QA server module did not load from its isolated copy.")
    from app.qa_guard import assert_qa_runtime
    from app.services.data_import_service import import_campaign_sales, import_customers, import_demographics
    from tests.test_post14b_fresh_v3_gate import _fresh_sources
    from tests.test_data_import import _campaign_row, _customer_row
    from app.database.schema import CAMPAIGN_SALES_COLUMNS, CUSTOMER_COLUMNS

    database = root / "state" / "qa.db"
    manifest = json.loads((root / "qa_fixture_manifest.json").read_text(encoding="utf-8"))
    assert_qa_runtime(database, project_root=source_root, operation="fixture_import")
    if not database.exists():
        if manifest["fixture_kind"] == "EMPTY":
            from app.database.schema import initialize_database
            (source_root / "data").mkdir(exist_ok=True)
            (source_root / "data" / "product_master.csv").write_text(
                "product_id,product_name,product_category\n", encoding="utf-8"
            )
            initialize_database(database)
        else:
            customers, sales, demographics, _ = _fresh_sources(
                source_root, prospect_count=manifest["expected_demographics"], qa_variants=True,
            )
            if manifest["fixture_kind"] == "NAMED_10K_QUALIFICATION":
                # The shared tiny-fixture helper appends the decimal person
                # index to a ten-digit phone base. At index 10,000 that
                # becomes an invalid 12-digit US number. Keep its intentional
                # missing-phone pattern, but give present synthetic contacts
                # a unique valid number within the named 20K QA hard cap.
                from app.database.schema import DEMOGRAPHIC_COLUMNS
                with demographics.open("r", newline="", encoding="utf-8") as file:
                    demographic_rows = list(csv.DictReader(file))
                for index, row in enumerate(demographic_rows):
                    if row["phone_number"]:
                        row["phone_number"] = f"+1202{5_000_000 + index:07d}"
                with demographics.open("w", newline="", encoding="utf-8") as file:
                    writer = csv.DictWriter(file, fieldnames=DEMOGRAPHIC_COLUMNS)
                    writer.writeheader()
                    writer.writerows(demographic_rows)
            if manifest["fixture_kind"] in {"UI_CATALOG_DIVERSE", "SIMILARITY_THRESHOLDS"}:
                from app.database.schema import DEMOGRAPHIC_COLUMNS
                with demographics.open("r", newline="", encoding="utf-8") as file:
                    demographic_rows = list(csv.DictReader(file))
                if manifest["fixture_kind"] == "SIMILARITY_THRESHOLDS":
                    for index, row in enumerate(demographic_rows):
                        group = index % 5
                        if group >= 1:
                            row["age"] = "80"
                        if group >= 2:
                            row["individual_yearly_income"] = "150000"
                            row["family_yearly_income"] = "200000"
                        if group >= 3:
                            row.update({"family_member_count": "5",
                                        "number_of_children_in_family": "3",
                                        "number_of_adults_in_family": "2"})
                        if group >= 4:
                            row.update({"gender": "Male", "state": "New York"})
                    with demographics.open("w", newline="", encoding="utf-8") as file:
                        writer = csv.DictWriter(file, fieldnames=DEMOGRAPHIC_COLUMNS)
                        writer.writeheader()
                        writer.writerows(demographic_rows)
            if manifest["fixture_kind"] == "UI_CATALOG_DIVERSE":
                with sales.open("r", newline="", encoding="utf-8") as file:
                    sales_rows = list(csv.DictReader(file))
                for index, row in enumerate(sales_rows):
                    row.update({
                        "campaign_name": f"Synthetic Catalog Campaign {index % 4}",
                        "campaign_type": ("Retention", "Acquisition")[index % 2],
                        "campaign_category": ("Seasonal", "Loyalty")[index % 2],
                        "offer_type": ("Discount", "Reward")[index % 2],
                        "campaign_channel": ("EMAIL", "SMS")[index % 2],
                        "product_name": f"Synthetic Product {row['product_id']}",
                        "product_category": (
                            "Everyday" if row["product_id"] == "P1" else "Specialty"
                        ),
                    })
                with sales.open("w", newline="", encoding="utf-8") as file:
                    writer = csv.DictWriter(file, fieldnames=CAMPAIGN_SALES_COLUMNS)
                    writer.writeheader()
                    writer.writerows(sales_rows)
                with demographics.open("r", newline="", encoding="utf-8") as file:
                    demographic_rows = list(csv.DictReader(file))
                for index, row in enumerate(demographic_rows):
                    if index % 2:
                        row.update({
                            "age": "52", "gender": "Male", "state": "New York",
                            "individual_yearly_income": "115000", "family_member_count": "4",
                            "family_yearly_income": "160000",
                            "number_of_children_in_family": "2", "number_of_adults_in_family": "2",
                            "marital_status": "Married", "education": "Postgraduate",
                            "employment_status": "Self-Employed", "resident_status": "Renter",
                            "resident_type": "Suburban", "type_of_employment": "Contract",
                        })
                with demographics.open("w", newline="", encoding="utf-8") as file:
                    writer = csv.DictWriter(file, fieldnames=DEMOGRAPHIC_COLUMNS)
                    writer.writeheader()
                    writer.writerows(demographic_rows)
            if manifest["fixture_kind"] == "SPARSE_BUYERS":
                with sales.open("r", newline="", encoding="utf-8") as file:
                    sales_rows = list(csv.DictReader(file))
                converted = 0
                for row in sales_rows:
                    if row["product_id"] == "P3" and converted < 8:
                        row["product_id"] = "P4"
                        row["product_name"] = "Sparse Buyers"
                        converted += 1
                if converted != 8:
                    raise RuntimeError("Sparse-buyer fixture expected eight P3 sales.")
                with sales.open("w", newline="", encoding="utf-8") as file:
                    writer = csv.DictWriter(file, fieldnames=CAMPAIGN_SALES_COLUMNS)
                    writer.writeheader()
                    writer.writerows(sales_rows)
            if manifest["fixture_kind"] in {"LEGACY_TRAINABLE", "PLANNER_TRAINABLE",
                                            "PLANNER_CALIBRATABLE"}:
                calibratable = manifest["fixture_kind"] == "PLANNER_CALIBRATABLE"
                positive_count = 400 if calibratable else 100
                unlabeled_count = 800 if calibratable else 200
                with customers.open("a", newline="", encoding="utf-8") as file:
                    writer = csv.DictWriter(file, fieldnames=CUSTOMER_COLUMNS)
                    if calibratable:
                        for index in range(230, positive_count):
                            writer.writerow(_customer_row(f"CUS{index:04d}"))
                    for index in range(unlabeled_count):
                        writer.writerow(_customer_row(f"CUS_U{index:04d}"))
                with sales.open("a", newline="", encoding="utf-8") as file:
                    writer = csv.DictWriter(file, fieldnames=CAMPAIGN_SALES_COLUMNS)
                    for index in range(positive_count):
                        row = _campaign_row(f"TRAIN_POS{index:04d}", f"CUS{index:04d}")
                        group = index % 10
                        row.update({"campaign_id": f"CMP_TRAIN_{group:02d}",
                                    "campaign_name": f"Training Campaign {group:02d}",
                                    "product_id": "P1", "order_id": f"TRAIN_ORDER{index:04d}",
                                    "purchase_date": "2025-01-02", "quantity": "1",
                                    "purchase_flag": "1", "campaign_attributed_sale_flag": "1",
                                    "pu_label": "1", "response_flag": "1",
                                    "gross_sales_amount": "100", "net_sales_amount": "100"})
                        if manifest["fixture_kind"] in {"PLANNER_TRAINABLE", "PLANNER_CALIBRATABLE"}:
                            row["campaign_type"] = "Training Fixture"
                        writer.writerow(row)
                    for index in range(unlabeled_count):
                        row = _campaign_row(f"TRAIN_UNLAB{index:04d}", f"CUS_U{index:04d}")
                        row.update({"campaign_id": f"CMP_TRAIN_{index % 10:02d}",
                                    "campaign_name": f"Training Campaign {index % 10:02d}",
                                    "product_id": "P1"})
                        if manifest["fixture_kind"] in {"PLANNER_TRAINABLE", "PLANNER_CALIBRATABLE"}:
                            row["campaign_type"] = "Training Fixture"
                        writer.writerow(row)
            assert import_customers(customers, database_path=database).rows_inserted == manifest["expected_customers"]
            assert import_campaign_sales(sales, database_path=database).rows_inserted == manifest["expected_campaign_sales"]
            assert import_demographics((demographics,), database_path=database).rows_inserted == manifest["expected_demographics"]
    counts = assert_qa_runtime(database, project_root=source_root,
                               operation="server_preimport", record_admission=True)
    if counts is None or any(
        counts[name] != manifest[f"expected_{name}"]
        for name in ("customers", "campaign_sales", "demographics")
    ):
        raise RuntimeError("QA fixture rows do not match the frozen manifest.")
    from app.main import app

    if manifest["fixture_kind"] == "FAULT_ONCE":
        # Named QA-only fault: fail the first genuine v3 worker preparation
        # call, then leave the unchanged worker path available for UI retry.
        # Never fabricate a successful API response or completion.
        from app.services import buyer_similarity_search_orchestration_service as similarity_worker

        original_resolver = similarity_worker.resolve_similarity_context
        marker = root / "fault_once_fired.json"

        def fail_once(*args, **kwargs):
            if not marker.exists():
                marker.write_text(json.dumps({
                    "fault": "BUYER_CONTEXT_RESOLUTION_ONCE",
                    "scope": "bounded_synthetic_qa",
                }), encoding="utf-8")
                raise RuntimeError("Injected one-shot bounded QA preparation fault.")
            return original_resolver(*args, **kwargs)

        similarity_worker.resolve_similarity_context = fail_once

    @app.get("/qa-retained", include_in_schema=False)
    def retained_qa_shell() -> FileResponse:
        return FileResponse(source_root / "frontend" / "index.html", media_type="text/html")

    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ["PORT"]),
                log_level="info", reload=False, workers=1)


if __name__ == "__main__":
    main()
