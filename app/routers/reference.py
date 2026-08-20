"""Bounded aggregate reference endpoints; no person-level data is exposed."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_database_path
from app.schemas.reference import (
    CampaignReferenceResponse,
    ProductReferenceResponse,
    StateReferenceResponse,
)
from app.services.data_api_service import (
    get_campaign_references,
    get_product_references,
    get_state_references,
)


router = APIRouter(prefix="/api/reference", tags=["reference"])
DatabasePath = Annotated[Path, Depends(get_database_path)]


@router.get("/states", response_model=list[StateReferenceResponse])
def states(database_path: DatabasePath) -> list[dict]:
    """Return aggregate demographic counts by state."""
    return get_state_references(database_path)


@router.get("/campaigns", response_model=list[CampaignReferenceResponse])
def campaigns(
    database_path: DatabasePath,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    search: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
) -> list[dict]:
    """Return bounded campaign-level reference summaries."""
    return get_campaign_references(database_path, limit=limit, search=search)


@router.get("/products", response_model=list[ProductReferenceResponse])
def products(
    database_path: DatabasePath,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    search: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
) -> list[dict]:
    """Return bounded product-level reference summaries."""
    return get_product_references(database_path, limit=limit, search=search)
