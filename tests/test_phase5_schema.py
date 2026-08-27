from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import (
    CREATE_TABLE_STATEMENTS,
    JOB_COLUMNS,
    MIGRATIONS,
    PHASE_FIVE_REQUIRED_INDEX_STATEMENTS,
    PROPENSITY_SCORE_COLUMNS,
    SCORING_RUN_COLUMNS,
    initialize_database,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "phase5-schema.db"


def _create_version_four_database(database_path: Path) -> None:
    with get_connection(database_path, write=True) as connection:
        for statement in CREATE_TABLE_STATEMENTS:
            connection.execute(statement)
        connection.executemany(
            """
            INSERT INTO app_metadata (key, value, updated_at)
            VALUES (?, ?, '2026-08-25T00:00:00Z')
            """,
            (
                ("schema_version", "1"),
                ("application_version", "0.1.0"),
                ("database_initialized_at", "2026-08-25T00:00:00Z"),
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
        MIGRATIONS[4](connection)
        connection.execute(
            "UPDATE app_metadata SET value = '4' WHERE key = 'schema_version'"
        )


def _create_legacy_version_five_database(database_path: Path) -> None:
    _create_version_four_database(database_path)
    with get_connection(database_path, write=True) as connection:
        MIGRATIONS[5](connection)
        connection.execute(
            "UPDATE app_metadata SET value = '5' WHERE key = 'schema_version'"
        )
        connection.execute("DROP INDEX IF EXISTS idx_scoring_runs_completed_model_unique")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_scoring_runs_completed_model_unique
            ON scoring_runs (model_run_id)
            WHERE status = 'COMPLETED'
            """
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
            "Phase 5 schema fixture",
            "2026-08-25T00:00:00Z",
            "2026-08-25T00:00:03Z",
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
            "Phase 5 model fixture",
            "2026-08-25T00:00:05Z",
            "RUNNING",
            42,
            0.2,
        ),
    )
    return int(cursor.lastrowid)


def _insert_demographic_person(connection: sqlite3.Connection, person_id: str) -> None:
    connection.execute(
        """
        INSERT INTO demographics (
            person_id, age, state, individual_yearly_income,
            family_member_count, number_of_children_in_family,
            number_of_adults_in_family, family_yearly_income
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (person_id, 40, "Ohio", 80_000, 2, 0, 2, 120_000),
    )


def _insert_scoring_job(
    connection: sqlite3.Connection,
    *,
    model_run_id: int,
    created_at: str,
) -> int:
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
            finished_at,
            request_json,
            result_json,
            error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "PROSPECT_SCORING",
            "RUNNING",
            1,
            "VALIDATING_MODEL",
            None,
            model_run_id,
            created_at,
            created_at,
            None,
            "{}",
            None,
            None,
        ),
    )
    return int(cursor.lastrowid)


def test_migration_from_v4_preserves_jobs_and_is_idempotent(database_path: Path) -> None:
    _create_version_four_database(database_path)
    with get_connection(database_path, write=True) as connection:
        analysis_run_id = _insert_completed_analysis(connection)
        connection.execute(
            """
            INSERT INTO jobs (
                job_type,
                status,
                progress_percent,
                stage,
                analysis_run_id,
                model_run_id,
                created_at,
                request_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "MODEL_TRAINING",
                "QUEUED",
                0,
                "QUEUED",
                analysis_run_id,
                None,
                "2026-08-25T00:10:00Z",
                '{"analysis_run_id":1,"model_name":null,"random_seed":42,"run_elkan_challenger":true,"validation_fraction":0.2}',
            ),
        )

    initialize_database(database_path)
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        schema_version = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
        jobs_count = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        job_columns = tuple(
            row["name"] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
        )
        scoring_columns = tuple(
            row["name"]
            for row in connection.execute("PRAGMA table_info(scoring_runs)").fetchall()
        )
        score_columns = tuple(
            row["name"]
            for row in connection.execute("PRAGMA table_info(propensity_scores)").fetchall()
        )
        index_names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }

    assert schema_version == "8"
    assert jobs_count == 1
    assert job_columns == JOB_COLUMNS
    assert scoring_columns == SCORING_RUN_COLUMNS
    assert score_columns == PROPENSITY_SCORE_COLUMNS
    assert set(PHASE_FIVE_REQUIRED_INDEX_STATEMENTS) <= index_names


def test_failed_v5_migration_rolls_back_schema_and_version(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_version_four_database(database_path)

    def fail_migration(connection: sqlite3.Connection) -> None:
        connection.execute("CREATE TABLE migration_should_rollback_v5 (id INTEGER)")
        raise RuntimeError("forced v5 migration failure")

    monkeypatch.setitem(MIGRATIONS, 5, fail_migration)

    with pytest.raises(RuntimeError, match="forced v5 migration failure"):
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

    assert schema_version == "4"
    assert "migration_should_rollback_v5" not in tables
    assert "scoring_runs" not in tables
    assert "propensity_scores" not in tables


def test_legacy_v5_completed_run_uniqueness_migrates_to_v6_non_unique_preserving_rows(
    database_path: Path,
) -> None:
    _create_legacy_version_five_database(database_path)

    with get_connection(database_path, write=True) as connection:
        analysis_run_id = _insert_completed_analysis(connection)
        model_run_id = _insert_model_run(connection, analysis_run_id)
        _insert_demographic_person(connection, "PER_001")

        first_job_id = _insert_scoring_job(
            connection,
            model_run_id=model_run_id,
            created_at="2026-08-25T01:10:00Z",
        )
        second_job_id = _insert_scoring_job(
            connection,
            model_run_id=model_run_id,
            created_at="2026-08-25T01:10:01Z",
        )

        connection.execute(
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
                first_job_id,
                model_run_id,
                "2026-08-25T01:10:05Z",
                "2026-08-25T01:10:20Z",
                "COMPLETED",
                1,
                "PER_001",
                "PER_001",
                1,
                10_000,
                "BAGGING_PU",
                "2",
                "1",
                "a" * 64,
                "b" * 64,
                0.20,
                0.80,
                0.45,
                "{}",
                None,
            ),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
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
                    second_job_id,
                    model_run_id,
                    "2026-08-25T01:10:06Z",
                    "2026-08-25T01:10:21Z",
                    "COMPLETED",
                    1,
                    "PER_001",
                    "PER_001",
                    1,
                    10_000,
                    "BAGGING_PU",
                    "2",
                    "1",
                    "c" * 64,
                    "d" * 64,
                    0.25,
                    0.85,
                    0.50,
                    "{}",
                    None,
                ),
            )

    initialize_database(database_path)

    with get_connection(database_path, write=True) as connection:
        schema_version = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
        legacy_index_row = connection.execute(
            """
            SELECT name
            FROM pragma_index_list('scoring_runs')
            WHERE name = 'idx_scoring_runs_completed_model_unique'
            """
        ).fetchone()
        index_row = connection.execute(
            """
            SELECT "unique"
            FROM pragma_index_list('scoring_runs')
            WHERE name = 'idx_scoring_runs_completed_model_newest'
            """
        ).fetchone()
        assert legacy_index_row is None
        assert index_row is not None
        assert int(index_row["unique"]) == 0

        connection.execute(
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
                second_job_id,
                model_run_id,
                "2026-08-25T01:10:06Z",
                "2026-08-25T01:10:21Z",
                "COMPLETED",
                1,
                "PER_001",
                "PER_001",
                1,
                10_000,
                "BAGGING_PU",
                "2",
                "1",
                "c" * 64,
                "d" * 64,
                0.25,
                0.85,
                0.50,
                "{}",
                None,
            ),
        )
        completed_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM scoring_runs
            WHERE model_run_id = ? AND status = 'COMPLETED'
            """,
            (model_run_id,),
        ).fetchone()[0]

    assert schema_version == "8"
    assert completed_count == 2


def test_scoring_runs_and_propensity_scores_constraints(database_path: Path) -> None:
    initialize_database(database_path)

    with get_connection(database_path, write=True) as connection:
        analysis_run_id = _insert_completed_analysis(connection)
        model_run_id = _insert_model_run(connection, analysis_run_id)
        _insert_demographic_person(connection, "PER_001")

        first_job_id = _insert_scoring_job(
            connection,
            model_run_id=model_run_id,
            created_at="2026-08-25T01:00:00Z",
        )
        second_job_id = _insert_scoring_job(
            connection,
            model_run_id=model_run_id,
            created_at="2026-08-25T01:00:01Z",
        )

        first_run_id = connection.execute(
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
                first_job_id,
                model_run_id,
                "2026-08-25T01:00:10Z",
                "2026-08-25T01:00:20Z",
                "COMPLETED",
                1,
                "PER_001",
                "PER_001",
                1,
                10_000,
                "BAGGING_PU",
                "2",
                "1",
                "a" * 64,
                "b" * 64,
                0.20,
                0.80,
                0.45,
                "{}",
                None,
            ),
        ).lastrowid

        connection.execute(
            """
            INSERT INTO scoring_runs (
                job_id,
                model_run_id,
                created_at,
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
                artifact_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                second_job_id,
                model_run_id,
                "2026-08-25T01:00:11Z",
                "RUNNING",
                10,
                "PER_001",
                "PER_001",
                0,
                10_000,
                "BAGGING_PU",
                "2",
                "1",
                "c" * 64,
                "d" * 64,
            ),
        )

        second_completed_run_id = connection.execute(
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
                _insert_scoring_job(
                    connection,
                    model_run_id=model_run_id,
                    created_at="2026-08-25T01:00:02Z",
                ),
                model_run_id,
                "2026-08-25T01:00:12Z",
                "2026-08-25T01:00:25Z",
                "COMPLETED",
                1,
                "PER_001",
                "PER_001",
                1,
                10_000,
                "BAGGING_PU",
                "2",
                "1",
                "e" * 64,
                "f" * 64,
                0.25,
                0.85,
                0.50,
                "{}",
                None,
            ),
        ).lastrowid

        assert second_completed_run_id != first_run_id

        connection.execute(
            """
            INSERT INTO propensity_scores (
                scoring_run_id,
                model_run_id,
                person_id,
                propensity_score
            ) VALUES (?, ?, ?, ?)
            """,
            (
                first_run_id,
                model_run_id,
                "PER_001",
                0.87,
            ),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO propensity_scores (
                    scoring_run_id,
                    model_run_id,
                    person_id,
                    propensity_score
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    first_run_id,
                    model_run_id,
                    "PER_001",
                    0.10,
                ),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO propensity_scores (
                    scoring_run_id,
                    model_run_id,
                    person_id,
                    propensity_score
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    first_run_id,
                    model_run_id,
                    "PER_001",
                    1.20,
                ),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO propensity_scores (
                    scoring_run_id,
                    model_run_id,
                    person_id,
                    propensity_score
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    first_run_id,
                    model_run_id + 1,
                    "PER_001",
                    0.55,
                ),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO propensity_scores (
                    scoring_run_id,
                    model_run_id,
                    person_id,
                    propensity_score
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    first_run_id,
                    model_run_id,
                    "PER_UNKNOWN",
                    0.55,
                ),
            )
