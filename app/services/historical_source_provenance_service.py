"""Historical customer/campaign import provenance resolution and validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from string import hexdigits
from typing import Any, Mapping

from app.database.connection import get_connection


class HistoricalSourceProvenanceError(RuntimeError):
    """Raised when historical customer/campaign source provenance is unavailable or invalid."""


@dataclass(frozen=True)
class HistoricalSourceProvenance:
    customer_import_id: int
    customer_source_checksum: str
    campaign_sales_import_id: int
    campaign_sales_source_checksum: str


def _is_valid_sha256(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    return len(normalized) == 64 and all(char in hexdigits for char in normalized)


def _latest_completed_import(connection: Any, dataset_name: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT import_id, source_checksum, rows_inserted
        FROM data_import_runs
        WHERE dataset_name = ? AND status = 'COMPLETED'
        ORDER BY import_id DESC
        LIMIT 1
        """,
        (dataset_name,),
    ).fetchone()
    return dict(row) if row is not None else None


def _table_count(connection: Any, table_name: str) -> int:
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0])


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def resolve_current_historical_source_provenance(
    database_path: str | Path,
) -> HistoricalSourceProvenance:
    with get_connection(database_path) as connection:
        customer_import = _latest_completed_import(connection, "customers")
        campaign_import = _latest_completed_import(connection, "campaign_sales")
        if customer_import is None or campaign_import is None:
            raise HistoricalSourceProvenanceError(
                "Completed customer and campaign_sales import provenance is required."
            )

        customer_checksum = customer_import.get("source_checksum")
        campaign_checksum = campaign_import.get("source_checksum")
        if not _is_valid_sha256(customer_checksum):
            raise HistoricalSourceProvenanceError(
                "Completed customers import checksum is missing or invalid."
            )
        if not _is_valid_sha256(campaign_checksum):
            raise HistoricalSourceProvenanceError(
                "Completed campaign_sales import checksum is missing or invalid."
            )

        customer_live_count = _table_count(connection, "customers")
        campaign_live_count = _table_count(connection, "campaign_sales")
        customer_rows_inserted = _optional_int(customer_import.get("rows_inserted"))
        campaign_rows_inserted = _optional_int(campaign_import.get("rows_inserted"))
        if customer_rows_inserted != customer_live_count:
            raise HistoricalSourceProvenanceError(
                "Completed customers import provenance does not match live customer count."
            )
        if campaign_rows_inserted != campaign_live_count:
            raise HistoricalSourceProvenanceError(
                "Completed campaign_sales import provenance does not match live campaign count."
            )

        return HistoricalSourceProvenance(
            customer_import_id=int(customer_import["import_id"]),
            customer_source_checksum=str(customer_checksum).strip().lower(),
            campaign_sales_import_id=int(campaign_import["import_id"]),
            campaign_sales_source_checksum=str(campaign_checksum).strip().lower(),
        )


def saved_analysis_source_provenance(
    analysis_row: Mapping[str, Any],
) -> HistoricalSourceProvenance | None:
    customer_import_id = analysis_row.get("customer_import_id")
    customer_source_checksum = analysis_row.get("customer_source_checksum")
    campaign_import_id = analysis_row.get("campaign_sales_import_id")
    campaign_source_checksum = analysis_row.get("campaign_sales_source_checksum")

    values = (
        customer_import_id,
        customer_source_checksum,
        campaign_import_id,
        campaign_source_checksum,
    )
    if all(value is None for value in values):
        return None

    if (
        isinstance(customer_import_id, bool)
        or not isinstance(customer_import_id, int)
        or customer_import_id <= 0
        or not _is_valid_sha256(customer_source_checksum)
        or isinstance(campaign_import_id, bool)
        or not isinstance(campaign_import_id, int)
        or campaign_import_id <= 0
        or not _is_valid_sha256(campaign_source_checksum)
    ):
        raise HistoricalSourceProvenanceError(
            "Historical analysis source provenance is incomplete or invalid."
        )

    return HistoricalSourceProvenance(
        customer_import_id=customer_import_id,
        customer_source_checksum=str(customer_source_checksum).strip().lower(),
        campaign_sales_import_id=campaign_import_id,
        campaign_sales_source_checksum=str(campaign_source_checksum).strip().lower(),
    )


def is_saved_analysis_provenance_current(
    database_path: str | Path,
    analysis_row: Mapping[str, Any],
) -> tuple[bool, str | None]:
    saved = saved_analysis_source_provenance(analysis_row)
    if saved is None:
        return False, "Historical analysis source provenance is unavailable."
    current = resolve_current_historical_source_provenance(database_path)

    if saved.customer_import_id != current.customer_import_id:
        return False, "Historical customer import provenance is stale."
    if saved.customer_source_checksum != current.customer_source_checksum:
        return False, "Historical customer source checksum is stale."
    if saved.campaign_sales_import_id != current.campaign_sales_import_id:
        return False, "Historical campaign_sales import provenance is stale."
    if saved.campaign_sales_source_checksum != current.campaign_sales_source_checksum:
        return False, "Historical campaign_sales source checksum is stale."

    return True, None


__all__ = (
    "HistoricalSourceProvenance",
    "HistoricalSourceProvenanceError",
    "is_saved_analysis_provenance_current",
    "resolve_current_historical_source_provenance",
    "saved_analysis_source_provenance",
)
