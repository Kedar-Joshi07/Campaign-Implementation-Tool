"""Stage 14B-09: imported sources through the real app, UI, and export."""

from __future__ import annotations

import csv
import importlib
import io
import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.dependencies import get_database_path
from app.main import app
from app.routers import potential_customer_search as search_router
from app.services import phase11_export_service as export_service
from app.services.buyer_similarity_preflight_service import exact_similarity_preflight
from app.services.data_import_service import (
    import_campaign_sales, import_customers, import_demographics,
)
from app.services.phase11_results_service import get_result_detail
from tests.test_data_import import (
    _campaign_row, _customer_row, _demographic_row, _write_source,
)
from tests.test_phase11_business_navigation import open_route

pytest_plugins = ("tests.test_phase11_business_navigation",)


def _import_fixture(root: Path) -> Path:
    root.joinpath("data").mkdir()
    root.joinpath("data", "product_master.csv").write_text(
        "product_id,product_name,product_category\n"
        "P1,Imported Buyer Product,Fixtures\n",
        encoding="utf-8",
    )
    customers = []
    sales = []
    for index in range(200):
        customer = _customer_row(f"CUS{index:04d}")
        customer.update({
            "marital_status": "Single", "education": "Graduate",
            "employment_status": "Employed", "resident_status": "Owner",
            "resident_type": "Urban", "type_of_employment": "Salaried",
        })
        customers.append(customer)
        sale = _campaign_row(f"SALE{index:04d}", customer["customer_id"])
        sale.update({
            "product_id": "P1", "order_id": f"ORDER{index:04d}",
            "purchase_date": "2025-01-02", "quantity": "1",
            "days_to_purchase": "0", "purchase_flag": "1",
            "campaign_attributed_sale_flag": "1", "pu_label": "1",
            "response_flag": "1", "gross_sales_amount": "100",
            "net_sales_amount": "100",
        })
        sales.append(sale)
    prospects = []
    for index in range(10):
        person = _demographic_row(f"PER{index:04d}")
        person.update({
            "age": "34", "gender": "Female",
            "individual_yearly_income": "65000", "family_member_count": "2",
            "number_of_children_in_family": "0", "number_of_adults_in_family": "2",
            "marital_status": "Single", "education": "Graduate",
            "employment_status": "Employed", "resident_status": "Owner",
            "resident_type": "Urban", "type_of_employment": "Salaried",
            "email": f"prospect{index}@example.test", "email_contactable": "1",
        })
        prospects.append(person)
    from app.database.schema import (
        CAMPAIGN_SALES_COLUMNS, CUSTOMER_COLUMNS, DEMOGRAPHIC_COLUMNS,
    )
    sources = root / "sources"
    sources.mkdir()
    customer_file = _write_source(sources / "customers.csv", CUSTOMER_COLUMNS, customers)
    sales_file = _write_source(sources / "campaign_sales.csv", CAMPAIGN_SALES_COLUMNS, sales)
    prospect_file = _write_source(sources / "demographics.csv", DEMOGRAPHIC_COLUMNS, prospects)
    database = root / "imported.db"
    assert import_customers(customer_file, database_path=database).rows_inserted == 200
    assert import_campaign_sales(sales_file, database_path=database).rows_inserted == 200
    assert import_demographics((prospect_file,), database_path=database).rows_inserted == 10
    return database


def _wait_for_completion(client: TestClient, run_id: int) -> dict:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        response = client.get(f"/api/potential-customer-search/runs/{run_id}/status")
        assert response.status_code == 200, response.text
        state = response.json()
        if state["status"] in {"COMPLETED", "FAILED", "BLOCKED"}:
            assert state["status"] == "COMPLETED", state
            return state
        time.sleep(0.25)
    pytest.fail("The imported v3 search did not complete within 90 seconds.")


@pytest.mark.browser
def test_import_to_http_chrome_snapshot_reuse_and_channel_export(
    page, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _import_fixture(tmp_path)
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT COUNT(DISTINCT dataset_name) FROM data_import_runs WHERE status='COMPLETED'"
        ).fetchone()[0] == 3
    monkeypatch.setattr(importlib.import_module("app.main"), "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(search_router, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(export_service, "DEFAULT_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        search_router, "exact_similarity_preflight",
        lambda path, **kwargs: exact_similarity_preflight(
            path, **kwargs, project_root=tmp_path,
            product_catalog_path=tmp_path / "data" / "product_master.csv",
        ),
    )
    monkeypatch.setattr(
        search_router.results_service, "get_result_detail",
        lambda path, run_id: get_result_detail(path, run_id, project_root=tmp_path),
    )
    app.dependency_overrides[get_database_path] = lambda: database
    browser, errors, _ = page
    try:
        with TestClient(app) as client:
            options_response = client.get("/api/potential-customer-search/options?include_similarity=true")
            assert options_response.status_code == 200, options_response.text
            options = options_response.json()
            profile = next(p for p in options["profiles"] if p["channel_code"] == "EMAIL"
                           and p["profile_version"] == "2")
            base = {
                "selection_contract_version": "3",
                "score_semantics": "PRODUCT_BUYER_SIMILARITY",
                "similarity_minimum": 0.70,
                "context": {"product_ids": ["P1"], "campaign_types": [],
                            "campaign_categories": [], "offer_types": [],
                            "historical_campaign_channels": [],
                            "campaign_channel": "EMAIL"},
                "criteria": {}, "selection_mode": "ALL_MATCHING",
                "catalog_version": options["catalog_version"],
            }
            preflight = client.post("/api/potential-customer-search/preflight", json=base)
            assert preflight.status_code == 200, preflight.text
            assert preflight.json()["similarity_currentness"] == "NOT_AVAILABLE"
            request = base | {"campaign_name": "Imported P1 buyers",
                              "export_profile": profile["export_profile"]}
            created = client.post("/api/potential-customer-search/runs", json=request)
            assert created.status_code == 201, created.text
            first_id = created.json()["search_run_id"]
            first = _wait_for_completion(client, first_id)
            assert first["selected_count"] == 10
            current_preflight = client.post("/api/potential-customer-search/preflight", json=base)
            assert current_preflight.status_code == 200, current_preflight.text
            assert current_preflight.json()["similarity_currentness"] == "CURRENT"
            assert current_preflight.json()["selected_count"] == 10
            detail_response = client.get(f"/api/potential-customer-search/runs/{first_id}/result")
            assert detail_response.status_code == 200, detail_response.text
            detail = detail_response.json()
            assert detail["selection_semantics"] == "PRODUCT_BUYER_SIMILARITY"
            assert detail["snapshot_provenance"]["currentness"] == "CURRENT"
            assert detail["similarity_explanation"]["sample_count"] == 10
            assert detail["similarity_explanation"]["feature_drivers"]
            history = client.get("/api/potential-customer-search/results")
            assert history.status_code == 200, history.text
            assert any(item["search_run_id"] == first_id and item["selection_contract_version"] == "3"
                       for item in history.json())
            download = client.get(f"/api/potential-customer-search/runs/{first_id}/download")
            assert download.status_code == 200, download.text
            exported = list(csv.DictReader(io.StringIO(download.text)))
            assert len(exported) == 10
            assert "buyer_similarity_score" in exported[0]
            assert "propensity_score" not in exported[0]
            assert all(row["email"].endswith("@example.test") for row in exported)
            second = client.post("/api/potential-customer-search/runs", json=request | {
                "campaign_name": "Imported P1 buyers again",
            })
            assert second.status_code == 201, second.text
            second_id = second.json()["search_run_id"]
            repeated = _wait_for_completion(client, second_id)
            assert repeated["selected_count"] == 10
            reused_detail = client.get(f"/api/potential-customer-search/runs/{second_id}/result").json()
            assert reused_detail["result_source"] == "EXACT_RESULT_REUSE"
            assert reused_detail["snapshot_provenance"]["snapshot_sha256"] == detail["snapshot_provenance"]["snapshot_sha256"]
            with get_connection(database) as connection:
                assert connection.execute("SELECT COUNT(*) FROM buyer_similarity_profiles WHERE publication_state='PUBLISHED'").fetchone()[0] == 1
                assert connection.execute("SELECT COUNT(*) FROM buyer_similarity_score_generations WHERE publication_state='PUBLISHED'").fetchone()[0] == 1
                assert connection.execute("SELECT COUNT(*) FROM score_calibration_artifacts").fetchone()[0] == 0

            def api(route):
                request = route.request
                parsed = urlsplit(request.url)
                response = client.request(
                    request.method, parsed.path + (f"?{parsed.query}" if parsed.query else ""),
                    content=request.post_data,
                    headers={"Content-Type": "application/json"},
                )
                route.fulfill(status=response.status_code,
                              content_type="application/json", body=response.content)

            browser.route("**/api/potential-customer-search/**", api)
            browser.route("**/api/health", lambda route: route.fulfill(
                status=200, content_type="application/json",
                body=client.get("/api/health").content,
            ))
            open_route(browser, f"#results/{first_id}")
            browser.locator("#result-detail-content").wait_for(state="visible")
            panel = browser.locator("#result-profile-details").inner_text().upper()
            assert "LARGEST OBSERVED DISTANCE DRIVERS" in panel
            assert "DESCRIPTIVE SAMPLE ONLY" in panel
            assert browser.locator("#result-detail-download").is_visible()
            assert errors == []
    finally:
        app.dependency_overrides.pop(get_database_path, None)
