from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.main import app
from app.repositories.historical_repository import HistoricalRepository
from app.routers import historical as historical_router
from tests.test_historical_analysis_service import _seed_cohort_fixture


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "phase2_hardening.db"
    initialize_database(path)
    _seed_cohort_fixture(path)
    return path


@pytest.fixture
def client(database_path: Path):
    app.dependency_overrides[get_database_path] = lambda: database_path
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("field", "maximum", "matching_value"),
    (
        ("campaign_ids", 25, "CMP_A"),
        ("product_ids", 50, "PRD_1"),
        ("product_categories", 25, "Category One"),
        ("campaign_channels", 20, "Email"),
        ("campaign_types", 20, "Acquisition"),
    ),
)
def test_each_analysis_list_accepts_its_limit_and_rejects_one_above(
    client: TestClient,
    field: str,
    maximum: int,
    matching_value: str,
) -> None:
    at_limit = [matching_value, *(f"UNUSED_{index:03d}" for index in range(maximum - 1))]
    above_limit = [*at_limit, "UNUSED_OVER_LIMIT"]

    accepted = client.post(
        "/api/historical/analyses",
        json={"analysis_name": f"Boundary for {field}", field: at_limit},
    )
    rejected = client.post(
        "/api/historical/analyses",
        json={"analysis_name": f"Over boundary for {field}", field: above_limit},
    )

    assert accepted.status_code == 201
    assert len(accepted.json()["filters"][field]) == maximum
    assert rejected.status_code == 422
    assert set(rejected.json()) == {"detail"}


def test_narrow_campaign_product_filter_predicates_remain_indexable() -> None:
    filters = {
        "campaign_ids": ["CMP_A"],
        "product_ids": ["PRD_1"],
        "product_categories": [],
        "campaign_channels": [],
        "campaign_types": [],
        "contact_date_from": "2025-01-01",
        "contact_date_to": "2025-06-15",
        "contacted_only": True,
        "conversion_definition": "ATTRIBUTED_PURCHASE",
    }
    cte, parameters = HistoricalRepository._matching_cte(filters)

    assert "campaign_id IN (?)" in cte
    assert "product_id IN (?)" in cte
    assert "TRIM(campaign_id)" not in cte
    assert "TRIM(product_id)" not in cte
    assert parameters[:2] == ("CMP_A", "PRD_1")


@pytest.mark.parametrize(
    "date_payload",
    (
        {"contact_date_from": "2024-12-31"},
        {"contact_date_to": "2025-06-16"},
        {
            "contact_date_from": "2024-12-31",
            "contact_date_to": "2026-01-01",
        },
    ),
)
def test_out_of_range_dates_return_a_stable_validation_response(
    client: TestClient,
    date_payload: dict[str, str],
) -> None:
    response = client.post("/api/historical/analyses", json=date_payload)

    assert response.status_code == 422
    assert response.json() == {
        "detail": (
            "Historical analysis dates must be within the available "
            "contact-date range."
        )
    }


def test_locked_database_error_is_logged_and_publicly_sanitized(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_detail = r"database is locked at C:\private\campaign_poc.db"

    def fail_insert(_self, **_kwargs):
        raise sqlite3.OperationalError(private_detail)

    monkeypatch.setattr(HistoricalRepository, "insert_analysis_run", fail_insert)
    with caplog.at_level(logging.ERROR):
        response = client.post(
            "/api/historical/analyses",
            json={"analysis_name": "Locked database"},
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": (
            "The database request could not be completed. Verify database "
            "initialization and availability."
        )
    }
    assert private_detail not in response.text
    assert private_detail in caplog.text


def test_unexpected_service_error_is_logged_and_publicly_sanitized(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_detail = r"unexpected SELECT detail at C:\private\campaign_poc.db"

    def fail_overview(_database_path):
        raise RuntimeError(private_detail)

    monkeypatch.setattr(historical_router, "get_historical_overview", fail_overview)
    with caplog.at_level(logging.ERROR):
        response = client.get("/api/historical/overview")

    assert response.status_code == 500
    assert response.json() == {"detail": "An unexpected application error occurred."}
    assert private_detail not in response.text
    assert private_detail in caplog.text


def test_corrupt_saved_json_returns_only_the_stable_public_error(
    client: TestClient,
    database_path: Path,
) -> None:
    created = client.post(
        "/api/historical/analyses",
        json={"analysis_name": "Corrupt snapshot boundary"},
    ).json()
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "UPDATE historical_analysis_runs SET results_json = ? "
            "WHERE analysis_run_id = ?",
            ('{"summary": NaN}', created["analysis_run_id"]),
        )

    response = client.get(
        f"/api/historical/analyses/{created['analysis_run_id']}"
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "The saved historical analysis could not be read."
    }
    assert "NaN" not in response.text
