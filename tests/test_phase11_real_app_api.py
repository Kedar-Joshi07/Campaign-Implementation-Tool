"""Step 7: real FastAPI lifespan and Phase 11 API integration coverage.

The Phase 11 executor and coordinator are never replaced in this module.  The
fixture prepares a small durable Phase 10 lineage before application startup so
the production coordinator can exercise reuse paths without full-scale work.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient

from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.main import app
from app.repositories.campaign_result_registry_repository import (
    CampaignResultRegistryRepository,
)
from app.repositories.campaign_targeting_context_repository import (
    CampaignTargetingContextRepository,
)
from app.services import potential_customer_search_submission_service as submission
from app.services.campaign_targeting_context_service import (
    _targeting_allowed_values,
    get_business_targeting_options,
)
from app.services.campaign_targeting_contract_service import (
    normalize_business_targeting_criteria,
)
from app.services.omnichannel_profile_contracts import get_omnichannel_profile
from app.services.phase10_context_identity_service import (
    derive_modeling_context_from_campaign_context,
)
from app.services.phase10_orchestration_service import (
    prepare_phase10_orchestration,
    run_phase10_orchestration,
)
from tests.test_phase10_orchestration_service import (
    _create_context,
    _seed_orchestration_database,
)


RUNS = "/api/potential-customer-search/runs"
RESULTS = "/api/potential-customer-search/results"
TERMINAL = {"COMPLETED", "BLOCKED", "FAILED"}


def _configure_isolated_app(
    monkeypatch: pytest.MonkeyPatch,
    database_path: Path,
    project_root: Path,
) -> None:
    """Redirect only durable paths; retain the production app composition."""

    monkeypatch.setattr("app.main.DATABASE_PATH", database_path)
    monkeypatch.setattr("app.main.PROJECT_ROOT", project_root)
    monkeypatch.setattr(
        "app.services.phase11_result_snapshot_service.DEFAULT_PROJECT_ROOT",
        project_root,
    )
    monkeypatch.setattr(
        "app.services.phase11_export_service.DEFAULT_PROJECT_ROOT", project_root
    )
    app.dependency_overrides[get_database_path] = lambda: database_path


def _run_phase10_inline(database_path: Path, orchestration_id: int, root: Path):
    return run_phase10_orchestration(
        database_path,
        orchestration_id,
        project_root=root,
        scoring_chunk_size=1_000,
        rank_chunk_size=1_000,
    )


def _prepare_phase10_fixture(
    database_path: Path,
    project_root: Path,
    targeting_context_id: int,
) -> dict:
    start = prepare_phase10_orchestration(
        database_path,
        targeting_context_id,
        project_root=project_root,
        submitter=_run_phase10_inline,
    )
    return start.orchestration


def _context_identity(database_path: Path, targeting_context_id: int) -> str:
    context = CampaignTargetingContextRepository(database_path).fetch_context(
        targeting_context_id
    )
    assert context is not None
    return derive_modeling_context_from_campaign_context(
        json.loads(context["campaign_context_json"])
    ).modeling_context_sha256


def _preseed_runtime_terminal_cases(
    database_path: Path,
    project_root: Path,
    ready_context_id: int,
) -> tuple[int, int]:
    """Create durable work that the real startup coordinator must resume."""

    repository = CampaignResultRegistryRepository(database_path)
    normalized = normalize_business_targeting_criteria(
        {
            "match_strength": "BROAD",
            "selection_mode": "ALL_MATCHING",
            "target_count": None,
        },
        allowed_values=_targeting_allowed_values(
            get_business_targeting_options(database_path)
        ),
    )

    insufficient_context_id = _create_context(database_path, product_id="P2")
    blocked_phase10 = _prepare_phase10_fixture(
        database_path, project_root, insufficient_context_id
    )
    assert blocked_phase10["status"] == "BLOCKED"
    blocked_id = repository.create_search_run(
        campaign_name="Insufficient history",
        targeting_context_id=insufficient_context_id,
        modeling_context_sha256=_context_identity(
            database_path, insufficient_context_id
        ),
        targeting_criteria=normalized.payload,
        filter_branches=list(normalized.audience_filter_branches),
        selection_mode="ALL_MATCHING",
        target_count=None,
        delivery_channel="EMAIL",
        export_profile="EMAIL_CONTACT_V1",
    )

    # This identity is valid and has READY intelligence, but the persisted
    # Audience Engine branch is deliberately unsupported.  The production safe
    # wrapper must convert the collaborator validation error into FAILED without
    # leaking its technical detail.
    failed_id = repository.create_search_run(
        campaign_name="Controlled runtime failure",
        targeting_context_id=ready_context_id,
        modeling_context_sha256=_context_identity(database_path, ready_context_id),
        targeting_criteria=normalized.payload,
        filter_branches=[{"unsupported_runtime_filter": ["fixture-value"]}],
        selection_mode="ALL_MATCHING",
        target_count=None,
        delivery_channel="EMAIL",
        export_profile="EMAIL_CONTACT_V1",
    )
    return blocked_id, failed_id


def _request_payload(*, campaign_name: str) -> dict:
    return {
        "campaign_name": campaign_name,
        "description": "Bounded real-app API integration",
        "planned_launch_date": "2026-12-01",
        "context": {
            "product_ids": ["P1"],
            "campaign_types": ["Retention"],
            "campaign_categories": ["Retention"],
            "offer_types": ["Loyalty"],
            "historical_campaign_channels": ["Email"],
            "campaign_channel": "EMAIL",
        },
        "criteria": {
            "match_strength": "BROAD",
            "selection_mode": "TOP_N",
            "target_count": 10,
        },
        "export_profile": "EMAIL_CONTACT_V1",
    }


def _poll_terminal(
    client: TestClient, search_run_id: int, *, timeout_seconds: float = 20.0
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    observed: list[str] = []
    while time.monotonic() < deadline:
        response = client.get(f"{RUNS}/{search_run_id}/status")
        assert response.status_code == 200, response.text
        payload = response.json()
        observed.append(payload["status"])
        if payload["status"] in TERMINAL:
            return payload
        time.sleep(0.1)
    raise AssertionError(
        f"search {search_run_id} did not terminate in time; observed={observed[-10:]}"
    )


def test_real_lifespan_configures_executor_and_reports_workflow_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = initialize_database(tmp_path / "runtime-wiring.db")
    _configure_isolated_app(monkeypatch, database_path, tmp_path)
    submission.reset_phase11_search_executor()
    try:
        with TestClient(app) as client:
            assert submission.PHASE11_SEARCH_EXECUTOR is not None
            options = client.get("/api/potential-customer-search/options")
            assert options.status_code == 200
            assert options.json()["workflow_available"] is True
        assert submission.PHASE11_SEARCH_EXECUTOR is None
    finally:
        app.dependency_overrides.clear()
        submission.reset_phase11_search_executor()


def test_real_app_api_reuse_failure_results_export_and_shutdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path, project_root = _seed_orchestration_database(tmp_path)
    ready_context_id = _create_context(database_path, product_id="P1")
    ready_phase10 = _prepare_phase10_fixture(
        database_path, project_root, ready_context_id
    )
    assert ready_phase10["status"] == "READY"
    blocked_id, failed_id = _preseed_runtime_terminal_cases(
        database_path, project_root, ready_context_id
    )
    _configure_isolated_app(monkeypatch, database_path, project_root)
    submission.reset_phase11_search_executor()
    repository = CampaignResultRegistryRepository(database_path)

    try:
        with TestClient(app) as client:
            assert submission.PHASE11_SEARCH_EXECUTOR is not None
            assert client.get("/api/potential-customer-search/options").json()[
                "workflow_available"
            ] is True

            first_response = client.post(
                RUNS, json=_request_payload(campaign_name="Intelligence reuse")
            )
            assert first_response.status_code == 201, first_response.text
            first_created = first_response.json()
            assert first_created["status"] in {
                "QUEUED",
                "PROCESSING",
                "COMPLETED",
            }
            assert first_created["status"] != "BLOCKED"
            first_id = first_created["search_run_id"]
            assert repository.fetch_search_run(first_id) is not None
            assert _poll_terminal(client, first_id)["status"] == "COMPLETED"
            first = repository.fetch_search_run(first_id)
            assert first is not None
            assert first["result_source"] == "INTELLIGENCE_REUSE"

            second_response = client.post(
                RUNS, json=_request_payload(campaign_name="Exact result reuse")
            )
            assert second_response.status_code == 201, second_response.text
            second_id = second_response.json()["search_run_id"]
            assert _poll_terminal(client, second_id)["status"] == "COMPLETED"
            second = repository.fetch_search_run(second_id)
            assert second is not None
            assert second["result_source"] == "EXACT_RESULT_REUSE"
            assert second["result_snapshot_id"] == first["result_snapshot_id"]

            blocked = _poll_terminal(client, blocked_id)
            assert blocked["status"] == "BLOCKED"
            assert "not connected" not in blocked["safe_message"].lower()

            failed = _poll_terminal(client, failed_id)
            assert failed["status"] == "FAILED"
            assert failed["safe_message"] == (
                "Your search could not be completed. It remains saved in Results; "
                "please try again."
            )
            failed_row = repository.fetch_search_run(failed_id)
            assert failed_row["safe_error_message"] == (
                "The search could not be completed. Please try again."
            )
            assert "unsupported_runtime_filter" not in failed_row[
                "safe_error_message"
            ]

            history_response = client.get(RESULTS)
            assert history_response.status_code == 200, history_response.text
            history = history_response.json()
            by_id = {item["search_run_id"]: item for item in history}
            assert by_id[first_id]["result_source"] == "INTELLIGENCE_REUSE"
            assert by_id[second_id]["result_source"] == "EXACT_RESULT_REUSE"
            assert by_id[blocked_id]["status"] == "BLOCKED"
            assert by_id[failed_id]["status"] == "FAILED"

            detail_response = client.get(f"{RUNS}/{second_id}/result")
            assert detail_response.status_code == 200, detail_response.text
            detail = detail_response.json()
            assert detail["status"] == "COMPLETED"
            assert detail["result_source"] == "EXACT_RESULT_REUSE"
            assert detail["currentness"] == "CURRENT"
            assert detail["download_eligible"] is True
            assert detail["snapshot_provenance"]["result_snapshot_id"] == second[
                "result_snapshot_id"
            ]

            download = client.get(f"{RUNS}/{second_id}/download")
            assert download.status_code == 200, download.text
            assert download.headers["x-export-profile"] == "EMAIL_CONTACT_V1"
            rows = list(csv.reader(io.StringIO(download.text)))
            profile = get_omnichannel_profile("EMAIL_CONTACT_V1")
            assert tuple(rows[0]) == profile.output_columns
            event = repository.list_export_events(second_id)[0]
            assert event["status"] == "COMPLETED"
            assert event["row_count"] == len(rows) - 1
            assert event["row_count"] == event["deliverable_count"]
            assert event["selected_count"] == (
                event["deliverable_count"] + event["undeliverable_count"]
            )
            assert event["currentness_state"] == "CURRENT"

        # Lifespan shutdown owns executor disconnection and bounded pool closure.
        assert submission.PHASE11_SEARCH_EXECUTOR is None
        for search_run_id in (first_id, second_id, blocked_id, failed_id):
            assert repository.fetch_search_run(search_run_id)["status"] in TERMINAL
    finally:
        app.dependency_overrides.clear()
        submission.reset_phase11_search_executor()
