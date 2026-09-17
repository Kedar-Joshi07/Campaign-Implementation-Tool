"""Phase 11 business Home dashboard endpoints."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_database_path
from app.schemas.business_dashboard import (
    BusinessOverviewResponse,
    BusinessRecentResult,
)
from app.services.business_dashboard_service import (
    get_business_overview,
    get_recent_results,
)


router = APIRouter(prefix="/api/business", tags=["business dashboard"])
DatabasePath = Annotated[Path, Depends(get_database_path)]


@router.get("/overview", response_model=BusinessOverviewResponse)
def business_overview(database_path: DatabasePath) -> dict:
    return get_business_overview(database_path)


@router.get("/recent-results", response_model=list[BusinessRecentResult])
def business_recent_results(
    database_path: DatabasePath,
    limit: Annotated[int, Query(ge=5, le=10)] = 5,
) -> list[dict]:
    return get_recent_results(database_path, limit=limit)
