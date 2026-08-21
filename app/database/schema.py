"""Idempotent SQLite schema creation and inspection."""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import APP_VERSION, DATABASE_PATH
from app.database.connection import get_connection


logger = logging.getLogger(__name__)
PHASE_ONE_SCHEMA_VERSION = 1
CURRENT_SCHEMA_VERSION = 2
SCHEMA_VERSION = str(CURRENT_SCHEMA_VERSION)

EXPECTED_TABLES = (
    "app_metadata",
    "data_import_runs",
    "customers",
    "campaign_sales",
    "demographics",
    "historical_analysis_runs",
)

HISTORICAL_ANALYSIS_RUN_COLUMNS = (
    "analysis_run_id",
    "analysis_name",
    "created_at",
    "completed_at",
    "status",
    "conversion_definition",
    "filters_json",
    "results_json",
    "observation_count",
    "selected_customer_count",
    "positive_customer_count",
    "unlabeled_customer_count",
    "positive_customer_rate",
    "error_message",
)

CUSTOMER_COLUMNS = (
    "customer_id",
    "first_name",
    "last_name",
    "gender",
    "date_of_birth",
    "address_line_1",
    "address_line_2",
    "street",
    "postal_code",
    "city",
    "state",
    "country",
    "phone_number",
    "email",
    "individual_yearly_income",
    "family_member_count",
    "resident_status",
    "resident_type",
    "education",
    "employment_status",
    "type_of_employment",
    "marital_status",
)

CAMPAIGN_SALES_COLUMNS = (
    "campaign_sales_id",
    "customer_id",
    "campaign_id",
    "product_id",
    "order_id",
    "campaign_name",
    "campaign_type",
    "campaign_channel",
    "campaign_start_date",
    "campaign_end_date",
    "campaign_category",
    "offer_type",
    "offer_value",
    "creative_id",
    "target_segment",
    "product_name",
    "product_category",
    "product_subcategory",
    "product_price",
    "product_cost",
    "product_tier",
    "product_launch_date",
    "contact_date",
    "contacted_flag",
    "delivery_status",
    "engagement_flag",
    "engagement_type",
    "response_flag",
    "purchase_flag",
    "purchase_date",
    "quantity",
    "gross_sales_amount",
    "discount_amount",
    "net_sales_amount",
    "gross_margin_amount",
    "days_to_purchase",
    "campaign_attributed_sale_flag",
    "pu_label",
)

DEMOGRAPHIC_COLUMNS = (
    "person_id",
    "first_name",
    "last_name",
    "gender",
    "age",
    "address_line_1",
    "address_line_2",
    "street",
    "postal_code",
    "city",
    "state",
    "country",
    "phone_number",
    "email",
    "individual_yearly_income",
    "marital_status",
    "education",
    "employment_status",
    "resident_status",
    "resident_type",
    "family_member_count",
    "number_of_children_in_family",
    "number_of_adults_in_family",
    "ethnicity",
    "type_of_employment",
    "occupation_industry",
    "family_yearly_income",
    "religion",
)

CREATE_TABLE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS app_metadata (
        key TEXT NOT NULL PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS data_import_runs (
        import_id INTEGER PRIMARY KEY AUTOINCREMENT,
        dataset_name TEXT NOT NULL,
        source_path TEXT NOT NULL,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
        rows_read INTEGER NOT NULL DEFAULT 0 CHECK (rows_read >= 0),
        rows_inserted INTEGER NOT NULL DEFAULT 0 CHECK (rows_inserted >= 0),
        rows_rejected INTEGER NOT NULL DEFAULT 0 CHECK (rows_rejected >= 0),
        error_message TEXT,
        source_checksum TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customers (
        customer_id TEXT NOT NULL PRIMARY KEY,
        first_name TEXT,
        last_name TEXT,
        gender TEXT,
        date_of_birth TEXT NOT NULL,
        address_line_1 TEXT,
        address_line_2 TEXT,
        street TEXT,
        postal_code TEXT,
        city TEXT,
        state TEXT NOT NULL,
        country TEXT,
        phone_number TEXT,
        email TEXT,
        individual_yearly_income REAL NOT NULL CHECK (individual_yearly_income >= 0),
        family_member_count INTEGER NOT NULL CHECK (family_member_count >= 1),
        resident_status TEXT,
        resident_type TEXT,
        education TEXT,
        employment_status TEXT,
        type_of_employment TEXT,
        marital_status TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS campaign_sales (
        campaign_sales_id TEXT NOT NULL PRIMARY KEY,
        customer_id TEXT NOT NULL,
        campaign_id TEXT NOT NULL,
        product_id TEXT NOT NULL,
        order_id TEXT,
        campaign_name TEXT,
        campaign_type TEXT,
        campaign_channel TEXT,
        campaign_start_date TEXT NOT NULL,
        campaign_end_date TEXT NOT NULL,
        campaign_category TEXT,
        offer_type TEXT,
        offer_value REAL,
        creative_id TEXT,
        target_segment TEXT,
        product_name TEXT,
        product_category TEXT,
        product_subcategory TEXT,
        product_price REAL,
        product_cost REAL,
        product_tier TEXT,
        product_launch_date TEXT,
        contact_date TEXT NOT NULL,
        contacted_flag INTEGER NOT NULL CHECK (contacted_flag IN (0, 1)),
        delivery_status TEXT,
        engagement_flag INTEGER NOT NULL CHECK (engagement_flag IN (0, 1)),
        engagement_type TEXT,
        response_flag INTEGER NOT NULL CHECK (response_flag IN (0, 1)),
        purchase_flag INTEGER NOT NULL CHECK (purchase_flag IN (0, 1)),
        purchase_date TEXT,
        quantity INTEGER CHECK (quantity IS NULL OR quantity >= 0),
        gross_sales_amount REAL,
        discount_amount REAL,
        net_sales_amount REAL,
        gross_margin_amount REAL,
        days_to_purchase INTEGER CHECK (days_to_purchase IS NULL OR days_to_purchase >= 0),
        campaign_attributed_sale_flag INTEGER NOT NULL
            CHECK (campaign_attributed_sale_flag IN (0, 1)),
        pu_label INTEGER NOT NULL CHECK (pu_label IN (0, 1)),
        FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
            ON UPDATE CASCADE ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS demographics (
        person_id TEXT NOT NULL PRIMARY KEY,
        first_name TEXT,
        last_name TEXT,
        gender TEXT,
        age INTEGER NOT NULL CHECK (age BETWEEN 0 AND 120),
        address_line_1 TEXT,
        address_line_2 TEXT,
        street TEXT,
        postal_code TEXT,
        city TEXT,
        state TEXT NOT NULL,
        country TEXT,
        phone_number TEXT,
        email TEXT,
        individual_yearly_income REAL NOT NULL CHECK (individual_yearly_income >= 0),
        marital_status TEXT,
        education TEXT,
        employment_status TEXT,
        resident_status TEXT,
        resident_type TEXT,
        family_member_count INTEGER NOT NULL CHECK (family_member_count >= 1),
        number_of_children_in_family INTEGER NOT NULL
            CHECK (number_of_children_in_family >= 0),
        number_of_adults_in_family INTEGER NOT NULL
            CHECK (number_of_adults_in_family >= 0),
        ethnicity TEXT,
        type_of_employment TEXT,
        occupation_industry TEXT,
        family_yearly_income REAL NOT NULL CHECK (family_yearly_income >= 0),
        religion TEXT
    )
    """,
)

PHASE_ONE_REQUIRED_INDEX_STATEMENTS = {
    "idx_customers_state": "CREATE INDEX IF NOT EXISTS idx_customers_state ON customers (state)",
    "idx_customers_date_of_birth": (
        "CREATE INDEX IF NOT EXISTS idx_customers_date_of_birth ON customers (date_of_birth)"
    ),
    "idx_customers_individual_yearly_income": (
        "CREATE INDEX IF NOT EXISTS idx_customers_individual_yearly_income "
        "ON customers (individual_yearly_income)"
    ),
    "idx_campaign_sales_customer_id": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_sales_customer_id ON campaign_sales (customer_id)"
    ),
    "idx_campaign_sales_campaign_id": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_sales_campaign_id ON campaign_sales (campaign_id)"
    ),
    "idx_campaign_sales_product_id": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_sales_product_id ON campaign_sales (product_id)"
    ),
    "idx_campaign_sales_contact_date": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_sales_contact_date ON campaign_sales (contact_date)"
    ),
    "idx_campaign_sales_purchase_flag": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_sales_purchase_flag ON campaign_sales (purchase_flag)"
    ),
    "idx_campaign_sales_pu_label": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_sales_pu_label ON campaign_sales (pu_label)"
    ),
    "idx_campaign_sales_campaign_product_pu": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_sales_campaign_product_pu "
        "ON campaign_sales (campaign_id, product_id, pu_label)"
    ),
    "idx_demographics_state": (
        "CREATE INDEX IF NOT EXISTS idx_demographics_state ON demographics (state)"
    ),
    "idx_demographics_age": "CREATE INDEX IF NOT EXISTS idx_demographics_age ON demographics (age)",
    "idx_demographics_individual_yearly_income": (
        "CREATE INDEX IF NOT EXISTS idx_demographics_individual_yearly_income "
        "ON demographics (individual_yearly_income)"
    ),
    "idx_demographics_education": (
        "CREATE INDEX IF NOT EXISTS idx_demographics_education ON demographics (education)"
    ),
    "idx_demographics_employment_status": (
        "CREATE INDEX IF NOT EXISTS idx_demographics_employment_status "
        "ON demographics (employment_status)"
    ),
    "idx_demographics_resident_status": (
        "CREATE INDEX IF NOT EXISTS idx_demographics_resident_status "
        "ON demographics (resident_status)"
    ),
    "idx_demographics_type_of_employment": (
        "CREATE INDEX IF NOT EXISTS idx_demographics_type_of_employment "
        "ON demographics (type_of_employment)"
    ),
}

PHASE_TWO_REQUIRED_INDEX_STATEMENTS = {
    "idx_historical_analysis_runs_newest": (
        "CREATE INDEX IF NOT EXISTS idx_historical_analysis_runs_newest "
        "ON historical_analysis_runs (created_at DESC, analysis_run_id DESC)"
    ),
    "idx_campaign_sales_campaign_channel": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_sales_campaign_channel "
        "ON campaign_sales (campaign_channel)"
    ),
    "idx_campaign_sales_product_category": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_sales_product_category "
        "ON campaign_sales (product_category)"
    ),
    "idx_campaign_sales_campaign_type": (
        "CREATE INDEX IF NOT EXISTS idx_campaign_sales_campaign_type "
        "ON campaign_sales (campaign_type)"
    ),
}

REQUIRED_INDEX_STATEMENTS = {
    **PHASE_ONE_REQUIRED_INDEX_STATEMENTS,
    **PHASE_TWO_REQUIRED_INDEX_STATEMENTS,
}


class UnsupportedSchemaVersionError(RuntimeError):
    """Raised when a database version cannot be safely handled by this application."""


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        is not None
    )


def _user_table_names(connection: sqlite3.Connection) -> tuple[str, ...]:
    return tuple(
        row["name"]
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    )


def _stored_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT value FROM app_metadata WHERE key = ?",
        ("schema_version",),
    ).fetchone()
    if row is None:
        raise UnsupportedSchemaVersionError(
            "Database metadata does not contain a schema_version value."
        )
    try:
        return int(row["value"])
    except (TypeError, ValueError) as exc:
        raise UnsupportedSchemaVersionError(
            f"Database schema_version is invalid: {row['value']!r}."
        ) from exc


def _initialize_phase_one_schema(path: Path, timestamp: str) -> None:
    """Create the accepted Phase 1 base only when the database is empty."""
    with get_connection(path) as connection:
        if _table_exists(connection, "app_metadata"):
            return

    with get_connection(path, write=True) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if _table_exists(connection, "app_metadata"):
            return

        existing_tables = _user_table_names(connection)
        if existing_tables:
            raise UnsupportedSchemaVersionError(
                "Database has tables but no app_metadata schema version; "
                "automatic migration was not attempted."
            )

        for statement in CREATE_TABLE_STATEMENTS:
            connection.execute(statement)

        for key, value in (
            ("schema_version", str(PHASE_ONE_SCHEMA_VERSION)),
            ("application_version", APP_VERSION),
            ("database_initialized_at", timestamp),
        ):
            connection.execute(
                """
                INSERT INTO app_metadata (key, value, updated_at)
                VALUES (?, ?, ?)
                """,
                (key, value, timestamp),
            )


def _migrate_to_version_2(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE historical_analysis_runs (
            analysis_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL
                CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
            conversion_definition TEXT NOT NULL
                CHECK (conversion_definition IN (
                    'ATTRIBUTED_PURCHASE', 'ANY_PURCHASE', 'RESPONSE'
                )),
            filters_json TEXT NOT NULL,
            results_json TEXT,
            observation_count INTEGER NOT NULL DEFAULT 0
                CHECK (observation_count >= 0),
            selected_customer_count INTEGER NOT NULL DEFAULT 0
                CHECK (selected_customer_count >= 0),
            positive_customer_count INTEGER NOT NULL DEFAULT 0
                CHECK (positive_customer_count >= 0),
            unlabeled_customer_count INTEGER NOT NULL DEFAULT 0
                CHECK (unlabeled_customer_count >= 0),
            positive_customer_rate REAL,
            error_message TEXT,
            CHECK (
                positive_customer_rate IS NULL
                OR positive_customer_rate BETWEEN 0 AND 1
            )
        )
        """
    )
    for statement in PHASE_TWO_REQUIRED_INDEX_STATEMENTS.values():
        connection.execute(statement)


MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    2: _migrate_to_version_2,
}


def initialize_database(database_path: str | Path | None = None) -> Path:
    """Create the Phase 1 base and apply each missing schema migration in order."""
    path = Path(database_path) if database_path is not None else DATABASE_PATH
    timestamp = _utc_timestamp()

    _initialize_phase_one_schema(path, timestamp)

    with get_connection(path) as connection:
        stored_version = _stored_schema_version(connection)

    if stored_version > CURRENT_SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            "Database schema version "
            f"{stored_version} is newer than supported version {CURRENT_SCHEMA_VERSION}."
        )
    if stored_version < PHASE_ONE_SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            f"Database schema version {stored_version} is older than the supported base "
            f"version {PHASE_ONE_SCHEMA_VERSION}."
        )

    for target_version in range(stored_version + 1, CURRENT_SCHEMA_VERSION + 1):
        migration = MIGRATIONS.get(target_version)
        if migration is None:
            raise UnsupportedSchemaVersionError(
                f"No migration is registered for schema version {target_version}."
            )

        with get_connection(path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current_version = _stored_schema_version(connection)
            if current_version >= target_version:
                continue
            if current_version != target_version - 1:
                raise UnsupportedSchemaVersionError(
                    "Database schema changed during migration; expected version "
                    f"{target_version - 1}, found {current_version}."
                )
            migration(connection)
            connection.execute(
                """
                UPDATE app_metadata
                SET value = ?, updated_at = ?
                WHERE key = 'schema_version'
                """,
                (str(target_version), timestamp),
            )

    with get_connection(path) as connection:
        application_version_row = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'application_version'"
        ).fetchone()

    if application_version_row is None or application_version_row["value"] != APP_VERSION:
        with get_connection(path, write=True) as connection:
            connection.execute(
                """
                INSERT INTO app_metadata (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                ("application_version", APP_VERSION, timestamp),
            )

    logger.info("SQLite schema initialized or verified | path=%s version=%s", path, SCHEMA_VERSION)
    return path


def initialize_required_indexes(database_path: str | Path | None = None) -> dict[str, float]:
    """Create all required query indexes idempotently and return per-index timings."""
    path = initialize_database(database_path)
    timings: dict[str, float] = {}

    with get_connection(path, write=True) as connection:
        for index_name, statement in REQUIRED_INDEX_STATEMENTS.items():
            started = time.perf_counter()
            connection.execute(statement)
            connection.commit()
            elapsed = time.perf_counter() - started
            timings[index_name] = elapsed
            logger.info("SQLite index verified | index=%s seconds=%.3f", index_name, elapsed)

    return timings


def verify_required_indexes(database_path: str | Path | None = None) -> dict[str, bool]:
    """Report whether each required index exists in the SQLite catalog."""
    path = Path(database_path) if database_path is not None else DATABASE_PATH
    with get_connection(path) as connection:
        existing = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
    return {name: name in existing for name in REQUIRED_INDEX_STATEMENTS}


def _quote_identifier(identifier: str) -> str:
    """Quote an identifier obtained from SQLite's own schema catalog."""
    return '"' + identifier.replace('"', '""') + '"'


def inspect_database(database_path: str | Path | None = None) -> dict[str, Any]:
    """Return tables, columns, indexes, and row counts for development inspection."""
    path = Path(database_path) if database_path is not None else DATABASE_PATH
    report: dict[str, Any] = {"database_path": str(path), "tables": []}

    with get_connection(path) as connection:
        table_names = [
            row["name"]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        ]

        for table_name in table_names:
            quoted_name = _quote_identifier(table_name)
            columns = [
                {
                    "name": row["name"],
                    "type": row["type"],
                    "not_null": bool(row["notnull"]),
                    "primary_key_position": row["pk"],
                }
                for row in connection.execute(f"PRAGMA table_info({quoted_name})").fetchall()
            ]
            indexes = [
                {
                    "name": row["name"],
                    "unique": bool(row["unique"]),
                    "origin": row["origin"],
                }
                for row in connection.execute(f"PRAGMA index_list({quoted_name})").fetchall()
            ]
            row_count = connection.execute(
                f"SELECT COUNT(*) AS row_count FROM {quoted_name}"
            ).fetchone()["row_count"]
            report["tables"].append(
                {
                    "name": table_name,
                    "row_count": row_count,
                    "columns": columns,
                    "indexes": indexes,
                }
            )

    return report


def format_inspection_report(report: dict[str, Any]) -> str:
    """Format an inspection result for the initialization CLI."""
    lines = [f"Database: {report['database_path']}"]
    for table in report["tables"]:
        lines.append(f"\nTable: {table['name']} | rows: {table['row_count']}")
        lines.append("  Columns:")
        for column in table["columns"]:
            markers = []
            if column["not_null"]:
                markers.append("NOT NULL")
            if column["primary_key_position"]:
                markers.append("PRIMARY KEY")
            suffix = f" [{' | '.join(markers)}]" if markers else ""
            lines.append(f"    - {column['name']}: {column['type']}{suffix}")
        lines.append("  Indexes:")
        if table["indexes"]:
            for index in table["indexes"]:
                lines.append(
                    f"    - {index['name']} | unique={index['unique']} | origin={index['origin']}"
                )
        else:
            lines.append("    - none")
    return "\n".join(lines)
