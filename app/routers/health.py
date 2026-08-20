"""Application health and version endpoints."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.config import APP_NAME, APP_VERSION
from app.dependencies import get_database_path
from app.repositories.data_repository import DataRepository


router = APIRouter(prefix="/api", tags=["system"])
logger = logging.getLogger(__name__)
DatabasePath = Annotated[Path, Depends(get_database_path)]


class HealthResponse(BaseModel):
    status: str
    application_status: str
    database_status: str
    schema_status: str
    missing_tables: list[str]
    application: str
    version: str


class VersionResponse(BaseModel):
    application: str
    version: str


@router.get("/health", response_model=HealthResponse)
def health(response: Response, database_path: DatabasePath) -> HealthResponse:
    """Return lightweight application health information."""
    try:
        database_health = DataRepository(database_path).check_health()
    except sqlite3.Error:
        logger.exception("Database health check failed")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="degraded",
            application_status="ok",
            database_status="unavailable",
            schema_status="unknown",
            missing_tables=[],
            application=APP_NAME,
            version=APP_VERSION,
        )

    application_status = "ok"
    overall_status = "ok" if database_health["schema_status"] == "ready" else "degraded"
    if overall_status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status=overall_status,
        application_status=application_status,
        database_status=database_health["database_status"],
        schema_status=database_health["schema_status"],
        missing_tables=database_health["missing_tables"],
        application=APP_NAME,
        version=APP_VERSION,
    )


@router.get("/version", response_model=VersionResponse)
async def version() -> VersionResponse:
    """Return the application name and version."""
    return VersionResponse(application=APP_NAME, version=APP_VERSION)
