"""Business projections for the Phase 11 Home dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.repositories.business_dashboard_repository import (
    BusinessDashboardRepository,
)
from app.services.phase11_run_lifecycle_service import (
    project_run_issue,
    project_run_progress,
)


_STATUS_MESSAGES = {
    "QUEUED": "Saved and waiting to prepare potential-customer results.",
    "PROCESSING": "Preparing potential-customer results.",
    "COMPLETED": "Potential-customer results are ready.",
    "BLOCKED": "This search is saved but could not be prepared yet.",
    "FAILED": "This search could not be completed.",
}


def get_business_overview(database_path: str | Path) -> dict[str, Any]:
    """Return four counts from import and search-run metadata only."""

    row = BusinessDashboardRepository(database_path).fetch_overview()
    return {
        "potential_customers_available": int(
            row["potential_customers_available"] or 0
        ),
        "search_runs": int(row["search_runs"] or 0),
        "completed_results": int(row["completed_results"] or 0),
        "latest_result_count": (
            int(row["latest_result_count"])
            if row["latest_result_count"] is not None
            else None
        ),
    }


def get_recent_results(
    database_path: str | Path, *, limit: int = 5
) -> list[dict[str, Any]]:
    """Return newest search-run metadata without loading members or lineage."""

    rows = BusinessDashboardRepository(database_path).fetch_recent_results(limit=limit)
    return [
        {
            "search_run_id": int(row["search_run_id"]),
            "campaign_name": str(row["campaign_name"]),
            "created_at": str(row["created_at"]),
            "completed_at": row["completed_at"],
            "status": str(row["status"]),
            "selected_count": (
                int(row["selected_count"])
                if row["selected_count"] is not None
                else None
            ),
            "delivery_profile_label": str(row["delivery_channel"])
            .replace("_", " ")
            .title(),
            "safe_message": _STATUS_MESSAGES[str(row["status"])],
            "progress": project_run_progress(
                row, row if row.get("lifecycle_status") is not None else None
            ),
            "issue": project_run_issue(
                row if row.get("lifecycle_status") is not None else None
            ),
        }
        for row in rows
    ]
