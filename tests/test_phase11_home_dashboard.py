"""Step 14 business Home dashboard API and real-browser coverage."""

from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from app.database.connection import get_connection
from app.repositories.campaign_result_registry_repository import (
    CampaignResultRegistryRepository,
)
from app.repositories.phase10_intelligence_repository import (
    Phase10IntelligenceRepository,
)
from app.services import potential_customer_search_submission_service as submission
from app.services.phase10_context_identity_service import (
    derive_modeling_context_from_campaign_context,
)
from app.services.phase11_result_snapshot_service import materialize_result_snapshot
from app.services.audience_preparation_service import classify_decile, classify_rank_band
from tests.test_phase10_schema_registry_repository import _generation_values, _seed_lineage
from tests.test_phase11_business_navigation import browser_session, open_route, page
from tests.test_phase11_business_search_form import client, database_path, request_payload


OVERVIEW = "/api/business/overview"
RECENT = "/api/business/recent-results"


def _complete_one_result(database_path: Path, client, monkeypatch) -> tuple[int, int]:
    ids = _seed_lineage(database_path)
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "UPDATE data_import_runs SET rows_read=?, rows_inserted=? "
            "WHERE import_id=?",
            (5_000_000, 5_000_000, ids["demographic_import_id"]),
        )

    monkeypatch.setattr(submission, "PHASE11_SEARCH_EXECUTOR", lambda *_: None)
    first_payload = request_payload()
    first = client.post("/api/potential-customer-search/runs", json=first_payload).json()
    repository = CampaignResultRegistryRepository(database_path)
    run = repository.fetch_search_run(first["search_run_id"])

    values = _generation_values(ids)
    identity = derive_modeling_context_from_campaign_context(first_payload["context"])
    values["modeling_context_json"] = identity.canonical_json
    values["modeling_context_sha256"] = identity.modeling_context_sha256
    generation_id = Phase10IntelligenceRepository(database_path).insert_ready_generation(values)
    generation = Phase10IntelligenceRepository(database_path).fetch_generation(generation_id)
    members = [
        {
            "person_id": f"P-{index}",
            "propensity_score": 0.9 - (index / 100),
            "percentile_bucket": index,
            "decile": classify_decile(index),
            "rank_band": classify_rank_band(index),
        }
        for index in range(1, 8)
    ]
    snapshot_id = materialize_result_snapshot(
        database_path,
        run,
        generation,
        "e" * 64,
        None,
        members,
        project_root=database_path.parent,
    )
    repository.mark_processing(first["search_run_id"])
    repository.complete_search_run(
        first["search_run_id"],
        result_snapshot_id=snapshot_id,
        result_source="NEW_INTELLIGENCE_BUILD",
    )

    second_payload = deepcopy(first_payload)
    second_payload["campaign_name"] = "Newest saved search"
    second = client.post(
        "/api/potential-customer-search/runs", json=second_payload
    ).json()
    repository.fail_search_run(second["search_run_id"], blocked=True)
    return first["search_run_id"], second["search_run_id"]


def test_business_dashboard_uses_metadata_counts_and_bounded_newest_results(
    client, database_path, monkeypatch,
):
    completed_id, newest_id = _complete_one_result(
        database_path, client, monkeypatch
    )

    response = client.get(OVERVIEW)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "potential_customers_available": 5_000_000,
        "search_runs": 2,
        "completed_results": 1,
        "latest_result_count": 7,
    }

    recent = client.get(RECENT, params={"limit": 5})
    assert recent.status_code == 200, recent.text
    assert [row["search_run_id"] for row in recent.json()] == [
        newest_id, completed_id,
    ]
    assert recent.json()[0]["campaign_name"] == "Newest saved search"
    assert recent.json()[1]["delivery_profile_label"] == "Email"
    assert recent.json()[1]["selected_count"] == 7
    assert set(recent.json()[0]) == {
        "search_run_id", "campaign_name", "created_at", "completed_at",
        "status", "selected_count", "delivery_profile_label", "safe_message",
    }
    assert client.get(RECENT, params={"limit": 4}).status_code == 422
    assert client.get(RECENT, params={"limit": 11}).status_code == 422


def test_dashboard_repository_never_queries_population_or_membership_tables() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "app/repositories/business_dashboard_repository.py"
    ).read_text(encoding="utf-8").lower()
    for forbidden in (
        "from demographics", "from scored_prospects", "from audience_members",
        "from campaign_result_members",
    ):
        assert forbidden not in source
    assert "from data_import_runs" in source
    assert "limit ?" in source


def _recent_payload(run_id: int, *, status: str, count: int | None) -> dict:
    return {
        "search_run_id": run_id,
        "campaign_name": f"Campaign {run_id}",
        "created_at": "2026-09-17T08:00:00Z",
        "completed_at": "2026-09-17T08:00:05Z" if status == "COMPLETED" else None,
        "status": status,
        "selected_count": count,
        "delivery_profile_label": "Email",
        "safe_message": "Potential-customer results are ready."
        if status == "COMPLETED" else "Preparing potential-customer results.",
    }


@pytest.mark.browser
def test_home_renders_business_cards_recent_results_and_primary_actions(page):
    browser, errors, requests = page
    browser.route(
        "**/api/health",
        lambda route: route.fulfill(status=200, json={
            "status": "ok", "version": "0.1.0",
        }),
    )
    browser.route(
        "**/api/business/overview",
        lambda route: route.fulfill(status=200, json={
            "potential_customers_available": 5_000_000,
            "search_runs": 12,
            "completed_results": 9,
            "latest_result_count": 28_450,
        }),
    )
    browser.route(
        "**/api/business/recent-results?limit=5",
        lambda route: route.fulfill(status=200, json=[
            _recent_payload(42, status="COMPLETED", count=28_450),
            _recent_payload(41, status="PROCESSING", count=None),
        ]),
    )

    open_route(browser, "#home")
    browser.locator("#home-recent-results .home-result-card").first.wait_for()
    assert browser.locator("#home-potential-customers").inner_text() == "5,000,000"
    assert browser.locator("#home-search-runs").inner_text() == "12"
    assert browser.locator("#home-completed-results").inner_text() == "9"
    assert browser.locator("#home-latest-result-count").inner_text() == "28,450"
    assert browser.locator(".home-result-card").count() == 2
    first = browser.locator(".home-result-card").first
    assert "Campaign 42" in first.inner_text()
    assert "Completed" in first.inner_text()
    assert "28,450" in first.inner_text()
    assert "Email" in first.inner_text()
    assert first.get_by_role("link", name="View Result").get_attribute("href") == "#results/42"
    visible = browser.locator("#overview-view").inner_text()
    for prohibited in (
        "model id", "analysis id", "scoring id", "pu count", "artifact",
        "rank boundary", "database", "schema", "reconciliation",
    ):
        assert prohibited not in visible.lower()
    assert browser.locator("#backend-status").get_attribute("class").endswith("is-online")
    assert not any(path in {
        "/api/data/summary", "/api/data/status", "/api/historical/overview",
    } for _, path in requests)
    browser.locator("#home-find-potential-customers").click()
    browser.wait_for_url("**/#find-potential-customers")
    assert errors == []


@pytest.mark.browser
def test_home_unavailable_retry_recovers_dashboard_and_global_status(page):
    browser, errors, _requests = page
    available = {"value": False}

    def health(route):
        if available["value"]:
            route.fulfill(status=200, json={"status": "ok", "version": "0.1.0"})
        else:
            route.fulfill(status=503, json={"detail": "Temporarily unavailable"})

    def overview(route):
        if available["value"]:
            route.fulfill(status=200, json={
                "potential_customers_available": 250,
                "search_runs": 0,
                "completed_results": 0,
                "latest_result_count": None,
            })
        else:
            route.fulfill(status=503, json={"detail": "Temporarily unavailable"})

    browser.route("**/api/health", health)
    browser.route("**/api/business/overview", overview)
    browser.route(
        "**/api/business/recent-results?limit=5",
        lambda route: route.fulfill(status=200, json=[]),
    )
    open_route(browser, "#home")
    browser.locator("#overview-error").wait_for(state="visible")
    assert "temporarily unavailable" in browser.locator("#overview-error").inner_text().lower()
    assert browser.locator("#backend-status").get_attribute("class").endswith("is-offline")

    available["value"] = True
    browser.locator("#overview-retry").click()
    browser.locator("#home-potential-customers").get_by_text("250").wait_for()
    assert browser.locator("#overview-error").is_hidden()
    assert browser.locator("#home-results-empty").is_visible()
    assert browser.locator("#backend-status").get_attribute("class").endswith("is-online")
    # Expected console logging is not a page execution error.
    assert errors == []
