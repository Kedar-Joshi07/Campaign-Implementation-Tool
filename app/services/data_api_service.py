"""Business response composition for Phase 1 summary and reference APIs."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath
from typing import Any

from app.repositories.data_repository import DataRepository
from app.services.data_reconciliation_service import run_reconciliation


DATASET_TABLES = {
    "customers": "customers",
    "campaign_sales": "campaign_sales",
    "demographics": "demographics",
}

STATE_CODES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI",
    "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
    "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME",
    "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE",
    "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
    "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH",
    "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}


def _display_source_path(source_path: str | None) -> str | None:
    if not source_path:
        return None
    display_names = []
    for raw_path in source_path.split(" | "):
        windows_name = PureWindowsPath(raw_path).name
        display_names.append(Path(windows_name).name)
    return " | ".join(display_names)


def _public_import_error(error_message: str | None) -> str | None:
    """Map detailed internal import failures to a stable display-safe message."""
    if not error_message:
        return None

    normalized = error_message.lower()
    if "schema mismatch" in normalized:
        return "Source schema is invalid."
    if "already contains" in normalized:
        return "Target already contains data."
    if any(
        marker in normalized
        for marker in (
            "unique constraint",
            "foreign key constraint",
            "database rejected",
            "sqlite database",
            "database is locked",
        )
    ):
        return "Database operation failed."
    if any(
        marker in normalized
        for marker in (
            "source file does not exist",
            "source file is empty",
            "unsupported source format",
            "unable to read",
            "input directory does not exist",
        )
    ):
        return "Source file is unavailable."
    if any(
        marker in normalized
        for marker in (
            "csv line",
            "date_of_birth",
            "must equal family_member_count",
            "invalid date",
            "required value",
        )
    ):
        return "Source data validation failed."
    return "Import failed."


def get_data_status(database_path: str | Path) -> list[dict[str, Any]]:
    repository = DataRepository(database_path)
    reconciliation = run_reconciliation(database_path)
    latest_imports = repository.fetch_latest_imports()
    response = []

    for dataset_name, table_name in DATASET_TABLES.items():
        dataset = reconciliation["datasets"][dataset_name]
        latest = latest_imports.get(dataset_name)
        response.append(
            {
                "dataset_name": dataset_name,
                "table_name": table_name,
                "actual_rows": dataset["actual_count"],
                "expected_rows": dataset["expected_count"],
                "exact_match_required": dataset["exact_match_required"],
                "count_tolerance_percent": dataset["count_tolerance_percent"],
                "acceptable_min_rows": dataset["acceptable_min_rows"],
                "acceptable_max_rows": dataset["acceptable_max_rows"],
                "acceptable_count": dataset["acceptable_count"],
                "reconciliation_status": dataset["status"],
                "last_import_status": latest["status"] if latest else None,
                "last_import_started_at": latest["started_at"] if latest else None,
                "last_import_completed_at": latest["completed_at"] if latest else None,
                "source_path": _display_source_path(latest["source_path"]) if latest else None,
                "rows_inserted": latest["rows_inserted"] if latest else None,
                "rows_rejected": latest["rows_rejected"] if latest else None,
            }
        )
    return response


def get_data_summary(database_path: str | Path) -> dict[str, Any]:
    result = DataRepository(database_path).fetch_summary()
    result["database_path"] = Path(database_path).name
    return result


def get_recent_imports(
    database_path: str | Path,
    *,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    rows = DataRepository(database_path).fetch_import_runs(limit=limit, offset=offset)
    for row in rows:
        row["source_path"] = _display_source_path(row["source_path"])
        row["error_message"] = _public_import_error(row["error_message"])
    return rows


def get_state_references(database_path: str | Path) -> list[dict[str, Any]]:
    rows = DataRepository(database_path).fetch_states()
    for row in rows:
        row["state_code"] = STATE_CODES.get(row["state_name"])
    return rows


def get_campaign_references(
    database_path: str | Path,
    *,
    limit: int,
    search: str | None,
) -> list[dict[str, Any]]:
    return DataRepository(database_path).fetch_campaigns(limit=limit, search=search)


def get_product_references(
    database_path: str | Path,
    *,
    limit: int,
    search: str | None,
) -> list[dict[str, Any]]:
    return DataRepository(database_path).fetch_products(limit=limit, search=search)
