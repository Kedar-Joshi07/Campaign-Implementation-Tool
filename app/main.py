"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import APP_ENV, APP_NAME, APP_VERSION
from app.logging_config import configure_logging
from app.routers.health import router as health_router


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
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/", include_in_schema=False, response_class=FileResponse)
async def frontend_index() -> FileResponse:
    """Serve the static application shell."""
    return FileResponse(FRONTEND_DIR / "index.html", media_type="text/html")

