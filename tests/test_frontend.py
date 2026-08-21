from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.main import app


@pytest.fixture
def client(tmp_path: Path):
    database_path = tmp_path / "frontend.db"
    initialize_database(database_path)
    app.dependency_overrides[get_database_path] = lambda: database_path
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_frontend_contains_functional_phase_one_views(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'data-view="overview"' in response.text
    assert 'data-view="data-status"' in response.text
    assert "Historical customers" in response.text
    assert "Recent runs" in response.text
    assert "Campaign readiness, grounded in real data." in response.text
    assert response.text.count('data-field="policy"') == 3
    assert "125,000" not in response.text
    assert "5,000,000" not in response.text


@pytest.mark.parametrize(
    "asset_path",
    (
        "/static/css/main.css",
        "/static/css/components.css",
        "/static/js/api.js",
        "/static/js/ui.js",
        "/static/js/overview.js",
        "/static/js/historical-overview.js",
        "/static/js/historical-analysis.js",
        "/static/js/data-status.js",
        "/static/js/app.js",
    ),
)
def test_frontend_assets_are_served(client: TestClient, asset_path: str) -> None:
    response = client.get(asset_path)

    assert response.status_code == 200
    assert response.text


def test_later_phase_navigation_is_visibly_disabled(client: TestClient) -> None:
    html = client.get("/").text

    assert html.count('class="navigation-item is-disabled"') == 3
    assert html.count("Later phase</small>") == 3
    assert "Model Training" in html
    assert "Audience Explorer" in html
    assert "Campaigns" in html


def test_historical_analysis_navigation_and_workspace_are_enabled(
    client: TestClient,
) -> None:
    html = client.get("/").text

    assert html.count('data-view-target="historical-analysis"') == 2
    assert 'id="historical-analysis-cta"' in html
    assert "Analyze historical campaigns" in html
    assert 'data-view="historical-analysis"' in html
    assert 'id="historical-analysis-form"' in html
    assert "Analyze Population" in html
    assert "Recent Analyses" in html


def test_historical_overview_has_three_accessible_visuals_and_all_states(
    client: TestClient,
) -> None:
    html = client.get("/").text

    assert html.count('class="historical-chart-card"') == 3
    assert 'id="historical-overview-loading"' in html
    assert 'id="historical-overview-empty"' in html
    assert 'id="historical-overview-unavailable"' in html
    assert 'id="historical-monthly-data" class="visually-hidden"' in html
    assert "Monthly attributed purchases" in html
    assert "Campaign channel performance" in html
    assert "Product-category performance" in html
    assert 'id="overview-retry"' in html


def test_historical_overview_script_uses_api_cache_and_safe_dom_rendering(
    client: TestClient,
) -> None:
    historical_script = client.get("/static/js/historical-overview.js").text
    overview_script = client.get("/static/js/overview.js").text

    assert 'import { getCachedJSON } from "./api.js"' in historical_script
    assert 'getCachedJSON("/api/historical/overview"' in historical_script
    assert "loadHistoricalOverview(force)" in overview_script
    assert "textContent" in historical_script
    assert "document.createElement" in historical_script
    assert "document.createElementNS" in historical_script
    assert "replaceChildren" in historical_script
    assert "innerHTML" not in historical_script
    assert "Unknown/Other" in historical_script
    assert "setVisibility({ loading: true })" in historical_script
    assert "setVisibility({ empty: true })" in historical_script
    assert "setVisibility({ unavailable: true })" in historical_script
    assert "570000" not in historical_script
    assert "34273" not in historical_script


def test_overview_retry_restores_global_backend_status_after_success(
    client: TestClient,
) -> None:
    overview_script = client.get("/static/js/overview.js").text

    assert 'querySelector("#overview-retry")' in overview_script
    assert "loadOverview(true)" in overview_script
    assert 'state: "is-offline"' in overview_script
    assert 'state: "is-online"' in overview_script
    assert "hideError(errorBanner)" in overview_script


def test_data_status_script_renders_exact_and_approximate_policy_labels(
    client: TestClient,
) -> None:
    script = client.get("/static/js/data-status.js").text

    assert 'return "Exact target"' in script
    assert "Approximate target (±${displayTolerance}%)" in script
    assert "dataset.count_tolerance_percent" in script
    assert "125,000" not in script
    assert "5,000,000" not in script
