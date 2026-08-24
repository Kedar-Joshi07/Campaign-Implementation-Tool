from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import (
    CAMPAIGN_SALES_COLUMNS,
    CREATE_TABLE_STATEMENTS,
    CUSTOMER_COLUMNS,
    DEMOGRAPHIC_COLUMNS,
    EXPECTED_TABLES,
    HISTORICAL_ANALYSIS_RUN_COLUMNS,
    MIGRATIONS,
    PHASE_TWO_REQUIRED_INDEX_STATEMENTS,
    SCHEMA_VERSION,
    UnsupportedSchemaVersionError,
    initialize_database,
    inspect_database,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "nested" / "phase1_test.db"


def _table_names(database_path: Path) -> set[str]:
    with get_connection(database_path) as connection:
        return {
            row["name"]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            ).fetchall()
        }


def _column_names(database_path: Path, table_name: str) -> tuple[str, ...]:
    with get_connection(database_path) as connection:
        return tuple(row["name"] for row in connection.execute(f"PRAGMA table_info({table_name})"))


def _create_version_one_database(database_path: Path) -> None:
    with get_connection(database_path, write=True) as connection:
        for statement in CREATE_TABLE_STATEMENTS:
            connection.execute(statement)
        connection.executemany(
            """
            INSERT INTO app_metadata (key, value, updated_at)
            VALUES (?, ?, '2026-08-20T00:00:00Z')
            """,
            (
                ("schema_version", "1"),
                ("application_version", "0.1.0"),
                ("database_initialized_at", "2026-08-20T00:00:00Z"),
            ),
        )


def test_database_initialization_creates_file_and_metadata(database_path: Path) -> None:
    initialized_path = initialize_database(database_path)

    assert initialized_path == database_path
    assert database_path.is_file()
    with get_connection(database_path) as connection:
        metadata = {
            row["key"]: row["value"]
            for row in connection.execute("SELECT key, value FROM app_metadata").fetchall()
        }

    assert metadata["schema_version"] == SCHEMA_VERSION
    assert metadata["application_version"]
    assert metadata["database_initialized_at"]


def test_expected_tables_exist(database_path: Path) -> None:
    initialize_database(database_path)

    assert _table_names(database_path) == set(EXPECTED_TABLES)


@pytest.mark.parametrize(
    ("table_name", "expected_columns"),
    (
        ("customers", CUSTOMER_COLUMNS),
        ("campaign_sales", CAMPAIGN_SALES_COLUMNS),
        ("demographics", DEMOGRAPHIC_COLUMNS),
    ),
)
def test_frozen_table_columns_are_exact(
    database_path: Path,
    table_name: str,
    expected_columns: tuple[str, ...],
) -> None:
    initialize_database(database_path)

    assert _column_names(database_path, table_name) == expected_columns


def test_connections_enable_foreign_keys_and_row_factory(database_path: Path) -> None:
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        foreign_keys_enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        metadata_row = connection.execute(
            "SELECT key, value FROM app_metadata WHERE key = ?",
            ("schema_version",),
        ).fetchone()

    assert foreign_keys_enabled == 1
    assert isinstance(metadata_row, sqlite3.Row)


def test_campaign_sales_rejects_unknown_customer(database_path: Path) -> None:
    initialize_database(database_path)

    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(database_path, write=True) as connection:
            connection.execute(
                """
                INSERT INTO campaign_sales (
                    campaign_sales_id,
                    customer_id,
                    campaign_id,
                    product_id,
                    campaign_start_date,
                    campaign_end_date,
                    contact_date,
                    contacted_flag,
                    engagement_flag,
                    response_flag,
                    purchase_flag,
                    campaign_attributed_sale_flag,
                    pu_label
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "CS_TEST_001",
                    "CUS_DOES_NOT_EXIST",
                    "CMP_TEST",
                    "PRD_TEST",
                    "2025-01-01",
                    "2025-01-10",
                    "2025-01-02",
                    1,
                    0,
                    0,
                    0,
                    0,
                    0,
                ),
            )


def test_demographics_has_no_foreign_keys(database_path: Path) -> None:
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        foreign_keys = connection.execute("PRAGMA foreign_key_list(demographics)").fetchall()

    assert foreign_keys == []


def test_initialization_is_idempotent_and_preserves_rows(database_path: Path) -> None:
    initialize_database(database_path)
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
            ("CUS_TEST_001", "1990-01-01", "California", 50000, 1),
        )

    initialize_database(database_path)
    report = inspect_database(database_path)
    customer_report = next(table for table in report["tables"] if table["name"] == "customers")

    assert customer_report["row_count"] == 1
    with get_connection(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM app_metadata").fetchone()[0] == 3


def test_populated_version_one_database_migrates_without_phase_one_data_loss(
    database_path: Path,
) -> None:
    _create_version_one_database(database_path)
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO customers (
                customer_id, first_name, date_of_birth, state,
                individual_yearly_income, family_member_count
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("CUS_V1", "Preserved", "1985-06-15", "Ohio", 72_500, 2),
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
                "CS_V1", "CUS_V1", "CMP_V1", "PRD_V1", "2025-01-01",
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
            ("PER_V1", 40, "Ohio", 80_000, 2, 0, 2, 120_000),
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

    with get_connection(database_path) as connection:
        counts_before = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("customers", "campaign_sales", "demographics", "data_import_runs")
        }
        customer_before = tuple(
            connection.execute(
                "SELECT customer_id, first_name, state, individual_yearly_income "
                "FROM customers WHERE customer_id = ?",
                ("CUS_V1",),
            ).fetchone()
        )

    initialize_database(database_path)

    with get_connection(database_path) as connection:
        counts_after = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("customers", "campaign_sales", "demographics", "data_import_runs")
        }
        customer_after = tuple(
            connection.execute(
                "SELECT customer_id, first_name, state, individual_yearly_income "
                "FROM customers WHERE customer_id = ?",
                ("CUS_V1",),
            ).fetchone()
        )
        stored_version = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]

    assert counts_after == counts_before
    assert customer_after == customer_before
    assert stored_version == "5"


def test_historical_analysis_table_columns_constraints_and_indexes(database_path: Path) -> None:
    initialize_database(database_path)

    assert _column_names(database_path, "historical_analysis_runs") == (
        HISTORICAL_ANALYSIS_RUN_COLUMNS
    )
    with get_connection(database_path) as connection:
        existing_indexes = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }

    assert set(PHASE_TWO_REQUIRED_INDEX_STATEMENTS) <= existing_indexes

    base_values = (
        "Analysis", "2026-08-20T00:00:00Z", "RUNNING",
        "ATTRIBUTED_PURCHASE", "{}",
    )
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO historical_analysis_runs (
                analysis_name, created_at, status, conversion_definition, filters_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            base_values,
        )

    invalid_rows = (
        ("Analysis", "2026-08-20T00:00:00Z", "INVALID", "ATTRIBUTED_PURCHASE", "{}", 0, None),
        ("Analysis", "2026-08-20T00:00:00Z", "RUNNING", "INVALID", "{}", 0, None),
        ("Analysis", "2026-08-20T00:00:00Z", "RUNNING", "RESPONSE", "{}", -1, None),
        ("Analysis", "2026-08-20T00:00:00Z", "RUNNING", "ANY_PURCHASE", "{}", 0, 1.01),
    )
    for values in invalid_rows:
        with pytest.raises(sqlite3.IntegrityError):
            with get_connection(database_path, write=True) as connection:
                connection.execute(
                    """
                    INSERT INTO historical_analysis_runs (
                        analysis_name, created_at, status, conversion_definition,
                        filters_json, observation_count, positive_customer_rate
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )


def test_failed_migration_rolls_back_schema_and_version(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_version_one_database(database_path)

    def fail_migration(connection: sqlite3.Connection) -> None:
        connection.execute("CREATE TABLE migration_should_rollback (id INTEGER)")
        raise RuntimeError("forced migration failure")

    monkeypatch.setitem(MIGRATIONS, 2, fail_migration)

    with pytest.raises(RuntimeError, match="forced migration failure"):
        initialize_database(database_path)

    with get_connection(database_path) as connection:
        stored_version = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
        rollback_table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("migration_should_rollback",),
        ).fetchone()

    assert stored_version == "1"
    assert rollback_table_exists is None


def test_future_schema_version_is_rejected(database_path: Path) -> None:
    initialize_database(database_path)
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            "UPDATE app_metadata SET value = '999' WHERE key = 'schema_version'"
        )

    with pytest.raises(UnsupportedSchemaVersionError, match="newer than supported version 5"):
        initialize_database(database_path)


def test_write_context_rolls_back_on_failure(database_path: Path) -> None:
    initialize_database(database_path)

    with pytest.raises(RuntimeError):
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
                ("CUS_TEST_ROLLBACK", "1990-01-01", "Texas", 60000, 2),
            )
            raise RuntimeError("force rollback")

    with get_connection(database_path) as connection:
        row_count = connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0]

    assert row_count == 0
