"""Pydantic response models for data APIs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


ReconciliationStatus = Literal["NOT_LOADED", "OK", "WARNING", "ERROR"]


class DatasetStatusResponse(BaseModel):
    dataset_name: str
    table_name: str
    actual_rows: int
    expected_rows: int | None
    exact_match_required: bool
    reconciliation_status: ReconciliationStatus
    last_import_status: str | None
    last_import_started_at: str | None
    last_import_completed_at: str | None
    source_path: str | None
    rows_inserted: int | None
    rows_rejected: int | None


class DataSummaryResponse(BaseModel):
    customer_count: int
    campaign_sales_count: int
    demographic_count: int
    distinct_campaigns: int
    distinct_products: int
    campaign_contact_date_min: str | None
    campaign_contact_date_max: str | None
    known_positive_count: int
    attributed_purchase_count: int
    database_path: str
    schema_version: str | None


class ImportRunResponse(BaseModel):
    import_id: int
    dataset_name: str
    source_path: str
    started_at: str
    completed_at: str | None
    status: str
    rows_read: int
    rows_inserted: int
    rows_rejected: int
    error_message: str | None
    source_checksum: str | None
