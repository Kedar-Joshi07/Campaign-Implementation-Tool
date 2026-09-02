import asyncio
import logging
from pathlib import Path

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app import config
from app.config import APP_NAME, APP_VERSION
from app.database.connection import get_connection
from app.database.schema import CURRENT_SCHEMA_VERSION, initialize_database
from app.dependencies import get_database_path
from app.main import app, unexpected_exception_handler


@pytest.fixture
def client(tmp_path: Path):
    database_path = tmp_path / "health.db"
    initialize_database(database_path)
    app.dependency_overrides[get_database_path] = lambda: database_path
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health_returns_success(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200


def test_health_payload_contains_application_and_database_details(client: TestClient) -> None:
    payload = client.get("/api/health").json()

    assert payload == {
        "status": "ok",
        "application_status": "ok",
        "database_status": "connected",
        "schema_status": "ready",
        "missing_tables": [],
        "application": APP_NAME,
        "version": APP_VERSION,
    }


def test_version_returns_configured_version(client: TestClient) -> None:
    response = client.get("/api/version")

    assert response.status_code == 200
    assert response.json() == {"application": APP_NAME, "version": APP_VERSION}


def test_root_returns_application_html(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Campaign Implementation Intelligence" in response.text


def test_health_reports_unavailable_database(tmp_path: Path) -> None:
    unavailable_path = tmp_path / "directory-not-database"
    unavailable_path.mkdir()
    app.dependency_overrides[get_database_path] = lambda: unavailable_path
    try:
        with TestClient(app) as test_client:
            response = test_client.get("/api/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["database_status"] == "unavailable"
    assert response.json()["schema_status"] == "unknown"


def test_application_startup_runs_stale_job_reconciliation_and_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def fake_reconcile(database_path: Path) -> int:
        observed["database_path"] = database_path
        return 0

    def fake_shutdown(*, wait: bool) -> None:
        observed["wait"] = wait

    monkeypatch.setattr("app.main.reconcile_stale_model_training_jobs", fake_reconcile)
    monkeypatch.setattr("app.main.shutdown_model_training_executor", fake_shutdown)

    with TestClient(app):
        pass

    assert "database_path" in observed
    assert observed["wait"] is False


def test_application_startup_tolerates_reconciliation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_reconcile(_database_path: Path) -> int:
        raise RuntimeError("forced startup reconciliation failure")

    monkeypatch.setattr(
        "app.main.reconcile_stale_model_training_jobs",
        failing_reconcile,
    )

    with TestClient(app):
        pass


def test_first_normal_database_access_initializes_current_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "first-access.db"
    monkeypatch.setattr(config, "DATABASE_PATH", database_path)

    assert get_database_path() == database_path

    with get_connection(database_path) as connection:
        schema_version = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]

    assert schema_version == str(CURRENT_SCHEMA_VERSION)


def test_unexpected_api_exception_is_logged_and_sanitized(
    caplog: pytest.LogCaptureFixture,
) -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
        }
    )

    with caplog.at_level(logging.ERROR):
        response = asyncio.run(
            unexpected_exception_handler(request, RuntimeError("sensitive detail"))
        )

    assert response.status_code == 500
    assert response.body == b'{"detail":"An unexpected application error occurred."}'
    assert "Unexpected API failure" in caplog.text
