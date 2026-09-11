from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.main import app
from app.services.audience_preparation_service import run_audience_rank_preparation
from app.services.campaign_service import (
    CampaignServiceError,
    EXPORT_PROFILE_EMAIL_CONTACT_V1,
    _iter_selected_member_chunks,
    _resolve_campaign_member_query_context,
)
from app.services import target_group_campaign_service
from app.services.campaign_targeting_context_service import (
    save_business_targeting_criteria,
    save_campaign_targeting_context,
)
from app.services.target_group_campaign_service import (
    reopen_phase9_campaign_draft,
    save_target_group_and_create_campaign_draft,
)
from app.services.targeting_intelligence_service import link_targeting_intelligence
from tests.test_saved_audience_service import _seed_fixture


@pytest.fixture
def ready_campaign_context(tmp_path: Path) -> tuple[Path, int, int]:
    database_path = tmp_path / "phase9-save-target-group.db"
    initialize_database(database_path)
    scoring_run_id = _seed_fixture(database_path)
    run_audience_rank_preparation(database_path, scoring_run_id=scoring_run_id)
    context = save_campaign_targeting_context(
        database_path,
        {
            "product_ids": ["PRD_001"],
            "campaign_types": [],
            "campaign_categories": [],
            "offer_types": [],
            "campaign_channel": "EMAIL",
            "historical_campaign_channels": [],
        },
    )
    targeting_context_id = int(context["targeting_context_id"])
    save_business_targeting_criteria(
        database_path,
        {
            "match_strength": "BROAD",
            "age_groups": ["25-34", "45-54"],
            "income_groups": ["<25K", "50K-74,999", "75K-99,999"],
            "marital_statuses": ["Married", "Single"],
            "selection_mode": "ALL_MATCHING",
        },
        targeting_context_id=targeting_context_id,
    )
    resolution = link_targeting_intelligence(
        database_path,
        targeting_context_id=targeting_context_id,
        scoring_run_id=scoring_run_id,
    )
    assert resolution.status == "READY"
    return database_path, targeting_context_id, scoring_run_id


def _request(**overrides: Any) -> dict[str, Any]:
    payload = {
        "target_group_name": "Autumn Retention Target Group",
        "target_group_description": "Business-approved target group",
        "campaign_name": "Autumn Retention",
        "campaign_description": "Retain priority customers",
        "planned_launch_date": "2026-10-15",
    }
    payload.update(overrides)
    return payload


def _assert_no_pii_keys(value: Any) -> None:
    forbidden = {
        "first_name",
        "last_name",
        "email",
        "phone",
        "address_line_1",
        "address_line_2",
        "postal_code",
    }
    if isinstance(value, dict):
        assert forbidden.isdisjoint(value)
        for child in value.values():
            _assert_no_pii_keys(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_pii_keys(child)


def test_api_saves_immutable_group_and_creates_linked_draft(
    ready_campaign_context: tuple[Path, int, int],
) -> None:
    database_path, targeting_context_id, scoring_run_id = ready_campaign_context
    app.dependency_overrides[get_database_path] = lambda: database_path
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/campaign-planner/contexts/{targeting_context_id}/save-target-group-and-create-draft",
                json=_request(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["campaign_created"] is True
    assert body["targeting_source_status"] == "READY"
    assert body["saved_target_group"]["selected_count"] == 2
    assert body["saved_target_group"]["filter_branch_count"] > 1
    assert body["saved_target_group"]["immutable"] is True
    assert body["saved_target_group"]["currentness"] == "UP_TO_DATE"
    assert body["campaign"]["status"] == "DRAFT"
    assert body["campaign"]["campaign_name"] == "Autumn Retention"
    assert body["campaign"]["description"] == "Retain priority customers"
    assert body["campaign"]["channel"] == "EMAIL"
    assert body["campaign"]["planned_launch_date"] == "2026-10-15"
    assert body["campaign"]["finalized_at"] is None
    assert body["campaign"]["saved_audience_id"] == body["saved_target_group"][
        "saved_target_group_id"
    ]
    assert body["campaign"]["scoring_run_id"] == scoring_run_id
    _assert_no_pii_keys(body)

    with get_connection(database_path) as connection:
        context = dict(
            connection.execute(
                "SELECT * FROM campaign_targeting_contexts WHERE targeting_context_id = ?",
                (targeting_context_id,),
            ).fetchone()
        )
        audience = dict(
            connection.execute(
                "SELECT * FROM saved_audiences WHERE audience_id = ?",
                (body["saved_target_group"]["saved_target_group_id"],),
            ).fetchone()
        )
        metadata = dict(
            connection.execute(
                "SELECT * FROM phase9_saved_target_groups WHERE audience_id = ?",
                (body["saved_target_group"]["saved_target_group_id"],),
            ).fetchone()
        )
    assert context["campaign_id"] == body["campaign"]["campaign_id"]
    assert audience["resolved_count"] == 2
    assert audience["scoring_run_id"] == scoring_run_id
    assert metadata["resolved_count"] == 2
    assert metadata["source_status"] == "READY"
    assert metadata["source_scoring_run_id"] == scoring_run_id
    assert json.loads(metadata["campaign_context_json"])["campaign_channel"] == "EMAIL"


def test_reopen_restores_immutable_business_context_and_exact_union_members(
    ready_campaign_context: tuple[Path, int, int],
) -> None:
    database_path, targeting_context_id, _ = ready_campaign_context
    created = save_target_group_and_create_campaign_draft(
        database_path,
        targeting_context_id=targeting_context_id,
        request_payload=_request(),
    )
    reopened = reopen_phase9_campaign_draft(
        database_path, targeting_context_id=targeting_context_id
    )

    assert reopened["campaign_created"] is False
    assert reopened["campaign_context"] == created["campaign_context"]
    assert reopened["targeting_criteria"] == created["targeting_criteria"]
    assert reopened["saved_target_group"] == created["saved_target_group"]
    assert reopened["saved_target_group"]["currentness_label"] == "Up to date"

    with get_connection(database_path) as connection:
        campaign_row = dict(
            connection.execute(
                "SELECT * FROM campaigns WHERE campaign_id = ?",
                (created["campaign"]["campaign_id"],),
            ).fetchone()
        )
    query_context = _resolve_campaign_member_query_context(database_path, campaign_row)
    with get_connection(database_path) as connection:
        chunks = list(
            _iter_selected_member_chunks(
                connection,
                query_context=query_context,
                export_profile=EXPORT_PROFILE_EMAIL_CONTACT_V1,
                chunk_size=1,
            )
        )
    members = [row["person_id"] for chunk in chunks for row in chunk]
    assert members == ["PER_000002", "PER_000005"]
    assert len(members) == len(set(members)) == created["saved_target_group"][
        "selected_count"
    ]


def test_edit_before_first_save_persists_only_final_values(
    ready_campaign_context: tuple[Path, int, int],
) -> None:
    database_path, targeting_context_id, _ = ready_campaign_context
    save_campaign_targeting_context(
        database_path,
        {
            "product_ids": ["PRD_001"],
            "campaign_types": [],
            "campaign_categories": [],
            "offer_types": [],
            "campaign_channel": "DIRECT_MAIL",
            "historical_campaign_channels": [],
        },
        targeting_context_id=targeting_context_id,
    )
    created = save_target_group_and_create_campaign_draft(
        database_path,
        targeting_context_id=targeting_context_id,
        request_payload=_request(
            target_group_name="Edited Before Save",
            campaign_name="Final Campaign Name",
            campaign_description="Final description",
        ),
    )

    assert created["saved_target_group"]["name"] == "Edited Before Save"
    assert created["campaign"]["campaign_name"] == "Final Campaign Name"
    assert created["campaign"]["description"] == "Final description"
    assert created["campaign"]["channel"] == "DIRECT_MAIL"
    assert created["campaign_context"]["campaign_channel"] == "DIRECT_MAIL"
    with get_connection(database_path) as connection:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("saved_audiences", "phase9_saved_target_groups", "campaigns")
        }
    assert counts == {
        "saved_audiences": 1,
        "phase9_saved_target_groups": 1,
        "campaigns": 1,
    }


def test_changed_criteria_creates_new_group_without_mutating_previous_group(
    ready_campaign_context: tuple[Path, int, int],
) -> None:
    database_path, targeting_context_id, _ = ready_campaign_context
    first = save_target_group_and_create_campaign_draft(
        database_path,
        targeting_context_id=targeting_context_id,
        request_payload=_request(),
    )
    first_id = first["saved_target_group"]["saved_target_group_id"]
    with get_connection(database_path) as connection:
        first_before = dict(
            connection.execute(
                "SELECT * FROM phase9_saved_target_groups WHERE audience_id = ?",
                (first_id,),
            ).fetchone()
        )

    save_business_targeting_criteria(
        database_path,
        {
            "match_strength": "BROAD",
            "age_groups": ["35-44"],
            "income_groups": ["100K-149,999"],
            "selection_mode": "ALL_MATCHING",
        },
        targeting_context_id=targeting_context_id,
    )
    second = save_target_group_and_create_campaign_draft(
        database_path,
        targeting_context_id=targeting_context_id,
        request_payload=_request(
            target_group_name="Revised Target Group",
            campaign_name="Revised Autumn Retention",
        ),
    )
    second_id = second["saved_target_group"]["saved_target_group_id"]

    assert second_id != first_id
    assert second["campaign_created"] is False
    assert second["campaign"]["campaign_id"] == first["campaign"]["campaign_id"]
    assert second["campaign"]["saved_audience_id"] == second_id
    assert second["campaign"]["status"] == "DRAFT"
    with get_connection(database_path) as connection:
        first_after = dict(
            connection.execute(
                "SELECT * FROM phase9_saved_target_groups WHERE audience_id = ?",
                (first_id,),
            ).fetchone()
        )
        audience_count = connection.execute(
            "SELECT COUNT(*) FROM saved_audiences"
        ).fetchone()[0]
    assert first_after == first_before
    assert audience_count == 2


def test_stale_source_is_visible_on_reopen_and_blocks_another_save(
    ready_campaign_context: tuple[Path, int, int],
) -> None:
    database_path, targeting_context_id, _ = ready_campaign_context
    created = save_target_group_and_create_campaign_draft(
        database_path,
        targeting_context_id=targeting_context_id,
        request_payload=_request(),
    )
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO data_import_runs (
                dataset_name, source_path, started_at, completed_at, status,
                rows_read, rows_inserted, rows_rejected, source_checksum
            ) VALUES ('demographics', 'changed.csv', '2026-09-11T00:00:00Z',
                      '2026-09-11T00:00:01Z', 'COMPLETED', 6, 6, 0, ?)
            """,
            ("f" * 64,),
        )

    reopened = reopen_phase9_campaign_draft(
        database_path, targeting_context_id=targeting_context_id
    )
    assert reopened["targeting_source_status"] == "STALE"
    assert reopened["saved_target_group"]["currentness"] == "NEEDS_REFRESH"
    assert reopened["saved_target_group"]["currentness_label"] == "Needs refresh"

    app.dependency_overrides[get_database_path] = lambda: database_path
    try:
        with TestClient(app) as client:
            blocked = client.post(
                f"/api/campaign-planner/contexts/{targeting_context_id}/save-target-group-and-create-draft",
                json=_request(target_group_name="Must Not Save"),
            )
    finally:
        app.dependency_overrides.clear()
    assert blocked.status_code == 409
    with get_connection(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM saved_audiences").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0] == 1
    assert created["campaign"]["status"] == "DRAFT"


def test_repeat_save_is_idempotent_and_draft_failure_retry_reuses_group(
    ready_campaign_context: tuple[Path, int, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path, targeting_context_id, scoring_run_id = ready_campaign_context
    first = save_target_group_and_create_campaign_draft(
        database_path,
        targeting_context_id=targeting_context_id,
        request_payload=_request(),
    )
    replay = save_target_group_and_create_campaign_draft(
        database_path,
        targeting_context_id=targeting_context_id,
        request_payload=_request(),
    )
    assert first["idempotent_replay"] is False
    assert replay["idempotent_replay"] is True
    assert replay["saved_target_group"]["saved_target_group_id"] == first[
        "saved_target_group"
    ]["saved_target_group_id"]
    assert replay["campaign"]["campaign_id"] == first["campaign"]["campaign_id"]

    second_context = save_campaign_targeting_context(
        database_path,
        {
            "product_ids": ["PRD_001"],
            "campaign_types": [],
            "campaign_categories": [],
            "offer_types": [],
            "campaign_channel": "EMAIL",
            "historical_campaign_channels": [],
        },
    )
    second_context_id = int(second_context["targeting_context_id"])
    save_business_targeting_criteria(
        database_path,
        {
            "match_strength": "BROAD",
            "age_groups": ["25-34", "45-54"],
            "income_groups": ["<25K", "50K-74,999", "75K-99,999"],
            "marital_statuses": ["Married", "Single"],
            "selection_mode": "ALL_MATCHING",
        },
        targeting_context_id=second_context_id,
    )
    link_targeting_intelligence(
        database_path,
        targeting_context_id=second_context_id,
        scoring_run_id=scoring_run_id,
    )
    retry_request = _request(
        target_group_name="Retry-safe Target Group",
        campaign_name="Retry-safe Campaign",
    )
    original_create = target_group_campaign_service.create_campaign

    def fail_campaign_creation(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise CampaignServiceError(
            "sqlite SELECT failed at C:\\private\\project; RuntimeError"
        )

    monkeypatch.setattr(
        target_group_campaign_service, "create_campaign", fail_campaign_creation
    )
    with pytest.raises(
        target_group_campaign_service.TargetGroupCampaignConflictError,
        match="inputs are preserved",
    ) as failure:
        save_target_group_and_create_campaign_draft(
            database_path,
            targeting_context_id=second_context_id,
            request_payload=retry_request,
        )
    assert "sqlite" not in str(failure.value).lower()
    assert "private" not in str(failure.value).lower()

    monkeypatch.setattr(target_group_campaign_service, "create_campaign", original_create)
    recovered = save_target_group_and_create_campaign_draft(
        database_path,
        targeting_context_id=second_context_id,
        request_payload=retry_request,
    )
    assert recovered["campaign_created"] is True
    assert recovered["idempotent_replay"] is True
    with get_connection(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM saved_audiences").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0] == 2


def test_target_group_save_failure_is_distinct_and_leaves_no_partial_records(
    ready_campaign_context: tuple[Path, int, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path, targeting_context_id, _scoring_run_id = ready_campaign_context

    def fail_target_group_save(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise target_group_campaign_service.SavedAudienceServiceValidationError(
            "Injected invalid target-group save"
        )

    monkeypatch.setattr(
        target_group_campaign_service,
        "save_resolved_audience_definition",
        fail_target_group_save,
    )
    with pytest.raises(
        target_group_campaign_service.CampaignContextValidationError,
        match="Target Group could not be saved",
    ):
        save_target_group_and_create_campaign_draft(
            database_path,
            targeting_context_id=targeting_context_id,
            request_payload=_request(),
        )

    with get_connection(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM saved_audiences").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM phase9_saved_target_groups").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0] == 0
