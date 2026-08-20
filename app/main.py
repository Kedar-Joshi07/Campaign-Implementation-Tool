"""FastAPI application entry point."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import APP_ENV, APP_NAME, APP_VERSION
from app.logging_config import configure_logging
from app.routers.data import router as data_router
from app.routers.health import router as health_router
from app.routers.reference import router as reference_router


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(
        "Application starting | name=%s version=%s environment=%s",
        APP_NAME,
        APP_VERSION,
        APP_ENV,
    )
    yield
    logger.info("Application stopping | name=%s", APP_NAME)


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Phase 1 foundation for the Campaign Implementation Tool POC.",
    lifespan=lifespan,
)
app.include_router(health_router)
app.include_router(data_router)
app.include_router(reference_router)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.exception_handler(sqlite3.Error)
async def sqlite_exception_handler(request: Request, exc: sqlite3.Error) -> JSONResponse:
    """Return a stable browser response while retaining database details in logs."""
    logger.exception("SQLite request failed | endpoint=%s", request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=503,
        content={
            "detail": "The database request could not be completed. Verify database initialization and availability."
        },
    )


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log unexpected failures without exposing implementation details to clients."""
    logger.exception("Unexpected API failure | endpoint=%s", request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected application error occurred."},
    )


@app.get("/", include_in_schema=False, response_class=FileResponse)
async def frontend_index() -> FileResponse:
    """Serve the static application shell."""
    return FileResponse(FRONTEND_DIR / "index.html", media_type="text/html")
