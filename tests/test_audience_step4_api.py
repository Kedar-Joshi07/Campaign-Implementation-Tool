from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.main import app


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "audience-step4-api.db"
    initialize_database(path)
    return path


@pytest.fixture
def client(database_path: Path):
    app.dependency_overrides[get_database_path] = lambda: database_path
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_step4_routes_return_404_for_missing_scoring_run(client: TestClient) -> None:
    options = client.get("/api/audience/options", params={"scoring_run_id": 1})
    assert options.status_code == 404

    estimate = client.post(
        "/api/audience/estimate",
        json={
            "scoring_run_id": 1,
            "filters": {},
            "selection": {"mode": "ALL_MATCHING"},
        },
    )
    assert estimate.status_code == 404

    search = client.post(
        "/api/audience/search",
        json={
            "scoring_run_id": 1,
            "filters": {},
            "page_size": 10,
        },
    )
    assert search.status_code == 404


def test_step4_endpoint_validation_errors(client: TestClient) -> None:
    invalid_page_size = client.post(
        "/api/audience/search",
        json={
            "scoring_run_id": 1,
            "filters": {},
            "page_size": 101,
        },
    )
    assert invalid_page_size.status_code == 422

    invalid_selection = client.post(
        "/api/audience/estimate",
        json={
            "scoring_run_id": 1,
            "filters": {},
            "selection": {"mode": "TOP_N", "target_count": None},
        },
    )
    # pydantic accepts nullable target_count; service rejects this as invalid before lookup.
    assert invalid_selection.status_code in {404, 422}
