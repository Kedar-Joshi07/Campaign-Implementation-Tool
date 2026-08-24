from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import (
    CREATE_TABLE_STATEMENTS,
    MIGRATIONS,
    MODEL_RUN_COLUMNS,
    PHASE_THREE_REQUIRED_INDEX_STATEMENTS,
    initialize_database,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "phase3-schema.db"


def _create_version_two_database(database_path: Path) -> None:
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
            "Phase 3 schema fixture",
            "2026-08-21T00:00:00Z",
            "2026-08-21T00:00:01Z",
            "COMPLETED",
            "ATTRIBUTED_PURCHASE",
            '{"contact_date_to":"2025-12-31"}',
            '{"summary":{"selected_customer_count":1}}',
            2,
            1,
            1,
            0,
            1.0,
        ),
    )
    return int(cursor.lastrowid)


def test_fresh_initialization_creates_schema_version_three(database_path: Path) -> None:
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        version = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert version == "5"
    assert "model_runs" in tables
    assert "scoring_runs" in tables
    assert "propensity_scores" in tables


def test_populated_version_two_migration_preserves_phase_one_and_two_rows(
    database_path: Path,
) -> None:
    _create_version_two_database(database_path)
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO customers (
                customer_id, first_name, date_of_birth, state,
                individual_yearly_income, family_member_count
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("CUS_V2", "Preserved", "1985-06-15", "Ohio", 72_500, 2),
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
                "CS_V2", "CUS_V2", "CMP_V2", "PRD_V2", "2025-01-01",
                "2025-01-31", "2025-01-10", 1, 1, 1, 1, 1, 1,
            ),
        )
        connection.execute(
            """
            INSERT INTO demographics (
                person_id, age, state, individual_yearly_income,
                family_member_count, number_of_children_in_family,
                number_of_adults_in_family, family_yearly_income
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("PER_V2", 40, "Ohio", 80_000, 2, 0, 2, 120_000),
        )
        connection.execute(
            """
            INSERT INTO data_import_runs (
                dataset_name, source_path, started_at, completed_at, status,
                rows_read, rows_inserted, rows_rejected
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "customers", "customers.csv.gz", "2026-08-20T00:00:00Z",
                "2026-08-20T00:01:00Z", "COMPLETED", 1, 1, 0,
            ),
        )
        analysis_run_id = _insert_historical_run(connection)

    preserved_tables = (
        "customers",
        "campaign_sales",
        "demographics",
        "data_import_runs",
        "historical_analysis_runs",
    )
    with get_connection(database_path) as connection:
        counts_before = {
            table: connection.execute(f"SELECT COUNT(1) FROM {table}").fetchone()[0]
            for table in preserved_tables
        }
        snapshot_before = tuple(
            connection.execute(
                """
                SELECT analysis_run_id, status, filters_json, results_json,
                       selected_customer_count, positive_customer_count,
                       unlabeled_customer_count
                FROM historical_analysis_runs WHERE analysis_run_id = ?
                """,
                (analysis_run_id,),
            ).fetchone()
        )

    initialize_database(database_path)
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        counts_after = {
            table: connection.execute(f"SELECT COUNT(1) FROM {table}").fetchone()[0]
            for table in preserved_tables
        }
        snapshot_after = tuple(
            connection.execute(
                """
                SELECT analysis_run_id, status, filters_json, results_json,
                       selected_customer_count, positive_customer_count,
                       unlabeled_customer_count
                FROM historical_analysis_runs WHERE analysis_run_id = ?
                """,
                (analysis_run_id,),
            ).fetchone()
        )
        version = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]

    assert version == "5"
    assert counts_after == counts_before
    assert snapshot_after == snapshot_before


def test_model_runs_columns_constraints_foreign_key_and_indexes(
    database_path: Path,
) -> None:
    initialize_database(database_path)
    with get_connection(database_path) as connection:
        columns = tuple(
            row["name"] for row in connection.execute("PRAGMA table_info(model_runs)")
        )
        indexes = {
            row["name"]
            for row in connection.execute("PRAGMA index_list(model_runs)").fetchall()
        }
        foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(model_runs)"
        ).fetchall()

    assert columns == MODEL_RUN_COLUMNS
    assert set(PHASE_THREE_REQUIRED_INDEX_STATEMENTS) <= indexes
    assert len(foreign_keys) == 1
    assert foreign_keys[0]["table"] == "historical_analysis_runs"
    assert foreign_keys[0]["from"] == "analysis_run_id"

    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(database_path, write=True) as connection:
            connection.execute(
                """
                INSERT INTO model_runs (
                    analysis_run_id, model_name, created_at, status,
                    random_seed, validation_fraction
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (999, "Unknown analysis", "2026-08-21T00:00:00Z", "RUNNING", 42, 0.2),
            )

    with get_connection(database_path, write=True) as connection:
        analysis_run_id = _insert_historical_run(connection)
        connection.execute(
            """
            INSERT INTO model_runs (
                analysis_run_id, model_name, created_at, status,
                random_seed, validation_fraction
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_run_id,
                "Valid running model",
                "2026-08-21T00:00:00Z",
                "RUNNING",
                42,
                0.2,
            ),
        )

    invalid_rows = (
        ("INVALID", 0.2, 0, 0, 0, 0, 0, 0, 0, None),
        ("RUNNING", 0.0, 0, 0, 0, 0, 0, 0, 0, None),
        ("RUNNING", 1.0, 0, 0, 0, 0, 0, 0, 0, None),
        ("RUNNING", 0.2, -1, 0, 0, 0, 0, 0, 0, None),
        ("COMPLETED", 0.2, 1, 2, 1, 0, 2, 0, 1, None),
        ("RUNNING", 0.2, 1, 0, 0, 0, 0, 0, 0, "not-a-sha"),
    )
    for values in invalid_rows:
        with pytest.raises(sqlite3.IntegrityError):
            with get_connection(database_path, write=True) as connection:
                connection.execute(
                    """
                    INSERT INTO model_runs (
                        analysis_run_id, model_name, created_at, status,
                        random_seed, validation_fraction,
                        reconstructed_observation_count,
                        selected_customer_count, positive_customer_count,
                        unlabeled_customer_count, train_customer_count,
                        validation_customer_count, train_positive_count,
                        artifact_sha256
                    ) VALUES (?, 'Invalid fixture', '2026-08-21T00:00:00Z',
                              ?, 42, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (analysis_run_id, *values),
                )


def test_failed_version_three_migration_rolls_back_schema_and_version(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_version_two_database(database_path)

    def fail_migration(connection: sqlite3.Connection) -> None:
        connection.execute("CREATE TABLE migration_should_rollback (id INTEGER)")
        raise RuntimeError("forced v3 migration failure")

    monkeypatch.setitem(MIGRATIONS, 3, fail_migration)

    with pytest.raises(RuntimeError, match="forced v3 migration failure"):
        initialize_database(database_path)

    with get_connection(database_path) as connection:
        version = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert version == "2"
    assert "migration_should_rollback" not in tables
    assert "model_runs" not in tables


def test_model_artifact_runtime_paths_are_ignored() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    artifact_paths = (
        "artifacts/models/model_run_000001/pu_model.joblib",
        "artifacts/models/model_run_000001/metadata.json",
    )
    ignored_artifacts = [
        subprocess.run(
            ("git", "check-ignore", "--quiet", "--", artifact_path),
            cwd=repository_root,
            check=False,
        )
        for artifact_path in artifact_paths
    ]
    tracked_placeholder = subprocess.run(
        ("git", "check-ignore", "--quiet", "--", "artifacts/models/.gitkeep"),
        cwd=repository_root,
        check=False,
    )

    assert all(result.returncode == 0 for result in ignored_artifacts)
    assert tracked_placeholder.returncode == 1
