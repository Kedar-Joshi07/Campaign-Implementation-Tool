from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import (
    AUDIENCE_RANK_BOUNDARY_COLUMNS,
    CREATE_TABLE_STATEMENTS,
    MIGRATIONS,
    PHASE_SIX_REQUIRED_INDEX_STATEMENTS,
    SAVED_AUDIENCE_COLUMNS,
    initialize_database,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "phase6-schema.db"


def _create_version_eight_database(database_path: Path) -> None:
    with get_connection(database_path, write=True) as connection:
        for statement in CREATE_TABLE_STATEMENTS:
            connection.execute(statement)
        connection.executemany(
            """
            INSERT INTO app_metadata (key, value, updated_at)
            VALUES (?, ?, '2026-09-01T00:00:00Z')
            """,
            (
                ("schema_version", "1"),
                ("application_version", "0.1.0"),
                ("database_initialized_at", "2026-09-01T00:00:00Z"),
            ),
        )
        for version in (2, 3, 4, 5, 6, 7, 8):
            MIGRATIONS[version](connection)
            connection.execute(
                "UPDATE app_metadata SET value = ? WHERE key = 'schema_version'",
                (str(version),),
            )


def _insert_completed_analysis(connection: sqlite3.Connection) -> int:
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
            "Phase 6 schema fixture",
            "2026-09-01T00:00:00Z",
            "2026-09-01T00:00:03Z",
            "COMPLETED",
            "ATTRIBUTED_PURCHASE",
            "{}",
            "{}",
            100,
            20,
            5,
            15,
            0.25,
        ),
    )
    return int(cursor.lastrowid)


def _insert_model_run(connection: sqlite3.Connection, analysis_run_id: int) -> int:
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
            "Phase 6 model fixture",
            "2026-09-01T00:00:05Z",
            "RUNNING",
            42,
            0.2,
        ),
    )
    return int(cursor.lastrowid)


def _insert_running_scoring_job(connection: sqlite3.Connection, model_run_id: int) -> int:
    cursor = connection.execute(
        """
        INSERT INTO jobs (
            job_type,
            status,
            progress_percent,
            stage,
            analysis_run_id,
            model_run_id,
            created_at,
            started_at,
            request_json,
            result_json,
            error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "PROSPECT_SCORING",
            "RUNNING",
            1,
            "VALIDATING_MODEL",
            None,
            model_run_id,
            "2026-09-01T00:00:10Z",
            "2026-09-01T00:00:10Z",
            "{}",
            None,
            None,
        ),
    )
    return int(cursor.lastrowid)


def _insert_scoring_run(connection: sqlite3.Connection, job_id: int, model_run_id: int) -> int:
    cursor = connection.execute(
        """
        INSERT INTO scoring_runs (
            job_id,
            model_run_id,
            created_at,
            completed_at,
            status,
            demographic_snapshot_count,
            demographic_min_person_id,
            demographic_max_person_id,
            scored_person_count,
            chunk_size,
            selected_candidate,
            model_role_policy_version,
            feature_contract_version,
            feature_contract_sha256,
            artifact_sha256,
            score_min,
            score_max,
            score_mean,
            score_summary_json,
            error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            model_run_id,
            "2026-09-01T00:00:11Z",
            "2026-09-01T00:00:20Z",
            "COMPLETED",
            1,
            "PER_001",
            "PER_001",
            1,
            1000,
            "BAGGING_PU",
            "2",
            "1",
            "a" * 64,
            "b" * 64,
            0.2,
            0.8,
            0.4,
            "{}",
            None,
        ),
    )
    return int(cursor.lastrowid)


def _insert_data_import_run(connection: sqlite3.Connection, dataset_name: str) -> int:
    cursor = connection.execute(
        """
        INSERT INTO data_import_runs (
            dataset_name,
            source_path,
            started_at,
            completed_at,
            status,
            rows_read,
            rows_inserted,
            rows_rejected,
            source_checksum
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dataset_name,
            f"{dataset_name}.csv.gz",
            "2026-09-01T00:00:00Z",
            "2026-09-01T00:00:01Z",
            "COMPLETED",
            1,
            1,
            0,
            "c" * 64,
        ),
    )
    return int(cursor.lastrowid)


def test_migration_from_v8_creates_phase6_tables_and_preserves_rows(database_path: Path) -> None:
    _create_version_eight_database(database_path)
    with get_connection(database_path, write=True) as connection:
        analysis_run_id = _insert_completed_analysis(connection)
        model_run_id = _insert_model_run(connection, analysis_run_id)
        job_id = _insert_running_scoring_job(connection, model_run_id)
        _insert_scoring_run(connection, job_id, model_run_id)

    initialize_database(database_path)
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        schema_version = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
        job_count = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        scoring_count = connection.execute("SELECT COUNT(*) FROM scoring_runs").fetchone()[0]
        boundary_columns = tuple(
            row["name"]
            for row in connection.execute("PRAGMA table_info(audience_rank_boundaries)").fetchall()
        )
        audience_columns = tuple(
            row["name"]
            for row in connection.execute("PRAGMA table_info(saved_audiences)").fetchall()
        )
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert schema_version == "9"
    assert job_count == 1
    assert scoring_count == 1
    assert boundary_columns == AUDIENCE_RANK_BOUNDARY_COLUMNS
    assert audience_columns == SAVED_AUDIENCE_COLUMNS
    assert "audience_members" not in tables


def test_phase6_table_constraints_and_indexes(database_path: Path) -> None:
    initialize_database(database_path)
    with get_connection(database_path, write=True) as connection:
        analysis_run_id = _insert_completed_analysis(connection)
        model_run_id = _insert_model_run(connection, analysis_run_id)
        job_id = _insert_running_scoring_job(connection, model_run_id)
        scoring_run_id = _insert_scoring_run(connection, job_id, model_run_id)
        customer_import_id = _insert_data_import_run(connection, "customers")
        campaign_import_id = _insert_data_import_run(connection, "campaign_sales")
        demographic_import_id = _insert_data_import_run(connection, "demographics")

    with get_connection(database_path) as connection:
        existing_indexes = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }

    assert set(PHASE_SIX_REQUIRED_INDEX_STATEMENTS) <= existing_indexes

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO audience_rank_boundaries (
                scoring_run_id,
                percentile_bucket,
                boundary_rank,
                boundary_score,
                boundary_person_id,
                total_population,
                rank_contract_version,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scoring_run_id,
                100,
                1,
                0.75,
                "PER_001",
                1,
                "1",
                "2026-09-01T00:10:00Z",
            ),
        )

    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(database_path, write=True) as connection:
            connection.execute(
                """
                INSERT INTO audience_rank_boundaries (
                    scoring_run_id,
                    percentile_bucket,
                    boundary_rank,
                    boundary_score,
                    boundary_person_id,
                    total_population,
                    rank_contract_version,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scoring_run_id,
                    100,
                    0,
                    0.75,
                    "PER_001",
                    1,
                    "1",
                    "2026-09-01T00:10:01Z",
                ),
            )

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO saved_audiences (
                audience_name,
                description,
                created_at,
                scoring_run_id,
                model_run_id,
                analysis_run_id,
                selection_mode,
                target_count,
                resolved_count,
                filter_contract_version,
                rank_contract_version,
                selection_contract_version,
                filters_json,
                selection_json,
                profile_summary_json,
                customer_import_id,
                customer_source_checksum,
                campaign_sales_import_id,
                campaign_sales_source_checksum,
                demographic_import_id,
                demographic_source_checksum,
                feature_contract_version,
                feature_contract_sha256,
                artifact_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Audience A",
                "Saved immutable audience",
                "2026-09-01T00:11:00Z",
                scoring_run_id,
                model_run_id,
                analysis_run_id,
                "TOP_N",
                10,
                10,
                "1",
                "1",
                "1",
                "{\"state\":[\"Ohio\"]}",
                "{\"sort\":\"score_desc\"}",
                "{\"overview\":{\"rows\":10}}",
                customer_import_id,
                "d" * 64,
                campaign_import_id,
                "e" * 64,
                demographic_import_id,
                "f" * 64,
                "1",
                "1" * 64,
                "2" * 64,
            ),
        )

    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(database_path, write=True) as connection:
            connection.execute(
                """
                INSERT INTO saved_audiences (
                    audience_name,
                    description,
                    created_at,
                    scoring_run_id,
                    model_run_id,
                    analysis_run_id,
                    selection_mode,
                    target_count,
                    resolved_count,
                    filter_contract_version,
                    rank_contract_version,
                    selection_contract_version,
                    filters_json,
                    selection_json,
                    profile_summary_json,
                    customer_import_id,
                    customer_source_checksum,
                    campaign_sales_import_id,
                    campaign_sales_source_checksum,
                    demographic_import_id,
                    demographic_source_checksum,
                    feature_contract_version,
                    feature_contract_sha256,
                    artifact_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Audience B",
                    None,
                    "2026-09-01T00:12:00Z",
                    scoring_run_id,
                    model_run_id,
                    analysis_run_id,
                    "TOP_N",
                    None,
                    5,
                    "1",
                    "1",
                    "1",
                    "{\"state\":[\"Ohio\"]}",
                    "{\"sort\":\"score_desc\"}",
                    None,
                    customer_import_id,
                    "d" * 64,
                    campaign_import_id,
                    "e" * 64,
                    demographic_import_id,
                    "f" * 64,
                    "1",
                    "1" * 64,
                    "2" * 64,
                ),
            )
