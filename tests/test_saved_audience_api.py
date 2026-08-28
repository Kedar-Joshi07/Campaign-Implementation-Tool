from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.main import app


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "saved-audience-api.db"
    initialize_database(path)
    return path


@pytest.fixture
def client(database_path: Path):
    app.dependency_overrides[get_database_path] = lambda: database_path
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_saved_audience_routes_registered(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/audiences" in paths
    assert "/api/audiences/{audience_id}" in paths
    assert "/api/audiences/{audience_id}/currentness" in paths


def test_save_missing_scoring_run_maps_to_404(client: TestClient) -> None:
    response = client.post(
        "/api/audiences",
        json={
            "audience_name": "Missing Run",
            "scoring_run_id": 999,
            "filters": {},
            "selection": {"mode": "ALL_MATCHING"},
        },
    )
    assert response.status_code == 404


def test_list_saved_audiences_empty(client: TestClient) -> None:
    response = client.get("/api/audiences", params={"limit": 20, "offset": 0})
    assert response.status_code == 200
    assert response.json() == []


def test_detail_missing_audience_maps_to_404(client: TestClient) -> None:
    response = client.get("/api/audiences/1")
    assert response.status_code == 404


def test_no_export_api_registered(client: TestClient) -> None:
    response = client.get("/openapi.json")
    paths = response.json()["paths"]
    assert "/api/audiences/export" not in paths
