"""Summary-oriented dataset API endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_database_path
from app.schemas.data import DataSummaryResponse, DatasetStatusResponse, ImportRunResponse
from app.services.data_api_service import get_data_status, get_data_summary, get_recent_imports


router = APIRouter(prefix="/api/data", tags=["data"])
DatabasePath = Annotated[Path, Depends(get_database_path)]


@router.get("/status", response_model=list[DatasetStatusResponse])
def data_status(database_path: DatabasePath) -> list[dict]:
    """Return current reconciliation and latest-import status per dataset."""
    return get_data_status(database_path)


@router.get("/summary", response_model=DataSummaryResponse)
def data_summary(database_path: DatabasePath) -> dict:
    """Return application-level aggregate counts and campaign coverage."""
    return get_data_summary(database_path)


@router.get("/imports", response_model=list[ImportRunResponse])
def import_runs(
    database_path: DatabasePath,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict]:
    """Return a bounded page of recent import runs, newest first."""
    return get_recent_imports(database_path, limit=limit, offset=offset)
