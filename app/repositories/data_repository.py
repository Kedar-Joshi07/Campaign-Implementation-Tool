"""SQLite queries for Phase 1 data status and reference APIs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.database.connection import get_connection
from app.database.schema import EXPECTED_TABLES


class DataRepository:
    """Execute bounded, summary-only queries against one SQLite database."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def fetch_summary(self) -> dict[str, Any]:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM customers) AS customer_count,
                    (SELECT COUNT(*) FROM campaign_sales) AS campaign_sales_count,
                    (SELECT COUNT(*) FROM demographics) AS demographic_count,
                    (SELECT COUNT(DISTINCT campaign_id) FROM campaign_sales)
                        AS distinct_campaigns,
                    (SELECT COUNT(DISTINCT product_id) FROM campaign_sales)
                        AS distinct_products,
                    (SELECT MIN(contact_date) FROM campaign_sales)
                        AS campaign_contact_date_min,
                    (SELECT MAX(contact_date) FROM campaign_sales)
                        AS campaign_contact_date_max,
                    (SELECT COUNT(*) FROM campaign_sales WHERE pu_label = 1)
                        AS known_positive_count,
                    (SELECT COUNT(*) FROM campaign_sales
                        WHERE campaign_attributed_sale_flag = 1)
                        AS attributed_purchase_count,
                    (SELECT value FROM app_metadata WHERE key = 'schema_version')
                        AS schema_version
                """
            ).fetchone()
        return dict(row)

    def fetch_latest_imports(self) -> dict[str, dict[str, Any]]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    import_id,
                    dataset_name,
                    source_path,
                    started_at,
                    completed_at,
                    status,
                    rows_read,
                    rows_inserted,
                    rows_rejected,
                    error_message,
                    source_checksum
                FROM data_import_runs AS run
                WHERE import_id = (
                    SELECT MAX(latest.import_id)
                    FROM data_import_runs AS latest
                    WHERE latest.dataset_name = run.dataset_name
                )
                ORDER BY dataset_name
                """
            ).fetchall()
        return {row["dataset_name"]: dict(row) for row in rows}

    def fetch_import_runs(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    import_id,
                    dataset_name,
                    source_path,
                    started_at,
                    completed_at,
                    status,
                    rows_read,
                    rows_inserted,
                    rows_rejected,
                    error_message,
                    source_checksum
                FROM data_import_runs
                ORDER BY import_id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_states(self) -> list[dict[str, Any]]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT state AS state_name, COUNT(*) AS person_count
                FROM demographics
                GROUP BY state
                ORDER BY person_count DESC, state_name
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_campaigns(self, *, limit: int, search: str | None) -> list[dict[str, Any]]:
        parameters: list[Any] = []
        where_clause = ""
        if search:
            where_clause = "WHERE campaign_id LIKE ? OR campaign_name LIKE ?"
            pattern = f"%{search}%"
            parameters.extend((pattern, pattern))
        parameters.append(limit)

        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    campaign_id,
                    MIN(campaign_name) AS campaign_name,
                    MIN(campaign_type) AS campaign_type,
                    MIN(campaign_channel) AS campaign_channel,
                    MIN(campaign_start_date) AS campaign_start_date,
                    MAX(campaign_end_date) AS campaign_end_date,
                    COUNT(*) AS observation_count,
                    SUM(CASE WHEN pu_label = 1 THEN 1 ELSE 0 END) AS positive_count
                FROM campaign_sales
                {where_clause}
                GROUP BY campaign_id
                ORDER BY observation_count DESC, campaign_id
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_products(self, *, limit: int, search: str | None) -> list[dict[str, Any]]:
        parameters: list[Any] = []
        where_clause = ""
        if search:
            where_clause = "WHERE product_id LIKE ? OR product_name LIKE ?"
            pattern = f"%{search}%"
            parameters.extend((pattern, pattern))
        parameters.append(limit)

        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    product_id,
                    MIN(product_name) AS product_name,
                    MIN(product_category) AS product_category,
                    MIN(product_subcategory) AS product_subcategory,
                    MIN(product_tier) AS product_tier,
                    COUNT(*) AS observation_count,
                    SUM(CASE WHEN purchase_flag = 1 THEN 1 ELSE 0 END) AS purchase_count
                FROM campaign_sales
                {where_clause}
                GROUP BY product_id
                ORDER BY observation_count DESC, product_id
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def check_health(self) -> dict[str, Any]:
        """Check connectivity and required table presence without scanning table rows."""
        with get_connection(self.database_path) as connection:
            connection.execute("SELECT 1").fetchone()
            present_tables = {
                row["name"]
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                    """
                ).fetchall()
            }

        expected_tables = set(EXPECTED_TABLES)
        missing_tables = sorted(expected_tables - present_tables)
        if not present_tables:
            schema_status = "missing"
        elif missing_tables:
            schema_status = "incomplete"
        else:
            schema_status = "ready"
        return {
            "database_status": "connected",
            "schema_status": schema_status,
            "missing_tables": missing_tables,
        }
