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

    assert html.count('class="navigation-item is-disabled"') == 4
    assert html.count("Later phase</small>") == 4


def test_data_status_script_renders_exact_and_approximate_policy_labels(
    client: TestClient,
) -> None:
    script = client.get("/static/js/data-status.js").text

    assert 'return "Exact target"' in script
    assert "Approximate target (±${displayTolerance}%)" in script
    assert "dataset.count_tolerance_percent" in script
    assert "125,000" not in script
    assert "5,000,000" not in script
