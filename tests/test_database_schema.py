from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import (
    CAMPAIGN_SALES_COLUMNS,
    CUSTOMER_COLUMNS,
    DEMOGRAPHIC_COLUMNS,
    EXPECTED_TABLES,
    SCHEMA_VERSION,
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

