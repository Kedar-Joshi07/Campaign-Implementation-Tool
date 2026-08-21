from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.main import app
from app.repositories.historical_repository import HistoricalRepository
from tests.test_historical_analysis_service import _seed_cohort_fixture


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "private" / "historical_api.db"
    initialize_database(path)
    return path


@pytest.fixture
def client(database_path: Path):
    app.dependency_overrides[get_database_path] = lambda: database_path
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_options_and_overview_return_real_bounded_aggregates(
    client: TestClient,
    database_path: Path,
) -> None:
    _seed_cohort_fixture(database_path)

    options_response = client.get("/api/historical/options")
    overview_response = client.get("/api/historical/overview")

    assert options_response.status_code == 200
    options = options_response.json()
    assert options["available_date_from"] == "2025-01-01"
    assert options["available_date_to"] == "2025-06-15"
    assert [item["campaign_id"] for item in options["campaigns"]] == [
        "CMP_A", "CMP_B", "CMP_OUT"
    ]
    assert [item["value"] for item in options["conversion_definitions"]] == [
        "ATTRIBUTED_PURCHASE", "ANY_PURCHASE", "RESPONSE"
    ]
    assert options["defaults"]["contacted_only"] is True

    assert overview_response.status_code == 200
    overview = overview_response.json()
    assert overview["summary"]["observation_count"] == 7
    assert overview["summary"]["distinct_customer_count"] == 3
    assert len(overview["monthly_trend"]) <= 120
    assert len(overview["top_campaigns"]) <= 10
    assert all(item["engagement_rate"] <= 1 for item in overview["monthly_trend"])


@pytest.mark.parametrize(
    ("conversion_definition", "positive_count"),
    (("ATTRIBUTED_PURCHASE", 1), ("ANY_PURCHASE", 2), ("RESPONSE", 2)),
)
def test_create_supports_each_conversion_definition(
    client: TestClient,
    database_path: Path,
    conversion_definition: str,
    positive_count: int,
) -> None:
    _seed_cohort_fixture(database_path)

    response = client.post(
        "/api/historical/analyses",
        json={
            "analysis_name": "  Campaign A analysis  ",
            "campaign_ids": [" CMP_A ", "CMP_A"],
            "conversion_definition": conversion_definition,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "COMPLETED"
    assert payload["analysis_name"] == "Campaign A analysis"
    assert payload["filters"]["campaign_ids"] == ["CMP_A"]
    assert payload["filters"]["contact_date_from"] == "2025-01-01"
    assert payload["filters"]["contact_date_to"] == "2025-06-15"
    assert payload["filters"]["conversion_definition"] == conversion_definition
    assert payload["summary"]["positive_customer_count"] == positive_count
    assert payload["summary"]["positive_customer_count"] + payload["summary"][
        "unlabeled_customer_count"
    ] == payload["summary"]["selected_customer_count"]
    assert "failure_message" not in payload


def test_create_list_and_reopen_preserve_bounded_contract(
    client: TestClient,
    database_path: Path,
) -> None:
    _seed_cohort_fixture(database_path)
    created = client.post(
        "/api/historical/analyses",
        json={"campaign_ids": ["CMP_B", "CMP_A", "CMP_A"]},
    ).json()

    list_response = client.get("/api/historical/analyses", params={"limit": 1})
    reopen_response = client.get(
        f"/api/historical/analyses/{created['analysis_run_id']}"
    )

    assert list_response.status_code == 200
    item = list_response.json()[0]
    assert item["analysis_run_id"] == created["analysis_run_id"]
    assert item["filters"]["campaign_ids"] == ["CMP_A", "CMP_B"]
    assert "profiles" not in item
    assert "monthly_trend" not in item
    assert reopen_response.status_code == 200
    assert reopen_response.json() == created


@pytest.mark.parametrize(
    "payload",
    (
        {"conversion_definition": "UNKNOWN"},
        {"contact_date_from": "2025-02-01", "contact_date_to": "2025-01-01"},
        {"analysis_name": "   "},
        {"analysis_name": "x" * 121},
        {"campaign_ids": [f"CMP_{index}" for index in range(26)]},
        {"unexpected_filter": "value"},
    ),
)
def test_create_rejects_structurally_invalid_requests(
    client: TestClient,
    payload: dict,
) -> None:
    response = client.post("/api/historical/analyses", json=payload)

    assert response.status_code == 422
    assert set(response.json()) == {"detail"}


@pytest.mark.parametrize(
    "path",
    (
        "/api/historical/analyses/0",
        "/api/historical/analyses/not-an-integer",
        "/api/historical/analyses?limit=0",
        "/api/historical/analyses?limit=101",
        "/api/historical/analyses?offset=-1",
    ),
)
def test_saved_run_identifiers_and_pagination_are_validated(
    client: TestClient,
    path: str,
) -> None:
    assert client.get(path).status_code == 422


def test_zero_match_and_unknown_run_return_stable_domain_errors(
    client: TestClient,
    database_path: Path,
) -> None:
    _seed_cohort_fixture(database_path)

    zero_match = client.post(
        "/api/historical/analyses",
        json={"campaign_ids": ["CMP_MISSING"]},
    )
    unknown = client.get("/api/historical/analyses/999999")

    assert zero_match.status_code == 400
    assert zero_match.json() == {
        "detail": "No campaign observations match the selected filters."
    }
    assert unknown.status_code == 404
    assert unknown.json() == {"detail": "Historical analysis run was not found."}


def test_failed_run_is_sanitized_in_error_list_and_reopen(
    client: TestClient,
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_cohort_fixture(database_path)
    private_detail = r"C:\private\historical.db SELECT * FROM customers"

    def fail_analysis(_self, _filters):
        raise RuntimeError(private_detail)

    monkeypatch.setattr(HistoricalRepository, "analyze_cohort", fail_analysis)
    failed_create = client.post(
        "/api/historical/analyses",
        json={"analysis_name": "Expected failure"},
    )
    with get_connection(database_path) as connection:
        analysis_run_id = connection.execute(
            "SELECT MAX(analysis_run_id) FROM historical_analysis_runs"
        ).fetchone()[0]
        stored_error = connection.execute(
            "SELECT error_message FROM historical_analysis_runs WHERE analysis_run_id = ?",
            (analysis_run_id,),
        ).fetchone()[0]

    list_response = client.get("/api/historical/analyses")
    reopen_response = client.get(f"/api/historical/analyses/{analysis_run_id}")

    assert failed_create.status_code == 500
    assert failed_create.json() == {
        "detail": "The historical analysis could not be completed."
    }
    assert private_detail in stored_error
    assert list_response.status_code == 200
    assert reopen_response.status_code == 200
    assert list_response.json()[0]["failure_message"] == (
        "The historical analysis could not be completed."
    )
    assert reopen_response.json()["failure_message"] == (
        "The historical analysis could not be completed."
    )
    public_text = json.dumps(
        [failed_create.json(), list_response.json(), reopen_response.json()]
    )
    for forbidden in (private_detail, "SELECT *", "C:\\private", "error_message"):
        assert forbidden not in public_text


def test_sql_looking_value_is_bound_and_error_does_not_reflect_it(
    client: TestClient,
    database_path: Path,
) -> None:
    _seed_cohort_fixture(database_path)
    injected_value = "CMP_A') OR 1=1; SELECT * FROM customers --"

    response = client.post(
        "/api/historical/analyses",
        json={"campaign_ids": [injected_value]},
    )

    assert response.status_code == 400
    assert injected_value not in response.text
    assert "SELECT" not in response.text
    with get_connection(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 4
        assert connection.execute("SELECT COUNT(*) FROM campaign_sales").fetchone()[0] == 7


def test_public_analysis_response_contains_no_person_level_data(
    client: TestClient,
    database_path: Path,
) -> None:
    _seed_cohort_fixture(database_path)

    response = client.post("/api/historical/analyses", json={})

    assert response.status_code == 201
    public_text = response.text
    for forbidden in (
        "CUS_001", "person_id", "first_name", "last_name", "phone_number",
        "email_address", "address_line", "SELECT ", str(database_path.parent),
    ):
        assert forbidden not in public_text


def test_empty_history_has_stable_empty_and_not_ready_responses(
    client: TestClient,
) -> None:
    options = client.get("/api/historical/options")
    overview = client.get("/api/historical/overview")
    create = client.post("/api/historical/analyses", json={})

    assert options.status_code == 200
    assert options.json()["available_date_from"] is None
    assert options.json()["available_date_to"] is None
    assert options.json()["campaigns"] == []
    assert options.json()["products"] == []
    assert overview.status_code == 200
    assert overview.json()["summary"]["observation_count"] == 0
    assert overview.json()["summary"]["contact_date_from"] is None
    assert overview.json()["monthly_trend"] == []
    assert create.status_code == 400
    assert create.json() == {"detail": "Historical campaign data is not loaded."}


def test_openapi_and_phase1_routes_remain_available(client: TestClient) -> None:
    schema = client.get("/openapi.json")
    docs = client.get("/docs")

    assert schema.status_code == 200
    paths = schema.json()["paths"]
    historical_operations = {
        (path, method)
        for path, operations in paths.items()
        for method in operations
        if path.startswith("/api/historical")
    }
    assert historical_operations == {
        ("/api/historical/options", "get"),
        ("/api/historical/overview", "get"),
        ("/api/historical/analyses", "post"),
        ("/api/historical/analyses", "get"),
        ("/api/historical/analyses/{analysis_run_id}", "get"),
    }
    assert "Phase 2 aggregate historical campaign analysis" in schema.json()["info"][
        "description"
    ]
    assert docs.status_code == 200
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/version").status_code == 200
    assert client.get("/api/data/summary").status_code == 200
    assert client.get("/api/reference/campaigns").status_code == 200
