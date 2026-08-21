from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.main import app
from tests.test_historical_analysis_service import _seed_cohort_fixture


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "historical_ui.db"
    initialize_database(path)
    return path


@pytest.fixture
def client(database_path: Path):
    app.dependency_overrides[get_database_path] = lambda: database_path
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_historical_workspace_contains_complete_accessible_form_and_states(
    client: TestClient,
) -> None:
    html = client.get("/").text

    for control_id in (
        "analysis-name",
        "campaign-filter",
        "product-category-filter",
        "product-filter",
        "channel-filter",
        "campaign-type-filter",
        "contact-date-from",
        "contact-date-to",
        "contacted-only",
        "conversion-definition-options",
        "analyze-population",
        "historical-analysis-reset",
    ):
        assert f'id="{control_id}"' in html
    for state_id in (
        "historical-options-loading",
        "historical-analysis-empty",
        "historical-analysis-error",
        "historical-form-error",
        "analysis-running-state",
        "analysis-run-announcement",
        "recent-analyses-loading",
        "recent-analyses-empty",
        "historical-analysis-results",
    ):
        assert f'id="{state_id}"' in html
    assert html.count('role="tablist"') == 2
    assert 'tabindex="-1">Analysis results</h2>' in html
    assert "Unlabeled customers are not confirmed negatives" in html


def test_historical_results_cover_summary_breakdowns_profiles_and_saved_run(
    client: TestClient,
) -> None:
    html = client.get("/").text

    for result_id in (
        "result-observations",
        "result-selected",
        "result-positive",
        "result-unlabeled",
        "result-positive-rate",
        "result-net-sales",
        "result-gross-margin",
        "result-run-id",
        "analysis-monthly-body",
        "analysis-breakdown-bars",
        "profile-dimension",
        "profile-chart",
        "recent-analyses-body",
    ):
        assert f'id="{result_id}"' in html
    assert html.count('data-breakdown="') == 4
    assert html.count('data-profile-group="') == 4


def test_historical_script_uses_only_bounded_historical_apis_and_safe_dom(
    client: TestClient,
) -> None:
    script = client.get("/static/js/historical-analysis.js").text

    assert 'getCachedJSON("/api/historical/options"' in script
    assert 'getJSON("/api/historical/analyses"' in script
    assert 'getCachedJSON("/api/historical/analyses?limit=20&offset=0"' in script
    assert "`/api/historical/analyses/${analysisRunId}`" in script
    assert "textContent" in script
    assert "document.createElement" in script
    assert "replaceChildren" in script
    assert "innerHTML" not in script
    assert "/api/demographics" not in script
    assert "propensity" not in script.lower()
    assert "model training" not in script.lower()
    assert "person_id" not in script
    assert 'getJSON("/api/historical/overview"' not in script


def test_form_payload_maps_every_api_contract_field(client: TestClient) -> None:
    script = client.get("/static/js/historical-analysis.js").text

    for field in (
        "analysis_name",
        "campaign_ids",
        "product_ids",
        "product_categories",
        "campaign_channels",
        "campaign_types",
        "contact_date_from",
        "contact_date_to",
        "contacted_only",
        "conversion_definition",
    ):
        assert f"{field}:" in script
    assert "body: JSON.stringify(analysisPayload())" in script
    assert 'method: "POST"' in script
    assert '"Content-Type": "application/json"' in script


def test_conversion_copy_and_validation_are_explicit(client: TestClient) -> None:
    script = client.get("/static/js/historical-analysis.js").text

    assert "Confirmed attributed purchasers are known positive." in script
    assert "Any observed purchaser inside the selected cohort is known positive." in script
    assert "Any responder inside the selected cohort is known positive." in script
    assert "Analysis name must be 120 characters or fewer." in script
    assert "Contact date from must be on or before contact date to." in script
    assert "Choose no more than ${config.maximum}" in script
    assert "if (analysisRunning) return" in script
    assert "No campaign observations match the selected filters." in script


def test_retry_focus_keyboard_and_backend_status_hooks_exist(client: TestClient) -> None:
    script = client.get("/static/js/historical-analysis.js").text

    assert 'querySelector("#historical-analysis-retry")' in script
    assert "loadHistoricalAnalysis(true)" in script
    assert 'dispatchBackendStatus("is-online"' in script
    assert 'dispatchBackendStatus("is-offline"' in script
    assert 'querySelector("#analysis-results-title").focus()' in script
    assert "error.focus()" in script
    for key in ("ArrowRight", "ArrowLeft", "Home", "End"):
        assert key in script


def test_empty_database_exposes_options_and_recent_empty_contract(
    client: TestClient,
) -> None:
    options = client.get("/api/historical/options")
    recent = client.get("/api/historical/analyses?limit=20&offset=0")

    assert options.status_code == 200
    assert options.json()["available_date_from"] is None
    assert options.json()["campaigns"] == []
    assert recent.status_code == 200
    assert recent.json() == []


@pytest.mark.parametrize(
    ("conversion_definition", "expected_positive", "expected_unlabeled"),
    (
        ("ATTRIBUTED_PURCHASE", 1, 1),
        ("ANY_PURCHASE", 2, 0),
        ("RESPONSE", 2, 0),
    ),
)
def test_ui_api_journey_runs_each_conversion_definition(
    client: TestClient,
    database_path: Path,
    conversion_definition: str,
    expected_positive: int,
    expected_unlabeled: int,
) -> None:
    _seed_cohort_fixture(database_path)
    options = client.get("/api/historical/options").json()

    response = client.post(
        "/api/historical/analyses",
        json={
            **options["defaults"],
            "analysis_name": f"UI {conversion_definition}",
            "campaign_ids": ["CMP_A"],
            "conversion_definition": conversion_definition,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["summary"]["selected_customer_count"] == 2
    assert payload["summary"]["positive_customer_count"] == expected_positive
    assert payload["summary"]["unlabeled_customer_count"] == expected_unlabeled
    assert payload["summary"]["positive_customer_count"] + payload["summary"][
        "unlabeled_customer_count"
    ] == payload["summary"]["selected_customer_count"]


def test_ui_api_journey_filters_lists_and_reopens_saved_analysis(
    client: TestClient,
    database_path: Path,
) -> None:
    _seed_cohort_fixture(database_path)

    created_response = client.post(
        "/api/historical/analyses",
        json={
            "analysis_name": "Filtered UI cohort",
            "campaign_ids": ["CMP_A"],
            "product_ids": ["PRD_1"],
            "product_categories": ["Category One"],
            "campaign_channels": ["Email"],
            "campaign_types": ["Acquisition"],
            "contact_date_from": "2025-01-01",
            "contact_date_to": "2025-06-15",
            "contacted_only": True,
            "conversion_definition": "ATTRIBUTED_PURCHASE",
        },
    )
    created = created_response.json()
    recent = client.get("/api/historical/analyses?limit=20&offset=0").json()
    reopened = client.get(
        f"/api/historical/analyses/{created['analysis_run_id']}"
    ).json()

    assert created_response.status_code == 201
    assert recent[0]["analysis_run_id"] == created["analysis_run_id"]
    assert "profiles" not in recent[0]
    assert reopened == created
    public_text = json.dumps([created, recent, reopened])
    for forbidden in ("CUS_001", "person_id", "first_name", "phone_number", "SELECT "):
        assert forbidden not in public_text


def test_ui_api_journey_zero_match_is_stable_and_recoverable(
    client: TestClient,
    database_path: Path,
) -> None:
    _seed_cohort_fixture(database_path)

    response = client.post(
        "/api/historical/analyses",
        json={"campaign_ids": ["DOES_NOT_EXIST"]},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "No campaign observations match the selected filters."
    }
    recent = client.get("/api/historical/analyses?limit=20&offset=0").json()
    assert recent[0]["status"] == "FAILED"
    assert recent[0]["failure_message"] == (
        "The historical analysis could not be completed."
    )
