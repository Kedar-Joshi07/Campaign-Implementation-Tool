"""Stage 14B-06 bounded system-Chrome checks with the real disposable API."""

# Imported pytest fixtures are registered by name even when not referenced
# directly; Ruff cannot see that runtime fixture lookup.
# ruff: noqa: F401, F811

from __future__ import annotations

import json
import importlib
import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_database_path
from app.main import app
from app.database.connection import get_connection
from app.services.buyer_similarity_preflight_service import exact_similarity_preflight
from app.services.phase11_results_service import get_result_detail
from app.services.buyer_similarity_search_orchestration_service import execute_similarity_search_safely
from app.services import potential_customer_search_submission_service as submission
from app.schemas.potential_customer_search import PotentialCustomerSearchV3Request
from app.repositories.campaign_result_registry_repository import CampaignResultRegistryRepository
from app.routers import potential_customer_search as search_router

from tests.test_phase11_business_navigation import browser_session, page, open_route
from tests.test_phase11_business_search_form import (
    OPTIONS, RUNS, choose, request_payload,
)
from tests.test_phase9_business_targeting import client, database_path
from tests.test_buyer_similarity_cohort_service import _seed
from app.services.potential_customer_search_submission_service import search_form_options


def test_product_options_use_observed_distinct_attributed_buyer_support(tmp_path):
    path = _seed(tmp_path / "buyer-options.db")
    options = search_form_options(path, workflow_available=True)
    products = {item["product_id"]: item for item in options["context"]["products"]}
    assert products["P1"]["buyer_support"] == {
        "distinct_attributed_buyers": 202,
        "status": "POTENTIALLY_SUPPORTED",
        "scope": "ALL_HISTORY_BEFORE_CONTEXT_FILTERS",
        "minimum_required": 200,
    }
    assert products["P3"]["buyer_support"]["distinct_attributed_buyers"] == 199
    assert products["P3"]["buyer_support"]["status"] == "INSUFFICIENT_HISTORY"
    assert products["P2"]["buyer_support"]["status"] == "INSUFFICIENT_HISTORY"


@pytest.mark.browser
def test_unprepared_v3_preflight_is_not_zero_or_blocked_by_missing_calibration(
    page, tmp_path, monkeypatch,
):
    database = _seed(tmp_path / "unprepared-ui.db")
    catalog = tmp_path / "products.csv"
    catalog.write_text(
        "product_id,product_name,product_category\n"
        "P1,Exact Product One,Category A\n"
        "P3,Unsupported Product Three,Category B\n",
        encoding="utf-8",
    )
    with get_connection(database, write=True) as connection:
        connection.execute(
            """INSERT INTO data_import_runs (
                   dataset_name,source_path,started_at,completed_at,status,
                   rows_read,rows_inserted,rows_rejected,source_checksum
               ) VALUES ('demographics','demographics.csv',?,?, 'COMPLETED',10,10,0,?)""",
            ("2026-10-07T00:00:00Z", "2026-10-07T00:00:00Z", "e" * 64),
        )
    app.dependency_overrides[get_database_path] = lambda: database
    monkeypatch.setattr(search_router, "exact_similarity_preflight", lambda path, **kwargs:
        exact_similarity_preflight(
            path, **kwargs, project_root=tmp_path, product_catalog_path=catalog,
        ))
    browser, errors, _ = page
    try:
        with TestClient(app) as api_client:
            def api(route):
                request = route.request
                parsed = urlsplit(request.url)
                response = api_client.request(
                    request.method, parsed.path,
                    content=request.post_data,
                    headers={"Content-Type": "application/json"},
                )
                route.fulfill(status=response.status_code,
                              content_type="application/json", body=response.content)

            browser.route("**/api/potential-customer-search/**", api)
            browser.route("**/api/health", lambda route: route.fulfill(
                status=200, content_type="application/json",
                body=api_client.get("/api/health").content,
            ))
            open_route(browser, "#find-potential-customers")
            browser.locator("#business-search-form").wait_for(state="visible")
            browser.locator("#business-campaign-name").fill("Unprepared P1")
            choose(browser, "product_ids", ["P1"])
            browser.locator("#business-export-profile").select_option(
                request_payload()["export_profile"]
            )
            browser.locator("#business-search-preflight").click()
            browser.wait_for_function(
                "document.querySelector('#business-search-preflight-result').textContent.includes('Not prepared')"
            )
            message = browser.locator("#business-search-preflight-result").inner_text()
            metrics = browser.locator("#business-search-preflight-result dl > div").evaluate_all(
                "items => Object.fromEntries(items.map(item => [item.querySelector('dt').textContent, item.querySelector('dd').textContent]))"
            )
            assert metrics["Eligible prospects"] == "10"
            assert metrics["Validly scored pool"] == "Not available"
            assert metrics["Selected"] == "Not available"
            assert metrics["Eventual exportable"] == "Not available"
            assert "Use Prepare & Start Search" in message
            assert "0 buyers" not in message
            _fixture_screenshot(browser, "v3_not_prepared_preflight_1280")
            choose(browser, "product_ids", ["P3"])
            browser.locator("#business-search-preflight").click()
            browser.wait_for_function(
                "document.querySelector('#business-search-preflight-result').textContent.includes('Unsupported product')"
            )
            unsupported = browser.locator("#business-search-preflight-result").inner_text()
            assert "Review the selected products or historical context" in unsupported
            assert "Not available" in unsupported
            _fixture_screenshot(browser, "v3_unsupported_product_1280")
            assert errors == []
    finally:
        app.dependency_overrides.pop(get_database_path, None)


@pytest.mark.browser
def test_current_v3_preflight_displays_distinct_exact_counts_without_probability(
    page, tmp_path, monkeypatch,
):
    database = _seed(tmp_path / "current-ui.db")
    catalog = tmp_path / "data" / "product_master.csv"
    catalog.parent.mkdir()
    catalog.write_text(
        "product_id,product_name,product_category\nP1,Exact Product One,Category A\n",
        encoding="utf-8",
    )
    with get_connection(database, write=True) as connection:
        connection.execute(
            """INSERT INTO data_import_runs (
                   dataset_name,source_path,started_at,completed_at,status,
                   rows_read,rows_inserted,rows_rejected,source_checksum
               ) VALUES ('demographics','demographics.csv',?,?, 'COMPLETED',10,10,0,?)""",
            ("2026-10-07T00:00:00Z", "2026-10-07T00:00:00Z", "e" * 64),
        )
    options = submission.search_form_options(database, workflow_available=True)
    context = {
        "product_ids": ["P1"], "campaign_types": [], "campaign_categories": [],
        "offer_types": [], "historical_campaign_channels": [], "campaign_channel": "EMAIL",
    }
    profile = next(item for item in options["profiles"] if item["channel_code"] == "EMAIL")
    monkeypatch.setattr(submission, "PHASE11_SEARCH_EXECUTOR", lambda *_: True)
    created = submission.submit_potential_customer_search(database, PotentialCustomerSearchV3Request(
        selection_contract_version="3", score_semantics="PRODUCT_BUYER_SIMILARITY",
        similarity_minimum=.50, campaign_name="Bounded prepared fixture",
        context=context, criteria={}, selection_mode="ALL_MATCHING",
        export_profile=profile["export_profile"], catalog_version=options["catalog_version"],
    ))
    repository = CampaignResultRegistryRepository(database)
    fence = repository.claim_search_attempt(created["search_run_id"], lease_owner="stage06-ui-fixture")
    outcome = execute_similarity_search_safely(
        database, created["search_run_id"], **fence.as_kwargs(), project_root=tmp_path,
    )
    assert outcome.status == "COMPLETED"
    app.dependency_overrides[get_database_path] = lambda: database
    monkeypatch.setattr(search_router, "exact_similarity_preflight", lambda path, **kwargs:
        exact_similarity_preflight(path, **kwargs, project_root=tmp_path, product_catalog_path=catalog))
    browser, errors, _ = page
    try:
        with TestClient(app) as api_client:
            def api(route):
                request = route.request
                parsed = urlsplit(request.url)
                response = api_client.request(
                    request.method, parsed.path + (f"?{parsed.query}" if parsed.query else ""),
                    content=request.post_data,
                    headers={"Content-Type": "application/json"},
                )
                route.fulfill(status=response.status_code,
                              content_type="application/json", body=response.content)

            browser.route("**/api/potential-customer-search/**", api)
            browser.route("**/api/health", lambda route: route.fulfill(
                status=200, content_type="application/json",
                body=api_client.get("/api/health").content,
            ))
            open_route(browser, "#find-potential-customers")
            browser.locator("#business-search-form").wait_for(state="visible")
            browser.locator("#business-campaign-name").fill("Prepared P1")
            choose(browser, "product_ids", ["P1"])
            browser.locator("#business-export-profile").select_option(profile["export_profile"])
            browser.locator('input[name="business_similarity_minimum"][value="0.5"]').check()
            browser.locator("#business-search-preflight").click()
            browser.wait_for_function(
                "document.querySelector('#business-search-preflight-result').textContent.includes('Current buyer similarity')"
            )
            metrics = browser.locator("#business-search-preflight-result dl > div").evaluate_all(
                "items => Object.fromEntries(items.map(item => [item.querySelector('dt').textContent, item.querySelector('dd').textContent]))"
            )
            assert metrics["Eligible prospects"] == "10"
            assert metrics["Selected"] == str(repository.fetch_search_run(created["search_run_id"])["selected_count"])
            assert metrics["Validly scored pool"] != "Not available"
            assert metrics["Similarity-qualified"] != "Not available"
            assert metrics["Eventual exportable"] == "Not available"
            assert "purchase probability" not in browser.locator("#business-search-preflight-result").inner_text().lower()
            _fixture_screenshot(browser, "v3_current_preflight_1280")
            browser.locator('input[name="business_similarity_minimum"][value="0.9"]').check()
            browser.locator("#business-search-preflight").click()
            browser.wait_for_function(
                "document.querySelector('#business-search-preflight-result').textContent.includes('Current buyer similarity') || document.querySelector('#business-search-preflight-result').textContent.includes('No exact matches')"
            )
            high_metrics = browser.locator("#business-search-preflight-result dl > div").evaluate_all(
                "items => Object.fromEntries(items.map(item => [item.querySelector('dt').textContent, item.querySelector('dd').textContent]))"
            )
            assert high_metrics["Selected"] == "0"
            assert "No prospects meet this exact similarity minimum" in browser.locator("#business-search-preflight-result").inner_text()
            _fixture_screenshot(browser, "v3_valid_zero_preflight_1280")
            assert errors == []
    finally:
        app.dependency_overrides.pop(get_database_path, None)


@pytest.mark.browser
def test_browser_prepare_starts_bounded_v3_build_without_probability_calibration(
    page, tmp_path, monkeypatch,
):
    database = _seed(tmp_path / "browser-build.db")
    catalog = tmp_path / "data" / "product_master.csv"
    catalog.parent.mkdir()
    catalog.write_text(
        "product_id,product_name,product_category\nP1,Exact Product One,Category A\n",
        encoding="utf-8",
    )
    with get_connection(database, write=True) as connection:
        connection.execute(
            """INSERT INTO data_import_runs (
                   dataset_name,source_path,started_at,completed_at,status,
                   rows_read,rows_inserted,rows_rejected,source_checksum
               ) VALUES ('demographics','demographics.csv',?,?, 'COMPLETED',10,10,0,?)""",
            ("2026-10-07T00:00:00Z", "2026-10-07T00:00:00Z", "e" * 64),
        )
        assert connection.execute("SELECT COUNT(*) FROM score_calibration_artifacts").fetchone()[0] == 0
    app.dependency_overrides[get_database_path] = lambda: database
    monkeypatch.setattr(importlib.import_module("app.main"), "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(search_router, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(search_router, "exact_similarity_preflight", lambda path, **kwargs:
        exact_similarity_preflight(path, **kwargs, project_root=tmp_path, product_catalog_path=catalog))
    monkeypatch.setattr(search_router.results_service, "get_result_detail", lambda path, run_id:
        get_result_detail(path, run_id, project_root=tmp_path))
    browser, errors, _ = page
    try:
        with TestClient(app) as api_client:
            def api(route):
                request = route.request
                parsed = urlsplit(request.url)
                response = api_client.request(
                    request.method, parsed.path + (f"?{parsed.query}" if parsed.query else ""),
                    content=request.post_data,
                    headers={"Content-Type": "application/json"},
                )
                route.fulfill(status=response.status_code,
                              content_type="application/json", body=response.content)

            browser.route("**/api/potential-customer-search/**", api)
            browser.route("**/api/health", lambda route: route.fulfill(
                status=200, content_type="application/json",
                body=api_client.get("/api/health").content,
            ))
            open_route(browser, "#find-potential-customers")
            browser.locator("#business-search-form").wait_for(state="visible")
            browser.locator("#business-campaign-name").fill("Browser prepared P1")
            choose(browser, "product_ids", ["P1"])
            browser.locator("#business-export-profile").select_option(
                request_payload()["export_profile"]
            )
            browser.locator('input[name="business_similarity_minimum"][value="0.5"]').check()
            browser.locator("#business-search-preflight").click()
            browser.wait_for_function(
                "document.querySelector('#business-search-preflight-result').textContent.includes('Not prepared')"
            )
            browser.locator("#business-search-submit").click()
            browser.wait_for_url("**/#results/1")
            browser.wait_for_function(
                "document.querySelector('#result-detail-badge').dataset.status === 'COMPLETED'",
                timeout=90000,
            )
            assert "Buyer Similarity" in browser.locator("#result-selection-details").inner_text().title()
            assert "10" in browser.locator("#result-detail-overview").inner_text()
            assert "LARGEST OBSERVED DISTANCE DRIVERS" in browser.locator("#result-profile-details").inner_text().upper()
            assert "descriptive sample only" in browser.locator("#result-profile-details").inner_text()
            assert "CURRENTNESS\nCURRENT" in browser.locator("#result-provenance-details").inner_text()
            with get_connection(database) as connection:
                assert connection.execute("SELECT COUNT(*) FROM score_calibration_artifacts").fetchone()[0] == 0
            _fixture_screenshot(browser, "v3_browser_built_result_1280")
            assert errors == []
    finally:
        app.dependency_overrides.pop(get_database_path, None)


@pytest.fixture
def v3_page(page, client):
    browser, errors, requests = page
    bodies = []

    def api(route):
        request = route.request
        parsed = urlsplit(request.url)
        requests.append((request.method, parsed.path))
        body = request.post_data
        if body and request.method == "POST":
            bodies.append((parsed.path, json.loads(body)))
        response = client.request(
            request.method, parsed.path + (f"?{parsed.query}" if parsed.query else ""),
            content=body, headers={"Content-Type": "application/json"},
        )
        route.fulfill(
            status=response.status_code, content_type="application/json",
            body=response.content,
        )

    browser.route("**/api/potential-customer-search/**", api)
    browser.route("**/api/health", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=client.get("/api/health").content,
    ))
    open_route(browser, "#find-potential-customers")
    browser.locator("#business-search-form").wait_for(state="visible")
    yield browser, errors, requests, bodies


def _fill(browser):
    browser.locator("#business-campaign-name").fill("Buyer similarity campaign")
    choose(browser, "product_ids", ["PRD-1"])
    browser.locator("#business-export-profile").select_option(
        request_payload()["export_profile"]
    )


def _fixture_screenshot(browser, name: str) -> None:
    destination = os.environ.get("LOOKALIKE_UI_EVIDENCE_DIR")
    if destination:
        target = Path(destination) / f"FIXTURE_{name}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        browser.screenshot(path=str(target), full_page=True)


@pytest.mark.browser
def test_default_v3_payload_uses_exact_products_and_cumulative_minimum(v3_page):
    browser, errors, _, bodies = v3_page
    assert browser.locator('input[name="business_score_mode"]:checked').input_value() == "similarity"
    assert browser.locator("#business-similarity-help").inner_text().find("not a purchase probability") >= 0
    assert browser.locator("#business-probability-fieldset").is_hidden()
    _fill(browser)
    browser.locator('input[name="business_similarity_minimum"][value="0.8"]').check()
    browser.locator("#business-selection-mode").select_option("TOP_N")
    browser.locator("#business-target-count").fill("25")
    _fixture_screenshot(browser, "v3_form_1280")
    browser.locator("#business-search-submit").click()
    browser.wait_for_url("**/#results/1")
    submitted = next(body for path, body in bodies if path == RUNS)
    assert submitted["selection_contract_version"] == "3"
    assert submitted["score_semantics"] == "PRODUCT_BUYER_SIMILARITY"
    assert submitted["similarity_minimum"] == .8
    assert submitted["context"]["product_ids"] == ["PRD-1"]
    assert submitted["selection_mode"] == "TOP_N" and submitted["top_n"] == 25
    assert "propensity_bucket" not in submitted
    assert "match_strength" not in submitted["criteria"]
    assert "top_matching_percent" not in submitted["criteria"]
    browser.locator("#result-detail-content").wait_for(state="visible")
    assert "Buyer Similarity" in browser.locator("#result-selection-details").inner_text().title()
    assert "not purchase probability" in browser.locator("#result-profile-details").inner_text()
    _fixture_screenshot(browser, "v3_saved_result_1280")
    browser.evaluate("""async () => {
      const result = await (await fetch('/api/potential-customer-search/runs/1/result')).json();
      const module = await import('/static/js/business-search-form.js');
      await module.restoreBusinessSearchFromResult(result);
      location.hash = '#find-potential-customers';
    }""")
    assert browser.locator('input[name="business_score_mode"]:checked').input_value() == "similarity"
    assert browser.locator("#business-selection-mode").input_value() == "TOP_N"
    assert browser.locator("#business-target-count").input_value() == "25"
    assert browser.locator("#business-product_ids").evaluate("el => [...el.selectedOptions].map(option => option.value)") == ["PRD-1"]
    assert errors == []


@pytest.mark.browser
def test_advanced_v2_request_remains_discrete_and_history_keeps_mode(v3_page):
    browser, errors, _, bodies = v3_page
    _fill(browser)
    browser.locator('input[name="business_score_mode"][value="probability"]').check()
    assert browser.locator("#business-probability-fieldset").is_visible()
    assert browser.locator("#business-top-percent").is_enabled()
    browser.locator('input[name="business_propensity_bucket"][value="0.80"]').check()
    browser.locator("#business-search-submit").click()
    browser.wait_for_url("**/#results/1")
    submitted = next(body for path, body in bodies if path == RUNS)
    assert submitted["propensity_bucket"] == "0.80"
    assert submitted["criteria"]["match_strength"] == "STRONG"
    assert "selection_contract_version" not in submitted
    assert "similarity_minimum" not in submitted
    browser.locator("#result-detail-content").wait_for(state="visible")
    assert "PURCHASE PROPENSITY" in browser.locator("#result-selection-details").inner_text()
    _fixture_screenshot(browser, "v2_saved_result_1280")
    browser.evaluate("""async () => {
      const result = await (await fetch('/api/potential-customer-search/runs/1/result')).json();
      const module = await import('/static/js/business-search-form.js');
      await module.restoreBusinessSearchFromResult(result);
      location.hash = '#find-potential-customers';
    }""")
    assert browser.locator('input[name="business_score_mode"]:checked').input_value() == "probability"
    assert browser.locator('input[name="business_propensity_bucket"]:checked').input_value() == "0.80"
    assert errors == []


@pytest.mark.browser
def test_v3_exact_demographic_bounds_do_not_change_learning_context(v3_page):
    browser, errors, _, bodies = v3_page
    _fill(browser)
    browser.locator("#business-search-form details summary").click()
    browser.locator("#business-family-min").fill("2")
    browser.locator("#business-family-max").fill("5")
    browser.locator("#business-search-submit").click()
    browser.wait_for_url("**/#results/1")
    submitted = next(body for path, body in bodies if path == RUNS)
    assert submitted["criteria"]["family_member_count_min"] == 2
    assert submitted["criteria"]["family_member_count_max"] == 5
    assert submitted["context"]["product_ids"] == ["PRD-1"]
    assert "family_member_count_min" not in submitted["context"]
    assert "family_member_count_max" not in submitted["context"]
    assert errors == []


@pytest.mark.browser
def test_late_preflight_response_cannot_replace_new_mode(v3_page, client):
    browser, errors, _, _ = v3_page
    _fill(browser)
    browser.locator('input[name="business_score_mode"][value="probability"]').check()
    pending = []

    def delay(route):
        pending.append(route)

    browser.route("**/api/potential-customer-search/preflight", delay)
    browser.locator("#business-search-preflight").click()
    browser.wait_for_function("document.querySelector('#business-search-preflight-result').textContent.includes('calibrated audience')")
    assert len(pending) == 1
    payload = json.loads(pending[0].request.post_data)
    response = client.post("/api/potential-customer-search/preflight", json=payload)
    assert response.status_code == 200
    browser.locator('input[name="business_score_mode"][value="similarity"]').check()
    pending[0].fulfill(status=200, content_type="application/json", body=response.content)
    browser.wait_for_timeout(150)
    assert "Choices changed" in browser.locator("#business-search-preflight-result").inner_text()
    assert "calibrated audience" not in browser.locator("#business-search-preflight-result").inner_text()
    assert errors == []


@pytest.mark.browser
@pytest.mark.parametrize("width", [390, 768, 1280])
def test_mode_controls_labels_keyboard_and_responsive_layout(v3_page, width):
    browser, errors, _, bodies = v3_page
    browser.set_viewport_size({"width": width, "height": 900})
    assert browser.locator('input[name="business_score_mode"]').count() == 2
    assert browser.locator('input[name="business_similarity_minimum"]').count() == 5
    assert browser.locator("#business-similarity-minimums").inner_text().find("90 and above") >= 0
    browser.locator('input[name="business_score_mode"][value="similarity"]').focus()
    browser.keyboard.press("ArrowRight")
    assert browser.locator('input[name="business_score_mode"]:checked').input_value() == "probability"
    browser.keyboard.press("ArrowLeft")
    assert browser.locator('input[name="business_score_mode"]:checked').input_value() == "similarity"
    assert browser.evaluate("document.documentElement.scrollWidth <= innerWidth")
    _fixture_screenshot(browser, f"v3_mode_controls_{width}")
    assert bodies == [] and errors == []
