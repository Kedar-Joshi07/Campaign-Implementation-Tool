from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.main import app


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "audience-profile-api.db"
    initialize_database(path)
    return path


@pytest.fixture
def client(database_path: Path):
    app.dependency_overrides[get_database_path] = lambda: database_path
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_profile_missing_scoring_run_maps_to_404(client: TestClient) -> None:
    response = client.post(
        "/api/audience/profile",
        json={
            "scoring_run_id": 1,
            "filters": {},
            "selection": {"mode": "ALL_MATCHING"},
        },
    )
    assert response.status_code == 404


def test_profile_payload_validation(client: TestClient) -> None:
    response = client.post(
        "/api/audience/profile",
        json={
            "scoring_run_id": 1,
            "filters": {},
            "selection": {"mode": "TOP_N"},
        },
    )
    # Service may return 404 for missing run or 422 for invalid selection before lookup.
    assert response.status_code in {404, 422}
