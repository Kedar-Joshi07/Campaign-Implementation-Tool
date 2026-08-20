from fastapi.testclient import TestClient

from app.config import APP_NAME, APP_VERSION
from app.main import app


def test_health_returns_success() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200


def test_health_payload_contains_application_details() -> None:
    with TestClient(app) as client:
        payload = client.get("/api/health").json()

    assert payload == {
        "status": "ok",
        "application": APP_NAME,
        "version": APP_VERSION,
    }


def test_version_returns_configured_version() -> None:
    with TestClient(app) as client:
        response = client.get("/api/version")

    assert response.status_code == 200
    assert response.json() == {"application": APP_NAME, "version": APP_VERSION}


def test_root_returns_application_html() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Campaign Implementation Intelligence" in response.text

