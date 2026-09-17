"""Step 15 future feedback/retraining lineage contract tests."""

from pathlib import Path
import sqlite3

import pytest

from app.database.connection import get_connection
from app.database.phase11_feedback_schema import (
    CAMPAIGN_SEARCH_FUTURE_LINEAGE_COLUMNS,
    PHASE_ELEVEN_FEEDBACK_INDEX_STATEMENTS,
)
from app.database.schema import CURRENT_SCHEMA_VERSION, MIGRATIONS, initialize_database
from app.repositories.campaign_result_registry_repository import (
    CampaignResultRegistryRepository,
)
from app.repositories.phase10_intelligence_repository import (
    Phase10IntelligenceRepository,
)
from app.services.phase11_feedback_lineage_service import (
    Phase11FeedbackLineageError,
    get_completed_search_lineage,
)
from tests.test_phase10_schema_registry_repository import (
    NOW,
    _create_version_fourteen_database,
    _generation_values,
    _seed_lineage,
)


LATER = "2026-09-17T10:00:10Z"


@pytest.fixture
def completed_search(tmp_path: Path):
    database_path = tmp_path / "future-lineage.db"
    ids = _seed_lineage(database_path)
    values = _generation_values(ids)
    generation_id = Phase10IntelligenceRepository(
        database_path
    ).insert_ready_generation(values)
    repository = CampaignResultRegistryRepository(database_path)
    search_run_id = repository.create_search_run(
        campaign_name="Future lineage proof",
        description="Immutable business intent",
        planned_launch_date="2026-10-01",
        targeting_context_id=ids["targeting_context_id"],
        modeling_context_sha256=values["modeling_context_sha256"],
        targeting_criteria={"states": ["Ohio"]},
        filter_branches=[{"state": ["Ohio"]}],
        delivery_channel="EMAIL",
        created_by_user_id="future-user-reference",
        timestamp=NOW,
    )
    run = repository.fetch_search_run(search_run_id)
    snapshot_id = repository.register_snapshot(
        generation_id=generation_id,
        targeting_criteria_sha256=run["targeting_criteria_sha256"],
        filter_branches_sha256=run["filter_branches_sha256"],
        result_cache_key_sha256="f" * 64,
        resolved_count=10,
        storage_format="CSV_GZIP",
        storage_uri=(
            "artifacts/results/result_snapshot_000001/members.csv.gz"
        ),
        snapshot_sha256="e" * 64,
        timestamp=NOW,
    )
    repository.mark_processing(search_run_id)
    repository.complete_search_run(
        search_run_id,
        result_snapshot_id=snapshot_id,
        result_source="INTELLIGENCE_REUSE",
        timestamp=LATER,
    )
    export_event_id = repository.create_export_event(
        search_run_id=search_run_id,
        snapshot_id=snapshot_id,
        export_profile="EMAIL_CONTACT_V1",
        selected_count=10,
        deliverable_count=8,
        undeliverable_count=2,
        timestamp=LATER,
    )
    return database_path, search_run_id, export_event_id, ids, generation_id


def test_fresh_schema_has_nullable_write_once_future_foreign_key_seam(
    tmp_path: Path,
):
    database_path = initialize_database(tmp_path / "fresh.db")
    with get_connection(database_path) as connection:
        columns = tuple(
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(campaign_search_future_lineage)"
            )
        )
        foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(campaign_search_future_lineage)"
        ).fetchall()
        indexes = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
    assert columns == CAMPAIGN_SEARCH_FUTURE_LINEAGE_COLUMNS
    assert len(foreign_keys) == 1
    assert foreign_keys[0]["table"] == "campaign_search_runs"
    assert set(PHASE_ELEVEN_FEEDBACK_INDEX_STATEMENTS) <= indexes
    assert CURRENT_SCHEMA_VERSION == 18


def test_version_17_upgrade_backfills_existing_search_without_changing_it(
    tmp_path: Path,
):
    database_path = tmp_path / "upgrade-v17.db"
    _create_version_fourteen_database(database_path)
    with get_connection(database_path, write=True) as connection:
        for version in (15, 16, 17):
            MIGRATIONS[version](connection)
        connection.execute(
            "UPDATE app_metadata SET value='17' WHERE key='schema_version'"
        )
        connection.execute(
            """
            INSERT INTO campaign_search_runs (
                search_run_contract_version, campaign_name,
                targeting_context_id, modeling_context_sha256,
                targeting_criteria_json, targeting_criteria_sha256,
                filter_branches_json, filter_branches_sha256,
                selection_mode, delivery_channel, export_profile,
                status, created_at, started_at, completed_at,
                processing_seconds, safe_error_message
            ) VALUES (
                '1', 'Preserved blocked search', 1, ?, '{}', ?, '[{}]', ?,
                'ALL_MATCHING', 'EMAIL', 'EMAIL_CONTACT_V1', 'BLOCKED',
                ?, ?, ?, 0, 'Preserved safe message'
            )
            """,
            ("a" * 64, "b" * 64, "c" * 64, NOW, NOW, NOW),
        )
        before = dict(
            connection.execute(
                "SELECT * FROM campaign_search_runs"
            ).fetchone()
        )

    initialize_database(database_path)
    initialize_database(database_path)
    with get_connection(database_path) as connection:
        after = dict(
            connection.execute(
                "SELECT * FROM campaign_search_runs"
            ).fetchone()
        )
        future = dict(
            connection.execute(
                "SELECT * FROM campaign_search_future_lineage"
            ).fetchone()
        )
        version = connection.execute(
            "SELECT value FROM app_metadata WHERE key='schema_version'"
        ).fetchone()[0]
    assert after == before
    assert future == {
        "search_run_id": before["search_run_id"],
        "activation_id": None,
        "provider_campaign_id": None,
        "feedback_batch_id": None,
        "outcome_dataset_id": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    assert version == "18"


def test_failed_version_18_migration_rolls_back_table_and_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    database_path = tmp_path / "rollback-v18.db"
    _create_version_fourteen_database(database_path)
    with get_connection(database_path, write=True) as connection:
        for version in (15, 16, 17):
            MIGRATIONS[version](connection)
        connection.execute(
            "UPDATE app_metadata SET value='17' WHERE key='schema_version'"
        )
    real_migration = MIGRATIONS[18]

    def fail_after_ddl(connection):
        real_migration(connection)
        raise RuntimeError("forced schema 18 failure")

    monkeypatch.setitem(MIGRATIONS, 18, fail_after_ddl)
    with pytest.raises(RuntimeError, match="forced schema 18 failure"):
        initialize_database(database_path)
    with get_connection(database_path) as connection:
        version = connection.execute(
            "SELECT value FROM app_metadata WHERE key='schema_version'"
        ).fetchone()[0]
        table = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='campaign_search_future_lineage'"
        ).fetchone()
    assert version == "17"
    assert table is None


def test_completed_search_audit_preserves_full_lineage_and_export_ids(
    completed_search,
):
    database_path, search_run_id, export_event_id, ids, generation_id = (
        completed_search
    )
    lineage = get_completed_search_lineage(database_path, search_run_id)
    assert lineage["search"]["created_by_user_id"] == "future-user-reference"
    assert lineage["business_context"]["campaign_context"] == {}
    assert lineage["targeting"]["criteria"] == {"states": ["Ohio"]}
    assert lineage["targeting"]["filter_branches"] == [
        {"state": ["Ohio"]}
    ]
    assert lineage["delivery"] == {
        "channel": "EMAIL",
        "export_profile": "EMAIL_CONTACT_V1",
        "export_event_ids": [export_event_id],
    }
    assert lineage["result"]["result_snapshot_id"] > 0
    assert lineage["result"]["snapshot_sha256"] == "e" * 64
    assert lineage["result"]["result_cache_key_sha256"] == "f" * 64
    assert lineage["intelligence"]["generation_id"] == generation_id
    assert lineage["intelligence"]["analysis_run_id"] == ids["analysis_run_id"]
    assert lineage["intelligence"]["model_run_id"] == ids["model_run_id"]
    assert lineage["intelligence"]["scoring_run_id"] == ids["scoring_run_id"]
    assert lineage["intelligence"]["model_artifact_sha256"] == "7" * 64
    assert lineage["intelligence"]["customer_source_checksum"] == "1" * 64
    assert lineage["intelligence"]["campaign_sales_source_checksum"] == "2" * 64
    assert lineage["intelligence"]["demographic_source_checksum"] == "3" * 64
    assert lineage["future_links"] == {
        "activation_id": None,
        "provider_campaign_id": None,
        "feedback_batch_id": None,
        "outcome_dataset_id": None,
    }


def test_future_links_are_completed_only_write_once_and_not_feedback_logic(
    completed_search,
):
    database_path, search_run_id, _export_event_id, _ids, _generation_id = (
        completed_search
    )
    repository = CampaignResultRegistryRepository(database_path)
    queued_id = repository.create_search_run(
        campaign_name="Not complete",
        targeting_context_id=1,
        modeling_context_sha256="a" * 64,
        targeting_criteria={},
        filter_branches=[{}],
        delivery_channel="EMAIL",
        timestamp=NOW,
    )
    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(database_path, write=True) as connection:
            connection.execute(
                "UPDATE campaign_search_future_lineage "
                "SET activation_id='too-early', updated_at=? "
                "WHERE search_run_id=?",
                (LATER, queued_id),
            )

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            UPDATE campaign_search_future_lineage
            SET activation_id='activation-1',
                provider_campaign_id='provider-campaign-1',
                feedback_batch_id='feedback-batch-1',
                outcome_dataset_id='outcome-dataset-1',
                updated_at=?
            WHERE search_run_id=?
            """,
            (LATER, search_run_id),
        )
    assert get_completed_search_lineage(database_path, search_run_id)[
        "future_links"
    ] == {
        "activation_id": "activation-1",
        "provider_campaign_id": "provider-campaign-1",
        "feedback_batch_id": "feedback-batch-1",
        "outcome_dataset_id": "outcome-dataset-1",
    }
    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(database_path, write=True) as connection:
            connection.execute(
                "UPDATE campaign_search_future_lineage "
                "SET feedback_batch_id='replacement', updated_at=? "
                "WHERE search_run_id=?",
                (LATER, search_run_id),
            )
    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(database_path, write=True) as connection:
            connection.execute(
                "DELETE FROM campaign_search_future_lineage WHERE search_run_id=?",
                (search_run_id,),
            )
    with pytest.raises(Phase11FeedbackLineageError):
        get_completed_search_lineage(database_path, queued_id)
