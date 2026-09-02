from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.routers.campaigns as campaigns_router_module
from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.main import app
from app.services.campaign_service import CampaignServiceUnavailableError
from app.services.saved_audience_service import save_audience
from app.services.audience_preparation_service import run_audience_rank_preparation
from tests.test_saved_audience_service import _seed_fixture


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "campaign-api.db"
    initialize_database(path)
    return path


@pytest.fixture
def client(database_path: Path):
    app.dependency_overrides[get_database_path] = lambda: database_path
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _create_current_saved_audience(database_path: Path) -> int:
    scoring_run_id = _seed_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)
    saved = save_audience(
        database_path,
        {
            "audience_name": "Campaign API Fixture",
            "description": "Seed audience for campaign API integration tests",
            "scoring_run_id": scoring_run_id,
            "filters": {"state": ["California", "Texas"]},
            "selection": {"mode": "TOP_N", "target_count": 4},
            "include_profile_snapshot": True,
        },
    )
    return int(saved["audience_id"])


def test_campaign_routes_registered(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200

    paths = response.json()["paths"]
    assert "/api/campaigns/options" in paths
    assert "/api/campaigns" in paths
    assert "/api/campaigns/{campaign_id}" in paths
    assert "/api/campaigns/{campaign_id}/currentness" in paths
    assert "/api/campaigns/{campaign_id}/finalize" in paths
    assert "/api/campaigns/{campaign_id}/exports" in paths
    assert "/api/campaigns/{campaign_id}/export.csv" in paths


def test_campaign_options_and_list_empty(database_path: Path, client: TestClient) -> None:
    options_response = client.get("/api/campaigns/options")
    assert options_response.status_code == 200
    options = options_response.json()

    assert options["campaign_contract_version"] == "1"
    assert options["export_contract_version"] == "1"
    assert options["member_resolution_contract_version"] == "1"
    assert options["supported_channels"] == ["EMAIL", "DIRECT_MAIL"]
    assert options["eligible_saved_audiences"] == []

    list_response = client.get("/api/campaigns", params={"limit": 20, "offset": 0})
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_campaign_create_missing_saved_audience_maps_to_404(client: TestClient) -> None:
    response = client.post(
        "/api/campaigns",
        json={
            "campaign_name": "Missing audience",
            "description": "Should fail",
            "channel": "EMAIL",
            "planned_launch_date": "2026-10-01",
            "saved_audience_id": 999_999,
        },
    )
    assert response.status_code == 404


def test_campaign_workflow_finalize_and_export(database_path: Path, client: TestClient) -> None:
    saved_audience_id = _create_current_saved_audience(database_path)

    create_response = client.post(
        "/api/campaigns",
        json={
            "campaign_name": "Section 2 Campaign",
            "description": "Email audience export",
            "channel": "EMAIL",
            "planned_launch_date": "2026-10-12",
            "saved_audience_id": saved_audience_id,
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    campaign_id = int(created["campaign_id"])

    assert created["status"] == "DRAFT"
    assert created["saved_audience_id"] == saved_audience_id
    assert created["currentness"]["ready_for_finalize"] is True
    assert created["currentness"]["ready_for_export"] is False

    detail_response = client.get(f"/api/campaigns/{campaign_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()

    forbidden_detail_keys = {
        "first_name",
        "last_name",
        "email",
        "address_line_1",
        "address_line_2",
        "postal_code",
    }
    assert forbidden_detail_keys.isdisjoint(set(detail.keys()))

    update_response = client.patch(
        f"/api/campaigns/{campaign_id}",
        json={
            "campaign_name": "Section 2 Campaign Updated",
            "description": "Updated draft description",
            "channel": "EMAIL",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["campaign_name"] == "Section 2 Campaign Updated"

    finalize_response = client.post(f"/api/campaigns/{campaign_id}/finalize")
    assert finalize_response.status_code == 200
    finalized = finalize_response.json()
    assert finalized["status"] == "FINALIZED"
    assert finalized["currentness"]["ready_for_export"] is True

    finalize_again = client.post(f"/api/campaigns/{campaign_id}/finalize")
    assert finalize_again.status_code == 409

    no_ack_export = client.get(f"/api/campaigns/{campaign_id}/export.csv")
    assert no_ack_export.status_code == 422

    export_response = client.get(
        f"/api/campaigns/{campaign_id}/export.csv",
        params={"acknowledge_pii": "true"},
    )
    assert export_response.status_code == 200
    assert export_response.headers["content-type"].startswith("text/csv")

    lines = [line for line in export_response.text.splitlines() if line.strip()]
    assert lines
    assert lines[0].split(",") == [
        "person_id",
        "propensity_score",
        "percentile_bucket",
        "decile",
        "rank_band",
        "first_name",
        "last_name",
        "email",
    ]

    exports_response = client.get(f"/api/campaigns/{campaign_id}/exports", params={"limit": 50})
    assert exports_response.status_code == 200
    events = exports_response.json()
    assert events

    latest = events[0]
    assert latest["status"] == "COMPLETED"
    assert latest["selected_count"] == created["saved_audience_resolved_count"]
    assert latest["deliverable_count"] + latest["undeliverable_count"] == latest["selected_count"]
    assert latest["row_count"] == latest["deliverable_count"]
    assert isinstance(latest["csv_sha256"], str) and len(latest["csv_sha256"]) == 64


def test_campaign_router_maps_unavailable_to_503(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_unavailable(*_args, **_kwargs):
        raise CampaignServiceUnavailableError("Campaign backend temporarily unavailable.")

    monkeypatch.setattr(campaigns_router_module, "get_campaign_options", _raise_unavailable)

    response = client.get("/api/campaigns/options")
    assert response.status_code == 503
    assert "Campaign backend temporarily unavailable." in response.json()["detail"]
