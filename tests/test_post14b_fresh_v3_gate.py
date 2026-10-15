"""Independent, bounded fresh-v3 path; never a legacy probability or 5M gate."""

from __future__ import annotations

import csv
import hashlib
import io
import importlib
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.dependencies import get_database_path
from app.main import app
from app.routers import potential_customer_search as search_router
from app.services import phase11_export_service as export_service
from app.services.buyer_similarity_preflight_service import exact_similarity_preflight
from app.services.data_import_service import import_campaign_sales, import_customers, import_demographics
from app.services.phase11_feedback_service import ingest_feedback, list_feedback
from app.services.phase11_results_service import get_result_detail
from tests.test_data_import import _campaign_row, _customer_row, _demographic_row, _write_source


def _fresh_sources(
    root: Path, *, prospect_count: int = 200, qa_variants: bool = False,
) -> tuple[Path, Path, Path, Path]:
    """Three overlapping, independently supported products and 200 prospects."""
    from app.database.schema import CAMPAIGN_SALES_COLUMNS, CUSTOMER_COLUMNS, DEMOGRAPHIC_COLUMNS

    cap = 20_000 if qa_variants else 2_000
    if prospect_count < 1 or prospect_count > cap:
        raise ValueError(f"Fresh-v3 fixture prospect count must be between 1 and {cap:,}.")
    source = root / "sources" / ("qa_v1" if qa_variants else "v1")
    source.mkdir(parents=True)
    catalog = root / "data" / "product_master.csv"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(
        "product_id,product_name,product_category\n"
        "P1,Fixture One,Fixtures\nP2,Fixture Two,Fixtures\n"
        "P3,Fixture Three,Fixtures\nP4,No Buyers,Fixtures\n",
        encoding="utf-8",
    )
    customers = []
    for index in range(230):
        customer = _customer_row(f"CUS{index:04d}")
        customer.update({"marital_status": "Single", "education": "Graduate",
                         "employment_status": "Employed", "resident_status": "Owner",
                         "resident_type": "Urban", "type_of_employment": "Salaried"})
        customers.append(customer)
    sales = []
    for product_index, product_id in enumerate(("P1", "P2", "P3")):
        for index in range(product_index * 10, product_index * 10 + 210):
            row = _campaign_row(f"SALE{len(sales):05d}", f"CUS{index:04d}")
            row.update({"product_id": product_id, "order_id": f"ORDER{len(sales):05d}",
                        "purchase_date": "2025-01-02", "quantity": "1",
                        "days_to_purchase": "0", "purchase_flag": "1",
                        "campaign_attributed_sale_flag": "1", "pu_label": "1",
                        "response_flag": "1", "gross_sales_amount": "100",
                        "net_sales_amount": "100"})
            sales.append(row)
    if qa_variants:
        for index in range(10):
            row = _campaign_row(f"UNLAB{index:05d}", f"CUS{index:04d}")
            row.update({"product_id": "P1", "campaign_id": "CMP_UNLABELED",
                        "order_id": f"UNLAB{index:05d}", "purchase_flag": "0",
                        "campaign_attributed_sale_flag": "0", "pu_label": "0",
                        "response_flag": "0", "quantity": "0",
                        "gross_sales_amount": "0", "net_sales_amount": "0"})
            sales.append(row)
    prospects = []
    for index in range(prospect_count):
        person = _demographic_row(f"PER{index:04d}")
        person.update({"age": "34", "gender": "Female",
                       "individual_yearly_income": "65000", "family_member_count": "2",
                       "number_of_children_in_family": "0", "number_of_adults_in_family": "2",
                       "marital_status": "Single", "education": "Graduate",
                       "employment_status": "Employed", "resident_status": "Owner",
                       "resident_type": "Urban", "type_of_employment": "Salaried",
                       "email": f"prospect{index}@example.test", "email_contactable": "1"})
        if qa_variants:
            variant = index % 10
            person.update({"phone_number": f"+1212555{index:04d}",
                           "address_line_1": f"{index + 1} Test Street",
                           "postal_code": "12345", "city": "Fixture City"})
            if variant == 0:
                person["telemarketing_contactable"] = "1"
            elif variant == 1:
                person["sms_opt_in"] = "1"
            elif variant == 2:
                person["whatsapp_opt_in"] = "1"
            elif variant == 3:
                person.update({"telemarketing_contactable": "0", "do_not_call": "1"})
            elif variant == 4:
                person["direct_mail_contactable"] = "1"
            elif variant == 5:
                person.update({"push_token": "pt_" + hashlib.sha256(
                    f"push-{index}".encode()
                ).hexdigest()[:32], "push_opt_in": "1"})
            elif variant == 6:
                person.update({"advertising_id": str(uuid.UUID(int=index + 1, version=4)),
                               "advertising_targetable": "1"})
            elif variant == 7:
                person.update({"web_visitor_id": "wv_" + hashlib.sha256(
                    f"web-{index}".encode()
                ).hexdigest()[:32],
                               "onsite_targetable": "1"})
            elif variant == 8:
                person.update({"email_contactable": "0", "email": ""})
            elif variant == 9:
                person.update({"email_contactable": "0", "email": "",
                               "phone_number": "", "address_line_1": ""})
        prospects.append(person)
    return (
        _write_source(source / "customers.csv", CUSTOMER_COLUMNS, customers),
        _write_source(source / "campaign_sales.csv", CAMPAIGN_SALES_COLUMNS, sales),
        _write_source(source / "demographics.csv", DEMOGRAPHIC_COLUMNS, prospects),
        catalog,
    )


def test_fresh_v3_runner_rejects_wrong_roots_and_missing_locks(tmp_path: Path, monkeypatch) -> None:
    from scripts.validation import run_post14b_fresh_v3 as runner

    with pytest.raises(ValueError, match="dedicated disposable QA tree"):
        runner.validate_qa_root(runner.PROJECT_ROOT / "data" / "operator.db")
    with pytest.raises(ValueError, match="dedicated disposable QA tree"):
        runner.validate_qa_root(runner.QA_PARENT)
    monkeypatch.setattr(runner, "REQUIRED_LOCKS", (tmp_path / "missing.lock",))
    with pytest.raises(SystemExit, match="dependency lock is missing"):
        runner.main()


def test_fresh_v3_fixture_rejects_over_cap_and_empty_population(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="between 1 and 2,000"):
        _fresh_sources(tmp_path, prospect_count=2_001)
    with pytest.raises(ValueError, match="between 1 and 2,000"):
        _fresh_sources(tmp_path, prospect_count=0)
    assert not (tmp_path / "sources").exists()


def _wait(client: TestClient, run_id: int) -> dict:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        response = client.get(f"/api/potential-customer-search/runs/{run_id}/status")
        assert response.status_code == 200, response.text
        state = response.json()
        if state["status"] in {"COMPLETED", "FAILED", "BLOCKED"}:
            assert state["status"] == "COMPLETED", state
            return state
        time.sleep(0.25)
    raise AssertionError("Real v3 worker did not finish within the bounded test deadline")


def test_empty_import_to_three_product_v3_snapshot_export_feedback_and_reuse(
    tmp_path: Path, monkeypatch,
) -> None:
    customers, sales, demographics, catalog = _fresh_sources(tmp_path)
    database = tmp_path / "fresh.db"
    assert not database.exists()
    assert import_customers(customers, database_path=database).rows_inserted == 230
    assert import_campaign_sales(sales, database_path=database).rows_inserted == 630
    assert import_demographics((demographics,), database_path=database).rows_inserted == 200
    with get_connection(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM buyer_similarity_profiles").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM buyer_similarity_score_generations").fetchone()[0] == 0

    monkeypatch.setattr(importlib.import_module("app.main"), "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(search_router, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(export_service, "DEFAULT_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        search_router, "exact_similarity_preflight",
        lambda path, **kwargs: exact_similarity_preflight(
            path, **kwargs, project_root=tmp_path, product_catalog_path=catalog,
        ),
    )
    monkeypatch.setattr(
        search_router.results_service, "get_result_detail",
        lambda path, run_id: get_result_detail(path, run_id, project_root=tmp_path),
    )
    app.dependency_overrides[get_database_path] = lambda: database
    try:
        with TestClient(app) as client:
            options_response = client.get("/api/potential-customer-search/options?include_similarity=true")
            assert options_response.status_code == 200, options_response.text
            options = options_response.json()
            profile = next(p for p in options["profiles"] if p["channel_code"] == "EMAIL"
                           and p["profile_version"] == "2")
            base = {
                "selection_contract_version": "3", "score_semantics": "PRODUCT_BUYER_SIMILARITY",
                "similarity_minimum": 0.50,
                "context": {"product_ids": ["P1", "P2", "P3"], "campaign_types": [],
                            "campaign_categories": [], "offer_types": [],
                            "historical_campaign_channels": [], "campaign_channel": "EMAIL"},
                "criteria": {}, "selection_mode": "ALL_MATCHING",
                "catalog_version": options["catalog_version"],
            }
            before = client.post("/api/potential-customer-search/preflight", json=base)
            assert before.status_code == 200, before.text
            assert before.json()["similarity_currentness"] == "NOT_AVAILABLE"
            unsupported = client.post("/api/potential-customer-search/preflight", json={
                **base, "context": {**base["context"], "product_ids": ["P4"]},
            })
            assert unsupported.status_code == 422, unsupported.text
            with get_connection(database) as connection:
                assert connection.execute("SELECT COUNT(*) FROM campaign_search_runs").fetchone()[0] == 0
            request = base | {"campaign_name": "Fresh bounded three-product v3",
                              "export_profile": profile["export_profile"]}
            created = client.post("/api/potential-customer-search/runs", json=request)
            assert created.status_code == 201, created.text
            first_id = created.json()["search_run_id"]
            first = _wait(client, first_id)
            assert 0 < first["selected_count"] <= 200
            with get_connection(database) as connection:
                scoring_events = connection.execute(
                    """SELECT processed_count,total_count FROM campaign_search_progress_events
                       WHERE search_run_id=? AND stage_code IN
                       ('SCORING_PROSPECTS','VERIFYING_SIMILARITY')
                       AND total_count IS NOT NULL
                       ORDER BY progress_event_id""", (first_id,),
                ).fetchall()
            assert scoring_events
            counts = [int(row["processed_count"]) for row in scoring_events]
            assert counts == sorted(counts)
            assert max(counts) == 600  # Three products times 200 prospects.
            assert all(int(row["total_count"]) == 600 for row in scoring_events)
            assert first["progress"]["progress_unit"] == "people"
            after = client.post("/api/potential-customer-search/preflight", json=base)
            assert after.status_code == 200, after.text
            assert after.json()["similarity_currentness"] == "CURRENT"
            assert after.json()["selected_count"] == first["selected_count"]
            assert after.json()["selected_count"] < 10_000  # Fixture is not a 10K demo pass.
            result = client.get(f"/api/potential-customer-search/runs/{first_id}/result")
            assert result.status_code == 200, result.text
            detail = result.json()
            assert detail["selection_semantics"] == "PRODUCT_BUYER_SIMILARITY"
            assert detail["snapshot_provenance"]["currentness"] == "CURRENT"
            assert detail["snapshot_provenance"]["snapshot_sha256"]
            history = client.get("/api/potential-customer-search/results")
            assert history.status_code == 200, history.text
            assert any(row["search_run_id"] == first_id for row in history.json())
            download = client.get(f"/api/potential-customer-search/runs/{first_id}/download")
            assert download.status_code == 200, download.text
            exported = list(csv.DictReader(io.StringIO(download.text)))
            assert len(exported) == first["selected_count"]
            assert "buyer_similarity_score" in exported[0]
            assert "propensity_score" not in exported[0]
            assert all(row["email"].endswith("@example.test") for row in exported)

            feedback = ingest_feedback(
                database, first_id,
                rows=[{"person_id": exported[0]["person_id"], "outcome": 1,
                       "outcome_at": "2026-01-01T00:00:00Z"}],
                source_name="bounded-fixture", idempotency_key="fresh-v3-feedback-1",
                project_root=tmp_path,
            )
            assert feedback["recalibration_status"] == "NOT_AVAILABLE"
            assert len(list_feedback(database, first_id)) == 1
            repeat = client.post("/api/potential-customer-search/runs", json=request | {
                "campaign_name": "Fresh bounded three-product v3 repeat",
            })
            assert repeat.status_code == 201, repeat.text
            second_id = repeat.json()["search_run_id"]
            assert _wait(client, second_id)["selected_count"] == first["selected_count"]
            second = client.get(f"/api/potential-customer-search/runs/{second_id}/result").json()
            assert second["result_source"] == "EXACT_RESULT_REUSE"
            assert second["snapshot_provenance"]["snapshot_sha256"] == detail["snapshot_provenance"]["snapshot_sha256"]
            with get_connection(database) as connection:
                assert connection.execute("SELECT COUNT(*) FROM buyer_similarity_profiles WHERE publication_state='PUBLISHED'").fetchone()[0] == 3
                assert connection.execute("SELECT COUNT(*) FROM buyer_similarity_score_generations WHERE publication_state='PUBLISHED'").fetchone()[0] == 3
                assert connection.execute("SELECT COUNT(*) FROM score_calibration_artifacts").fetchone()[0] == 0
                assert connection.execute("SELECT COUNT(*) FROM campaign_feedback_batches").fetchone()[0] == 1

            # A real import replacement changes source identity; an old
            # generation/result must not be silently treated as current.
            demographics.write_text(
                demographics.read_text(encoding="utf-8").replace(
                    "prospect0@example.test", "replaced0@example.test"
                ), encoding="utf-8",
            )
            assert import_demographics((demographics,), database_path=database,
                                       replace=True).rows_inserted == 200
            refreshed = client.get("/api/potential-customer-search/options?include_similarity=true")
            assert refreshed.status_code == 200, refreshed.text
            stale = client.post("/api/potential-customer-search/preflight", json={
                **base, "catalog_version": refreshed.json()["catalog_version"],
            })
            assert stale.status_code == 200, stale.text
            assert stale.json()["similarity_currentness"] == "STALE"
            assert stale.json()["selected_count"] is None
    finally:
        app.dependency_overrides.pop(get_database_path, None)
