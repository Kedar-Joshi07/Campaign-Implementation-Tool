from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import (
    CREATE_TABLE_STATEMENTS,
    JOB_COLUMNS,
    MIGRATIONS,
    PHASE_FOUR_REQUIRED_INDEX_STATEMENTS,
    initialize_database,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "phase4-schema.db"


def _create_version_three_database(database_path: Path) -> None:
    with get_connection(database_path, write=True) as connection:
        for statement in CREATE_TABLE_STATEMENTS:
            connection.execute(statement)
        connection.executemany(
            """
            INSERT INTO app_metadata (key, value, updated_at)
            VALUES (?, ?, '2026-08-21T00:00:00Z')
            """,
            (
                ("schema_version", "1"),
                ("application_version", "0.1.0"),
                ("database_initialized_at", "2026-08-20T00:00:00Z"),
            ),
        )
        MIGRATIONS[2](connection)
        connection.execute(
            "UPDATE app_metadata SET value = '2' WHERE key = 'schema_version'"
        )
        MIGRATIONS[3](connection)
        connection.execute(
            "UPDATE app_metadata SET value = '3' WHERE key = 'schema_version'"
        )


def _insert_historical_run(connection: sqlite3.Connection) -> int:
    cursor = connection.execute(
        """
        INSERT INTO historical_analysis_runs (
            analysis_name, created_at, completed_at, status,
            conversion_definition, filters_json, results_json,
            observation_count, selected_customer_count,
            positive_customer_count, unlabeled_customer_count,
            positive_customer_rate
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "Phase 4 schema fixture",
            "2026-08-21T00:00:00Z",
            "2026-08-21T00:00:01Z",
            "COMPLETED",
            "ATTRIBUTED_PURCHASE",
            "{}",
            "{}",
            1,
            1,
            1,
            0,
            1.0,
        ),
    )
    return int(cursor.lastrowid)


def _insert_running_model_run(connection: sqlite3.Connection, analysis_run_id: int) -> int:
    cursor = connection.execute(
        """
        INSERT INTO model_runs (
            analysis_run_id,
            model_name,
            created_at,
            status,
            random_seed,
            validation_fraction
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            analysis_run_id,
            "Phase 4 model fixture",
            "2026-08-21T00:00:02Z",
            "RUNNING",
            42,
            0.2,
        ),
    )
    return int(cursor.lastrowid)


def test_fresh_initialization_creates_schema_version_four_with_jobs(database_path: Path) -> None:
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        schema_version = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert schema_version == "9"
    assert "jobs" in tables
    assert "scoring_runs" in tables
    assert "propensity_scores" in tables


def test_populated_version_three_database_migrates_to_version_four_additively(
    database_path: Path,
) -> None:
    _create_version_three_database(database_path)
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO customers (
                customer_id,
                date_of_birth,
                state,
                individual_yearly_income,
                family_member_count
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("CUS_V3", "1985-06-15", "Ohio", 72_500, 2),
        )
        connection.execute(
            """
            INSERT INTO campaign_sales (
                campaign_sales_id, customer_id, campaign_id, product_id,
                campaign_start_date, campaign_end_date, contact_date,
                contacted_flag, engagement_flag, response_flag, purchase_flag,
                campaign_attributed_sale_flag, pu_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "CS_V3",
                "CUS_V3",
                "CMP_V3",
                "PRD_V3",
                "2025-01-01",
                "2025-01-31",
                "2025-01-10",
                1,
                1,
                1,
                1,
                1,
                1,
            ),
        )
        analysis_run_id = _insert_historical_run(connection)
        _insert_running_model_run(connection, analysis_run_id)

    preserved_tables = (
        "customers",
        "campaign_sales",
        "demographics",
        "data_import_runs",
        "historical_analysis_runs",
        "model_runs",
    )
    with get_connection(database_path) as connection:
        before_counts = {
            table: connection.execute(f"SELECT COUNT(1) FROM {table}").fetchone()[0]
            for table in preserved_tables
        }

    initialize_database(database_path)
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        after_counts = {
            table: connection.execute(f"SELECT COUNT(1) FROM {table}").fetchone()[0]
            for table in preserved_tables
        }
        schema_version = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
        jobs_count = connection.execute("SELECT COUNT(1) FROM jobs").fetchone()[0]

    assert schema_version == "9"
    assert after_counts == before_counts
    assert jobs_count == 0


def test_failed_version_four_migration_rolls_back_schema_and_version(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_version_three_database(database_path)

    def fail_migration(connection: sqlite3.Connection) -> None:
        connection.execute("CREATE TABLE migration_should_rollback_v4 (id INTEGER)")
        raise RuntimeError("forced v4 migration failure")

    monkeypatch.setitem(MIGRATIONS, 4, fail_migration)

    with pytest.raises(RuntimeError, match="forced v4 migration failure"):
        initialize_database(database_path)

    with get_connection(database_path) as connection:
        schema_version = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert schema_version == "3"
    assert "jobs" not in tables
    assert "migration_should_rollback_v4" not in tables


def test_jobs_table_constraints_foreign_keys_and_indexes(database_path: Path) -> None:
    initialize_database(database_path)
    with get_connection(database_path, write=True) as connection:
        analysis_run_id = _insert_historical_run(connection)
        model_run_id = _insert_running_model_run(connection, analysis_run_id)

    with get_connection(database_path) as connection:
        columns = tuple(row["name"] for row in connection.execute("PRAGMA table_info(jobs)"))
        indexes = {
            row["name"] for row in connection.execute("PRAGMA index_list(jobs)").fetchall()
        }
        foreign_keys = connection.execute("PRAGMA foreign_key_list(jobs)").fetchall()

    assert columns == JOB_COLUMNS
    assert set(PHASE_FOUR_REQUIRED_INDEX_STATEMENTS) <= indexes
    assert {
        (row["from"], row["table"])
        for row in foreign_keys
    } == {
        ("analysis_run_id", "historical_analysis_runs"),
        ("model_run_id", "model_runs"),
    }

    valid_insert = (
        "MODEL_TRAINING",
        "QUEUED",
        0,
        "QUEUED",
        analysis_run_id,
        None,
        "2026-08-21T00:00:10Z",
        '{"analysis_run_id":1,"model_name":null,"random_seed":42,'
        '"run_elkan_challenger":true,"validation_fraction":0.2}',
    )
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO jobs (
                job_type, status, progress_percent, stage, analysis_run_id,
                model_run_id, created_at, request_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            valid_insert,
        )

    invalid_rows = (
        (
            "INVALID",
            "QUEUED",
            0,
            "QUEUED",
            analysis_run_id,
            None,
            "2026-08-21T00:00:11Z",
            "{}",
        ),
        (
            "MODEL_TRAINING",
            "INVALID",
            0,
            "QUEUED",
            analysis_run_id,
            None,
            "2026-08-21T00:00:12Z",
            "{}",
        ),
        (
            "MODEL_TRAINING",
            "QUEUED",
            -1,
            "QUEUED",
            analysis_run_id,
            None,
            "2026-08-21T00:00:13Z",
            "{}",
        ),
        (
            "MODEL_TRAINING",
            "RUNNING",
            0,
            "STARTING",
            analysis_run_id,
            None,
            "2026-08-21T00:00:14Z",
            "{}",
        ),
        (
            "MODEL_TRAINING",
            "COMPLETED",
            99,
            "COMPLETED",
            analysis_run_id,
            model_run_id,
            "2026-08-21T00:00:15Z",
            "{}",
        ),
        (
            "MODEL_TRAINING",
            "FAILED",
            20,
            "FAILED",
            analysis_run_id,
            model_run_id,
            "2026-08-21T00:00:16Z",
            "{}",
        ),
    )
    for row in invalid_rows:
        with pytest.raises(sqlite3.IntegrityError):
            with get_connection(database_path, write=True) as connection:
                connection.execute(
                    """
                    INSERT INTO jobs (
                        job_type, status, progress_percent, stage, analysis_run_id,
                        model_run_id, created_at, request_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row,
                )

    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(database_path, write=True) as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    job_type, status, progress_percent, stage, analysis_run_id,
                    created_at, request_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "MODEL_TRAINING",
                    "QUEUED",
                    0,
                    "QUEUED",
                    999999,
                    "2026-08-21T00:00:17Z",
                    "{}",
                ),
            )

    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(database_path, write=True) as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    job_type, status, progress_percent, stage, analysis_run_id,
                    model_run_id, created_at, request_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "MODEL_TRAINING",
                    "QUEUED",
                    0,
                    "QUEUED",
                    analysis_run_id,
                    999999,
                    "2026-08-21T00:00:18Z",
                    "{}",
                ),
            )