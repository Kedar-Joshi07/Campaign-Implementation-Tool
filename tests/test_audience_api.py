from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.routers.models as models_router_module
from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.main import app


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "audience-api.db"
    initialize_database(path)
    return path


@pytest.fixture
def client(database_path: Path):
    app.dependency_overrides[get_database_path] = lambda: database_path
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_audience_routes_are_registered(client: TestClient) -> None:
    openapi_response = client.get("/openapi.json")
    assert openapi_response.status_code == 200
    paths = openapi_response.json()["paths"]
    assert "/api/audience/options" in paths
    assert "/api/audience/estimate" in paths
    assert "/api/audience/search" in paths
    assert "/api/audience/profile" in paths
    assert "/api/audience/runs/{scoring_run_id}/prepare" in paths
    assert "/api/audience/runs/{scoring_run_id}/preparation-status" in paths
    assert "/api/audience/runs" in paths
    assert "/api/audiences" in paths
    assert "/api/audiences/{audience_id}" in paths
    assert "/api/audiences/{audience_id}/currentness" in paths


def test_prepare_and_status_missing_run_map_to_404(client: TestClient) -> None:
    prepare_response = client.post(
        "/api/audience/runs/1/prepare",
        json={"rank_contract_version": "1"},
    )
    assert prepare_response.status_code == 404

    status_response = client.get("/api/audience/runs/1/preparation-status")
    assert status_response.status_code == 404


def test_list_runs_empty_returns_200(client: TestClient) -> None:
    response = client.get("/api/audience/runs", params={"limit": 20, "offset": 0})
    assert response.status_code == 200
    assert response.json() == []


def test_prepare_validation_for_bad_body(client: TestClient) -> None:
    response = client.post("/api/audience/runs/9/prepare", json={"rank_contract_version": ""})
    assert response.status_code == 422


def test_preparation_status_response_includes_readiness_fields(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        models_router_module,
        "get_audience_run_preparation_status",
        lambda *_args, **_kwargs: {
            "scoring_run_id": 8,
            "model_run_id": 8,
            "status": "COMPLETED",
            "rank_contract_version": "1",
            "prepared": True,
            "is_canonical": True,
            "source_verified": True,
            "ready_for_current_audience_actions": True,
            "currentness_issues": [],
            "boundary_count": 100,
            "total_population": 5000000,
            "active_job": None,
        },
    )

    response = client.get("/api/audience/runs/8/preparation-status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["prepared"] is True
    assert payload["is_canonical"] is True
    assert payload["source_verified"] is True
    assert payload["ready_for_current_audience_actions"] is True
    assert payload["currentness_issues"] == []


def test_preparation_runs_list_includes_stale_but_visible_runs(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        models_router_module,
        "list_audience_run_preparation_summaries",
        lambda *_args, **_kwargs: [
            {
                "scoring_run_id": 9,
                "model_run_id": 8,
                "completed_at": "2026-09-11T01:00:00Z",
                "scored_person_count": 5000000,
                "prepared": True,
                "is_canonical": False,
                "source_verified": False,
                "ready_for_current_audience_actions": False,
                "currentness_issues": ["Demographic source provenance is stale for this scoring run."],
                "rank_contract_version": "1",
                "boundary_count": 100,
            }
        ],
    )

    response = client.get("/api/audience/runs", params={"limit": 20, "offset": 0})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["prepared"] is True
    assert payload[0]["ready_for_current_audience_actions"] is False
    assert payload[0]["currentness_issues"]
