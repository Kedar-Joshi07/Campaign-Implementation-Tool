from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.database.connection import get_connection
from app.repositories.phase10_intelligence_repository import (
    LIFECYCLE_STATES,
    Phase10IntelligenceRepository,
)
from app.schemas.phase10_intelligence import Phase10LifecycleReport
from app.services.campaign_targeting_context_service import (
    save_business_targeting_criteria,
)
from app.services.phase10_lifecycle_service import reconcile_phase10_lifecycle
from app.services.phase10_orchestration_service import (
    prepare_phase10_orchestration,
    run_phase10_orchestration,
)
from app.services.target_group_campaign_service import (
    save_target_group_and_create_campaign_draft,
)
from app.services.target_group_preview_service import get_target_group_preview
from tests.test_phase10_orchestration_service import (
    _create_context,
    _seed_orchestration_database,
)


@pytest.fixture
def ready_generation(tmp_path: Path) -> tuple[Path, Path, int, int]:
    database_path, project_root = _seed_orchestration_database(tmp_path)
    context_id = _create_context(database_path)
    queued = prepare_phase10_orchestration(
        database_path,
        context_id,
        project_root=project_root,
        submitter=lambda *_args: None,
    )
    ready = run_phase10_orchestration(
        database_path,
        int(queued.orchestration["orchestration_id"]),
        project_root=project_root,
        artifact_root=Path("artifacts/models"),
    )
    assert ready["status"] == "READY"
    return database_path, project_root, context_id, int(ready["generation_id"])


def _clone_generation(
    database_path: Path,
    source_generation_id: int,
    *,
    key_character: str,
    created_at: str,
) -> int:
    repository = Phase10IntelligenceRepository(database_path)
    source = repository.fetch_generation(source_generation_id)
    assert source is not None
    values = {field: value for field, value in source.items() if field != "generation_id"}
    values.update(
        {
            "intelligence_key_sha256": key_character * 64,
            "lifecycle_state": "CURRENT",
            "created_at": created_at,
            "last_verified_at": created_at,
            "last_used_at": created_at,
        }
    )
    return repository.insert_ready_generation(values)


def _generation_report(report: dict[str, Any], generation_id: int) -> dict[str, Any]:
    return next(
        row for row in report["generations"] if row["generation_id"] == generation_id
    )


def _set_last_used(database_path: Path, generation_id: int, value: str) -> None:
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            UPDATE phase10_intelligence_generations
            SET last_used_at = ?
            WHERE generation_id = ?
            """,
            (value, generation_id),
        )


def _last_used(database_path: Path, generation_id: int) -> str:
    with get_connection(database_path) as connection:
        return str(
            connection.execute(
                """
                SELECT last_used_at FROM phase10_intelligence_generations
                WHERE generation_id = ?
                """,
                (generation_id,),
            ).fetchone()["last_used_at"]
        )


def _assert_no_pii_report(value: object) -> None:
    forbidden_keys = {
        "customer_id",
        "person_id",
        "prospect_id",
        "email",
        "phone",
        "name",
        "address",
    }
    if isinstance(value, dict):
        assert forbidden_keys.isdisjoint(value)
        for child in value.values():
            _assert_no_pii_report(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_pii_report(child)


def test_current_reuse_preview_and_target_group_save_touch_usage(
    ready_generation: tuple[Path, Path, int, int],
) -> None:
    database_path, project_root, context_id, generation_id = ready_generation
    report = reconcile_phase10_lifecycle(
        database_path, generated_at="2026-09-14T10:00:00Z"
    )
    Phase10LifecycleReport.model_validate(report)
    _assert_no_pii_report(report)
    row = _generation_report(report, generation_id)
    assert row["lifecycle_state"] == "CURRENT"
    assert row["source_current"] is True
    assert row["reusable_targeting_context_ids"] == [context_id]
    assert report["reusable_contexts"] == {str(generation_id): [context_id]}
    assert report["score_row_footprint_count"] == 60
    assert sum(report["counts_by_state"].values()) == 1
    assert set(report["counts_by_state"]) == LIFECYCLE_STATES

    old = "2000-01-01T00:00:00Z"
    _set_last_used(database_path, generation_id, old)
    reused = prepare_phase10_orchestration(
        database_path,
        context_id,
        project_root=project_root,
        submitter=lambda *_args: (_ for _ in ()).throw(
            AssertionError("exact current reuse must not submit work")
        ),
    )
    assert reused.already_ready is True
    assert _last_used(database_path, generation_id) > old

    save_business_targeting_criteria(
        database_path,
        {
            "match_strength": "BROAD",
            "selection_mode": "TOP_N",
            "target_count": 5,
        },
        targeting_context_id=context_id,
    )
    _set_last_used(database_path, generation_id, old)
    preview = get_target_group_preview(
        database_path, targeting_context_id=context_id
    )
    assert preview["currentness"] == "UP_TO_DATE"
    assert _last_used(database_path, generation_id) > old

    _set_last_used(database_path, generation_id, old)
    saved = save_target_group_and_create_campaign_draft(
        database_path,
        targeting_context_id=context_id,
        request_payload={
            "target_group_name": "Lifecycle Target Group",
            "target_group_description": None,
            "campaign_name": "Lifecycle Campaign",
            "campaign_description": None,
            "planned_launch_date": "2026-10-15",
        },
    )
    assert saved["campaign"]["status"] == "DRAFT"
    assert _last_used(database_path, generation_id) > old


def test_superseded_generation_with_saved_business_references_is_protected(
    ready_generation: tuple[Path, Path, int, int],
) -> None:
    database_path, _project_root, context_id, generation_id = ready_generation
    save_business_targeting_criteria(
        database_path,
        {"match_strength": "BROAD", "selection_mode": "TOP_N", "target_count": 5},
        targeting_context_id=context_id,
    )
    saved = save_target_group_and_create_campaign_draft(
        database_path,
        targeting_context_id=context_id,
        request_payload={
            "target_group_name": "Protected Target Group",
            "target_group_description": None,
            "campaign_name": "Protected Campaign",
            "campaign_description": None,
            "planned_launch_date": None,
        },
    )
    audience_id = saved["saved_target_group"]["saved_target_group_id"]
    campaign_id = saved["campaign"]["campaign_id"]
    _clone_generation(
        database_path,
        generation_id,
        key_character="a",
        created_at="2026-09-14T11:00:00Z",
    )

    report = reconcile_phase10_lifecycle(
        database_path, generated_at="2026-09-14T11:01:00Z"
    )
    row = _generation_report(report, generation_id)
    assert row["lifecycle_state"] == "PROTECTED"
    assert row["classification_before_protection"] == "SUPERSEDED"
    assert {"SAVED_AUDIENCE", "PHASE9_SAVED_TARGET_GROUP", "CAMPAIGN"}.issubset(
        row["protection_reasons"]
    )
    repository = Phase10IntelligenceRepository(database_path)
    generation = repository.fetch_generation(generation_id)
    assert generation is not None
    protected_candidates = repository.list_reusable_model_generations(
        str(generation["modeling_context_sha256"])
    )
    assert generation_id in {
        int(candidate["generation_id"]) for candidate in protected_candidates
    }

    with get_connection(database_path) as connection:
        assert connection.execute(
            "SELECT scoring_run_id FROM saved_audiences WHERE audience_id = ?",
            (audience_id,),
        ).fetchone() is not None
        assert connection.execute(
            "SELECT saved_audience_id FROM campaigns WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()["saved_audience_id"] == audience_id


def test_unreferenced_superseded_generation_becomes_retirement_eligible(
    ready_generation: tuple[Path, Path, int, int],
) -> None:
    database_path, _project_root, _context_id, generation_id = ready_generation
    middle_id = _clone_generation(
        database_path,
        generation_id,
        key_character="b",
        created_at="2026-09-14T12:00:00Z",
    )
    _clone_generation(
        database_path,
        generation_id,
        key_character="c",
        created_at="2026-09-14T12:01:00Z",
    )
    report = reconcile_phase10_lifecycle(
        database_path, generated_at="2026-09-14T12:02:00Z"
    )

    row = _generation_report(report, middle_id)
    assert row["classification_before_protection"] == "SUPERSEDED"
    assert row["lifecycle_state"] == "RETIREMENT_ELIGIBLE"
    assert row["protection_reasons"] == []
    assert middle_id in report["retirement_eligible_generation_ids"]
    # Three registry records share one physical scoring run; footprint is not
    # triple-counted.
    assert report["score_row_footprint_count"] == 60


def test_changed_source_marks_bound_generation_stale(
    ready_generation: tuple[Path, Path, int, int],
) -> None:
    database_path, _project_root, _context_id, generation_id = ready_generation
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO data_import_runs (
                dataset_name, source_path, started_at, completed_at, status,
                rows_read, rows_inserted, rows_rejected, source_checksum
            ) VALUES (
                'demographics', 'data/demographics-refresh.csv.gz',
                '2026-09-14T13:00:00Z', '2026-09-14T13:00:01Z',
                'COMPLETED', 60, 60, 0, ?
            )
            """,
            ("f" * 64,),
        )
    report = reconcile_phase10_lifecycle(
        database_path, generated_at="2026-09-14T13:01:00Z"
    )
    row = _generation_report(report, generation_id)
    assert row["source_current"] is False
    assert row["classification_before_protection"] == "STALE"
    assert row["lifecycle_state"] == "STALE"


def test_active_orchestration_protects_generation_and_classification_is_non_destructive(
    ready_generation: tuple[Path, Path, int, int],
) -> None:
    database_path, project_root, context_id, generation_id = ready_generation
    repository = Phase10IntelligenceRepository(database_path)
    generation = repository.fetch_generation(generation_id)
    assert generation is not None
    active, created = repository.create_or_get_active_orchestration(
        orchestration_contract_version="1",
        targeting_context_id=context_id,
        modeling_context_sha256=str(generation["modeling_context_sha256"]),
        intelligence_key_sha256=str(generation["intelligence_key_sha256"]),
        business_message="Checking available targeting intelligence",
        reuse_plan={
            "analysis": "REUSE",
            "model": "REUSE",
            "scoring": "REUSE",
            "rank": "REUSE",
        },
        created_at="2026-09-14T14:00:00Z",
    )
    assert created is True and active["status"] == "QUEUED"

    analytical_tables = (
        "historical_analysis_runs",
        "model_runs",
        "scoring_runs",
        "propensity_scores",
    )
    with get_connection(database_path) as connection:
        before = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in analytical_tables
        }
        artifact_path = str(
            connection.execute(
                "SELECT artifact_path FROM model_runs WHERE model_run_id = ?",
                (generation["model_run_id"],),
            ).fetchone()["artifact_path"]
        )

    report = reconcile_phase10_lifecycle(
        database_path, generated_at="2026-09-14T14:01:00Z"
    )
    row = _generation_report(report, generation_id)
    assert row["lifecycle_state"] == "PROTECTED"
    assert "ACTIVE_ORCHESTRATION" in row["protection_reasons"]

    with get_connection(database_path) as connection:
        after = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in analytical_tables
        }
    assert after == before
    assert (project_root / artifact_path).is_file()

    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "phase10_lifecycle_service.py"
    ).read_text(encoding="utf-8")
    assert "DELETE FROM propensity_scores" not in source
    assert "DELETE FROM scoring_runs" not in source
    assert "DELETE FROM model_runs" not in source
    assert "DELETE FROM historical_analysis_runs" not in source
