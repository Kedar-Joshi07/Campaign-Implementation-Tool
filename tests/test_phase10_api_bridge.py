from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.dependencies import get_database_path
from app.main import app
from app.repositories.phase10_intelligence_repository import (
    Phase10IntelligenceRepository,
)
from app.services.phase10_orchestration_service import (
    SAFE_FAILURE_MESSAGE,
    run_phase10_orchestration,
)
from tests.test_phase10_orchestration_service import _seed_orchestration_database


def _context(*, delivery_channel: str = "EMAIL") -> dict[str, Any]:
    return {
        "product_ids": ["P1"],
        "campaign_types": ["Retention"],
        "campaign_categories": ["Retention"],
        "offer_types": ["Loyalty"],
        "campaign_channel": delivery_channel,
        "historical_campaign_channels": ["Email"],
    }


def _assert_no_pii_keys(value: Any) -> None:
    forbidden = {
        "first",
        "first_name",
        "last",
        "last_name",
        "email",
        "phone",
        "address",
        "street",
        "city",
        "postal",
        "postal_code",
        "date_of_birth",
        "customer_id",
        "person_id",
    }
    if isinstance(value, dict):
        assert forbidden.isdisjoint(value)
        for child in value.values():
            _assert_no_pii_keys(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_pii_keys(child)


@pytest.fixture
def phase10_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    database_path, project_root = _seed_orchestration_database(tmp_path)

    def run_inline(path, orchestration_id, root):
        return run_phase10_orchestration(
            path,
            orchestration_id,
            project_root=root,
            artifact_root=Path("artifacts/models"),
        )

    monkeypatch.setattr(
        "app.services.phase10_api_service.DEFAULT_PROJECT_ROOT", project_root
    )
    monkeypatch.setattr(
        "app.services.phase10_api_service.PHASE10_API_SUBMITTER", run_inline
    )
    app.dependency_overrides[get_database_path] = lambda: database_path
    client = TestClient(app)
    try:
        yield client, database_path
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_context_prepare_poll_ready_and_unchanged_phase9_flow(
    phase10_client,
) -> None:
    client, database_path = phase10_client
    created = client.post(
        "/api/campaign-planner/contexts", json={"context": _context()}
    )
    assert created.status_code == 201
    context_id = created.json()["targeting_context_id"]

    criteria = client.put(
        f"/api/campaign-planner/contexts/{context_id}/targeting-criteria",
        json={
            "criteria": {
                "match_strength": "BROAD",
                "selection_mode": "TOP_N",
                "target_count": 10,
            }
        },
    )
    assert criteria.status_code == 200

    plan = client.get(
        f"/api/campaign-planner/contexts/{context_id}/intelligence-plan"
    )
    assert plan.status_code == 200
    assert plan.json()["readiness"] == "NEEDS_PREPARATION"
    assert plan.json()["reuse_summary"] == {
        "analysis": "BUILD",
        "model": "BUILD",
        "scoring": "BUILD",
        "rank": "BUILD",
    }
    _assert_no_pii_keys(plan.json())

    not_ready_preview = client.get(
        f"/api/campaign-planner/contexts/{context_id}/target-group-preview"
    )
    assert not_ready_preview.status_code == 409

    prepared = client.post(
        f"/api/campaign-planner/contexts/{context_id}/targeting-intelligence/prepare"
    )
    assert prepared.status_code == 202
    assert prepared.json()["status"] == "READY"
    assert prepared.json()["is_ready"] is True
    assert prepared.json()["can_retry"] is False
    assert prepared.json()["progress_percent"] == 100
    assert "scoring_run_id" not in {
        key for key in prepared.json() if key != "technical_details"
    }
    _assert_no_pii_keys(prepared.json())

    polled = client.get(
        f"/api/campaign-planner/contexts/{context_id}/targeting-intelligence/preparation"
    )
    assert polled.status_code == 200
    assert polled.json() == prepared.json()
    scoring_run_id = polled.json()["technical_details"]["scoring_run_id"]
    generation_id = polled.json()["technical_details"]["generation_id"]

    # Existing Phase 9 resolution remains backward compatible and receives its
    # source only from the verified Phase 10 READY finalization.
    resolution = client.get(
        f"/api/campaign-planner/contexts/{context_id}/targeting-intelligence"
    )
    assert resolution.status_code == 200
    assert resolution.json()["status"] == "READY"
    assert resolution.json()["technical_details"]["scoring_run_id"] == scoring_run_id

    preview = client.get(
        f"/api/campaign-planner/contexts/{context_id}/target-group-preview"
    )
    assert preview.status_code == 200
    assert preview.json()["currentness"] == "UP_TO_DATE"
    assert preview.json()["kpis"]["selected_for_target_group"] > 0

    search = client.post(
        f"/api/campaign-planner/contexts/{context_id}/target-group-search",
        json={"page_size": 5},
    )
    assert search.status_code == 200
    assert search.json()["rows"]

    saved = client.post(
        f"/api/campaign-planner/contexts/{context_id}/save-target-group-and-create-draft",
        json={
            "target_group_name": "Phase 10 Verified Target Group",
            "campaign_name": "Phase 10 Verified Campaign",
            "planned_launch_date": "2026-10-15",
        },
    )
    assert saved.status_code == 201
    assert saved.json()["targeting_source_status"] == "READY"
    assert saved.json()["campaign"]["status"] == "DRAFT"
    assert saved.json()["campaign"]["scoring_run_id"] == scoring_run_id

    draft = client.get(
        f"/api/campaign-planner/contexts/{context_id}/campaign-draft"
    )
    assert draft.status_code == 200
    assert draft.json()["campaign"] == saved.json()["campaign"]

    retry_ready = client.post(
        f"/api/campaign-planner/contexts/{context_id}/targeting-intelligence/preparation/retry"
    )
    assert retry_ready.status_code == 409

    # Delivery channel is not analytical identity: prepare reuses the same
    # generation and keeps the verified Phase 9 source binding.
    updated = client.put(
        f"/api/campaign-planner/contexts/{context_id}",
        json={"context": _context(delivery_channel="DIRECT_MAIL")},
    )
    assert updated.status_code == 200
    assert updated.json()["source_scoring_run_id"] == scoring_run_id
    reused = client.post(
        f"/api/campaign-planner/contexts/{context_id}/targeting-intelligence/prepare"
    )
    assert reused.status_code == 202
    assert reused.json()["status"] == "READY"
    assert reused.json()["technical_details"]["generation_id"] == generation_id
    with get_connection(database_path) as connection:
        linked = connection.execute(
            "SELECT source_scoring_run_id FROM campaign_targeting_contexts "
            "WHERE targeting_context_id = ?",
            (context_id,),
        ).fetchone()["source_scoring_run_id"]
    assert linked == scoring_run_id

    # An analytical dimension change invalidates the old binding immediately.
    changed_context = {**_context(delivery_channel="DIRECT_MAIL")}
    changed_context["historical_campaign_channels"] = []
    changed = client.put(
        f"/api/campaign-planner/contexts/{context_id}",
        json={"context": changed_context},
    )
    assert changed.status_code == 200
    stale = client.get(
        f"/api/campaign-planner/contexts/{context_id}/targeting-intelligence/preparation"
    )
    assert stale.status_code == 200
    assert stale.json()["status"] == "STALE"
    assert stale.json()["is_ready"] is False
    assert stale.json()["can_retry"] is True
    stale_preview = client.get(
        f"/api/campaign-planner/contexts/{context_id}/target-group-preview"
    )
    assert stale_preview.status_code == 409


def test_phase10_api_error_contracts_are_stable_and_safe(
    phase10_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = phase10_client
    missing = client.get("/api/campaign-planner/contexts/999/intelligence-plan")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Campaign Context was not found."}

    invalid = client.get("/api/campaign-planner/contexts/0/intelligence-plan")
    assert invalid.status_code == 422

    def fail_safely(*_args, **_kwargs):
        raise RuntimeError("private internal detail")

    monkeypatch.setattr(
        "app.routers.campaign_targeting.prepare_phase10_targeting_intelligence",
        fail_safely,
    )
    failed = client.post(
        "/api/campaign-planner/contexts/1/targeting-intelligence/prepare"
    )
    assert failed.status_code == 500
    assert failed.json() == {"detail": SAFE_FAILURE_MESSAGE}
    assert "private internal detail" not in failed.text


def test_active_prepare_is_idempotent_and_failed_retry_queues_new_parent(
    phase10_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, database_path = phase10_client
    monkeypatch.setattr(
        "app.services.phase10_api_service.PHASE10_API_SUBMITTER",
        lambda *_args: None,
    )
    created = client.post(
        "/api/campaign-planner/contexts", json={"context": _context()}
    )
    context_id = created.json()["targeting_context_id"]

    first = client.post(
        f"/api/campaign-planner/contexts/{context_id}/targeting-intelligence/prepare"
    )
    second = client.post(
        f"/api/campaign-planner/contexts/{context_id}/targeting-intelligence/prepare"
    )
    assert first.status_code == second.status_code == 202
    assert first.json()["status"] == second.json()["status"] == "QUEUED"
    first_id = first.json()["technical_details"]["orchestration_id"]
    assert second.json()["technical_details"]["orchestration_id"] == first_id

    # Polling an active durable parent reads its persisted reuse plan and does
    # not repeat compatibility scans.
    monkeypatch.setattr(
        "app.services.phase10_api_service.build_phase10_reuse_plan",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("active polling must not rebuild the reuse plan")
        ),
    )
    polled = client.get(
        f"/api/campaign-planner/contexts/{context_id}/targeting-intelligence/preparation"
    )
    assert polled.status_code == 200
    assert polled.json()["status"] == "QUEUED"

    Phase10IntelligenceRepository(database_path).mark_orchestration_terminal(
        first_id,
        status="FAILED",
        business_message=SAFE_FAILURE_MESSAGE,
        safe_error_message=SAFE_FAILURE_MESSAGE,
        technical_message="SyntheticFailure",
        completed_at="2026-09-14T12:00:00Z",
    )
    retried = client.post(
        f"/api/campaign-planner/contexts/{context_id}/targeting-intelligence/preparation/retry"
    )
    assert retried.status_code == 202
    assert retried.json()["status"] == "QUEUED"
    assert retried.json()["technical_details"]["orchestration_id"] > first_id
    repeated_retry = client.post(
        f"/api/campaign-planner/contexts/{context_id}/targeting-intelligence/preparation/retry"
    )
    assert repeated_retry.status_code == 409
    with get_connection(database_path) as connection:
        active_count = connection.execute(
            """
            SELECT COUNT(*) FROM phase10_orchestration_runs
            WHERE targeting_context_id = ? AND status IN ('QUEUED', 'RUNNING')
            """,
            (context_id,),
        ).fetchone()[0]
    assert active_count == 1
