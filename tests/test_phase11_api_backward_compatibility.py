"""Step 16 Phase 11 API surface, errors, and compatibility contracts."""

from copy import deepcopy

import pytest

from app.main import app
from app.services import potential_customer_search_submission_service as submission
from tests.test_phase11_business_search_form import (
    RUNS,
    client,
    database_path,
    request_payload,
)


RECOMMENDED_METHODS = {
    "/api/business/overview": {"get"},
    "/api/business/recent-results": {"get"},
    "/api/potential-customer-search/options": {"get"},
    "/api/potential-customer-search/runs": {"get", "post"},
    "/api/potential-customer-search/runs/{search_run_id}": {"get"},
    "/api/potential-customer-search/runs/{search_run_id}/status": {"get"},
    "/api/potential-customer-search/runs/{search_run_id}/result": {"get"},
    "/api/potential-customer-search/runs/{search_run_id}/download": {"get"},
    "/api/export-profiles": {"get"},
}

LEGACY_PATHS = {
    "/api/health",
    "/api/version",
    "/api/data/status",
    "/api/data/summary",
    "/api/data/imports",
    "/api/reference/states",
    "/api/reference/campaigns",
    "/api/reference/products",
    "/api/historical/overview",
    "/api/historical/options",
    "/api/historical/analyses",
    "/api/models/train",
    "/api/models/{model_run_id}/score",
    "/api/audience/estimate",
    "/api/audience/search",
    "/api/audiences",
    "/api/campaigns",
    "/api/campaigns/{campaign_id}/finalize",
    "/api/campaigns/{campaign_id}/export.csv",
}


def test_openapi_exposes_complete_phase11_surface_and_preserves_legacy_paths():
    paths = app.openapi()["paths"]
    for path, methods in RECOMMENDED_METHODS.items():
        assert path in paths
        assert methods <= set(paths[path])
    assert LEGACY_PATHS <= set(paths)
    assert paths["/api/potential-customer-search/runs"]["post"][
        "responses"
    ].keys() >= {"201", "422"}
    for path in RECOMMENDED_METHODS:
        assert not path.startswith(("/api/feedback", "/api/activation"))


def test_create_get_status_and_history_share_one_safe_status_contract(client):
    created = client.post(RUNS, json=request_payload())
    assert created.status_code == 201, created.text
    payload = created.json()
    run_id = payload["search_run_id"]
    projections = [
        payload,
        client.get(f"{RUNS}/{run_id}").json(),
        client.get(f"{RUNS}/{run_id}/status").json(),
        client.get(RUNS).json()[0],
    ]
    expected_fields = {
        "search_run_id",
        "campaign_name",
        "status",
        "created_at",
        "completed_at",
        "selected_count",
        "delivery_channel",
        "export_profile",
        "safe_message",
    }
    state_order = {"QUEUED": 0, "PROCESSING": 1, "COMPLETED": 2, "BLOCKED": 2, "FAILED": 2}
    assert all(set(item) == expected_fields for item in projections)
    assert all(item["search_run_id"] == run_id for item in projections)
    assert all(item["campaign_name"] == payload["campaign_name"] for item in projections)
    assert all(item["created_at"] == payload["created_at"] for item in projections)
    assert all(item["delivery_channel"] == payload["delivery_channel"] for item in projections)
    assert all(item["export_profile"] == payload["export_profile"] for item in projections)
    assert [state_order[item["status"]] for item in projections] == sorted(
        state_order[item["status"]] for item in projections
    )


def test_repeated_intentional_identical_posts_are_distinct_but_synchronous(
    client, monkeypatch,
):
    calls: list[int] = []

    def finish_before_return(_database_path, run_id):
        calls.append(run_id)
        # The synchronous boundary returns before another HTTP submission can
        # enter this fixture, preventing detached duplicate worker creation.

    monkeypatch.setattr(submission, "PHASE11_SEARCH_EXECUTOR", finish_before_return)
    payload = request_payload()
    first = client.post(RUNS, json=payload)
    second = client.post(RUNS, json=deepcopy(payload))
    assert first.status_code == second.status_code == 201
    assert first.json()["search_run_id"] != second.json()["search_run_id"]
    assert calls == [first.json()["search_run_id"], second.json()["search_run_id"]]
    assert len(client.get(RUNS).json()) == 2


@pytest.mark.parametrize(
    "method,url,json_body,expected",
    (
        ("get", f"{RUNS}/0", None, 422),
        ("get", f"{RUNS}/999999", None, 404),
        ("get", f"{RUNS}/999999/status", None, 404),
        ("get", f"{RUNS}/999999/result", None, 404),
        ("get", f"{RUNS}/999999/download", None, 404),
        ("get", "/api/business/recent-results?limit=4", None, 422),
        ("get", "/api/business/recent-results?limit=11", None, 422),
    ),
)
def test_bounded_validation_and_missing_resources_are_422_or_404(
    client, method, url, json_body, expected,
):
    response = client.request(method, url, json=json_body)
    assert response.status_code == expected
    assert "traceback" not in response.text.lower()
    assert "select " not in response.text.lower()


def test_invalid_profile_is_422_and_incomplete_download_is_409(client):
    invalid = request_payload()
    invalid["export_profile"] = "invented-profile"
    response = client.post(RUNS, json=invalid)
    assert response.status_code == 422
    assert response.json() == {
        "detail": (
            "Review your campaign choices, targeting preferences and "
            "available download profile."
        )
    }

    created = client.post(RUNS, json=request_payload()).json()
    download = client.get(f"{RUNS}/{created['search_run_id']}/download")
    assert download.status_code == 409
    assert download.json() == {
        "detail": "The saved result is not completed and current for download."
    }


def test_unexpected_submission_failure_returns_only_safe_500(client, monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError(
            "SELECT * FROM secret C:\\private\\artifact private@example.test"
        )

    monkeypatch.setattr(submission, "submit_potential_customer_search", fail)
    response = client.post(RUNS, json=request_payload())
    assert response.status_code == 500
    assert response.json() == {
        "detail": "Your search could not be saved. Please try again."
    }
    lowered = response.text.lower()
    for prohibited in (
        "select *",
        "c:\\\\private",
        "artifact",
        "private@example.test",
        "traceback",
    ):
        assert prohibited not in lowered


def test_phase11_json_contracts_do_not_return_contact_pii_or_raw_paths(client):
    created = client.post(RUNS, json=request_payload()).json()
    responses = (
        client.get("/api/business/overview"),
        client.get("/api/business/recent-results?limit=5"),
        client.get("/api/export-profiles"),
        client.get(f"{RUNS}/{created['search_run_id']}"),
        client.get(f"{RUNS}/{created['search_run_id']}/result"),
    )
    for response in responses:
        assert response.status_code == 200, response.text
        lowered = response.text.lower()
        for value in (
            "private@example.test",
            "c:\\\\",
            "/users/",
            "traceback",
            "select *",
        ):
            assert value not in lowered
