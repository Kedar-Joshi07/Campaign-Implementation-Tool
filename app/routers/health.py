"""Application health and version endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import APP_NAME, APP_VERSION


router = APIRouter(prefix="/api", tags=["system"])


class HealthResponse(BaseModel):
    status: str
    application: str
    version: str


class VersionResponse(BaseModel):
    application: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return lightweight application health information."""
    return HealthResponse(status="ok", application=APP_NAME, version=APP_VERSION)


@router.get("/version", response_model=VersionResponse)
async def version() -> VersionResponse:
    """Return the application name and version."""
    return VersionResponse(application=APP_NAME, version=APP_VERSION)

