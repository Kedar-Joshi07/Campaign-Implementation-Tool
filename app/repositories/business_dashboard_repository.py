"""Bounded metadata queries for the Phase 11 business Home dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.database.connection import get_connection


class BusinessDashboardRepository:
    """Read operational metadata without scanning the demographic population."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def fetch_overview(self) -> dict[str, Any]:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                    COALESCE((
                        SELECT rows_inserted
                        FROM data_import_runs
                        WHERE dataset_name = 'demographics'
                          AND status = 'COMPLETED'
                        ORDER BY import_id DESC
                        LIMIT 1
                    ), 0) AS potential_customers_available,
                    (SELECT COUNT(*) FROM campaign_search_runs) AS search_runs,
                    (SELECT COUNT(*) FROM campaign_search_runs
                     WHERE status = 'COMPLETED') AS completed_results,
                    (SELECT selected_count FROM campaign_search_runs
                     WHERE status = 'COMPLETED'
                     ORDER BY completed_at DESC, search_run_id DESC
                     LIMIT 1) AS latest_result_count
                """
            ).fetchone()
        return dict(row)

    def fetch_recent_results(self, *, limit: int) -> list[dict[str, Any]]:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 10
        ):
            raise ValueError("limit must be between 1 and 10.")
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT search_run_id, campaign_name, created_at, completed_at,
                       status, selected_count, delivery_channel
                FROM campaign_search_runs
                ORDER BY created_at DESC, search_run_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
