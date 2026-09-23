from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import (
    CAMPAIGN_TARGETING_CONTEXT_COLUMNS,
    CREATE_TABLE_STATEMENTS,
    CURRENT_SCHEMA_VERSION,
    MIGRATIONS,
    PHASE_NINE_REQUIRED_INDEX_STATEMENTS,
    PHASE9_SAVED_TARGET_GROUP_COLUMNS,
    initialize_database,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "phase9-schema.db"


def _create_version_twelve_database(database_path: Path) -> None:
    with get_connection(database_path, write=True) as connection:
        for statement in CREATE_TABLE_STATEMENTS:
            connection.execute(statement)
        connection.executemany(
            """
            INSERT INTO app_metadata (key, value, updated_at)
            VALUES (?, ?, '2026-09-09T00:00:00Z')
            """,
            (
                ("schema_version", "1"),
                ("application_version", "0.1.0"),
                ("database_initialized_at", "2026-09-09T00:00:00Z"),
                ("phase9_preservation_sentinel", "preserve-me"),
            ),
        )
        for version in range(2, 13):
            MIGRATIONS[version](connection)
            connection.execute(
                "UPDATE app_metadata SET value = ? WHERE key = 'schema_version'",
                (str(version),),
            )


def _create_version_thirteen_database(database_path: Path) -> None:
    _create_version_twelve_database(database_path)
    with get_connection(database_path, write=True) as connection:
        MIGRATIONS[13](connection)
        connection.execute(
            "UPDATE app_metadata SET value = '13' WHERE key = 'schema_version'"
        )


def _columns(connection: sqlite3.Connection, table_name: str) -> tuple[str, ...]:
    return tuple(
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    )


def _insert_context(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO campaign_targeting_contexts (
            campaign_targeting_context_contract_version,
            targeting_segment_contract_version,
            business_match_strength_contract_version,
            campaign_context_json,
            campaign_context_sha256,
            targeting_criteria_json,
            targeting_criteria_sha256,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "1",
            "1",
            "1",
            '{"campaign_channel":"EMAIL"}',
            "a" * 64,
            '{"match_strength":"GOOD"}',
            "b" * 64,
            "2026-09-09T00:00:00Z",
            "2026-09-09T00:00:00Z",
        ),
    )


def test_fresh_schema_creates_phase9_table_columns_and_indexes(database_path: Path) -> None:
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        schema_version = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
        columns = _columns(connection, "campaign_targeting_contexts")
        saved_target_group_columns = _columns(
            connection, "phase9_saved_target_groups"
        )
        indexes = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }

    assert schema_version == str(CURRENT_SCHEMA_VERSION) == "19"
    assert columns == CAMPAIGN_TARGETING_CONTEXT_COLUMNS
    assert saved_target_group_columns == PHASE9_SAVED_TARGET_GROUP_COLUMNS
    assert set(PHASE_NINE_REQUIRED_INDEX_STATEMENTS) <= indexes


def test_v12_to_current_migrations_are_additive_idempotent_and_preserve_data(
    database_path: Path,
) -> None:
    _create_version_twelve_database(database_path)

    initialize_database(database_path)
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        schema_version = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
        sentinel = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'phase9_preservation_sentinel'"
        ).fetchone()[0]
        columns = _columns(connection, "campaign_targeting_contexts")

    assert schema_version == str(CURRENT_SCHEMA_VERSION)
    assert sentinel == "preserve-me"
    assert columns == CAMPAIGN_TARGETING_CONTEXT_COLUMNS


def test_phase9_table_enforces_json_hash_and_source_reference_constraints(
    database_path: Path,
) -> None:
    initialize_database(database_path)
    with get_connection(database_path, write=True) as connection:
        _insert_context(connection)

    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(database_path, write=True) as connection:
            connection.execute(
                """
                UPDATE campaign_targeting_contexts
                SET campaign_context_json = 'not-json'
                WHERE targeting_context_id = 1
                """
            )
    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(database_path, write=True) as connection:
            connection.execute(
                """
                UPDATE campaign_targeting_contexts
                SET targeting_criteria_sha256 = 'short'
                WHERE targeting_context_id = 1
                """
            )
    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(database_path, write=True) as connection:
            connection.execute(
                """
                UPDATE campaign_targeting_contexts
                SET source_scoring_run_id = 999
                WHERE targeting_context_id = 1
                """
            )


def test_failed_v14_migration_rolls_back_schema_and_version(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_version_thirteen_database(database_path)

    def fail_migration(connection: sqlite3.Connection) -> None:
        connection.execute("CREATE TABLE migration_should_rollback_v14 (id INTEGER)")
        raise RuntimeError("forced v14 migration failure")

    monkeypatch.setitem(MIGRATIONS, 14, fail_migration)
    with pytest.raises(RuntimeError, match="forced v14 migration failure"):
        initialize_database(database_path)

    with get_connection(database_path) as connection:
        schema_version = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("migration_should_rollback_v14",),
        ).fetchone()

    assert schema_version == "13"
    assert table is None
