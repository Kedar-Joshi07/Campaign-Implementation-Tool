"""FastAPI application entry point."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import APP_ENV, APP_NAME, APP_VERSION, DATABASE_PATH
from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.jobs.executor import shutdown_model_training_executor
from app.jobs.phase11_search_coordinator import Phase11SearchCoordinator
from app.logging_config import configure_logging
from app.runtime_health import RuntimeHealthState
from app.routers.data import router as data_router
from app.routers.campaigns import router as campaign_router
from app.routers.campaign_targeting import router as campaign_targeting_router
from app.routers.health import router as health_router
from app.routers.historical import router as historical_router
from app.routers.models import router as model_router
from app.routers.reference import router as reference_router
from app.routers.potential_customer_search import router as potential_customer_search_router
from app.routers.business import router as business_router
from app.services.campaign_service import reconcile_stale_campaign_export_events
from app.services.model_job_service import reconcile_stale_model_training_jobs
from app.services.phase10_orchestration_service import (
    reconcile_phase10_orchestrations,
)
from app.services.phase11_export_service import reconcile_stale_result_export_events
from app.services.phase11_result_snapshot_service import ResultSnapshotMaterializer
from app.services.potential_customer_search_submission_service import (
    configure_phase11_search_executor,
    reset_phase11_search_executor,
)
from app.services.phase11_feedback_service import configure_feedback_recalibration_executor
from app.jobs.feedback_retraining_worker import FeedbackRecalibrationWorker
from app.services.source_currentness_service import reconcile_source_currentness


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
    database_override = app.dependency_overrides.get(get_database_path)
    runtime_database_path = Path(
        database_override() if database_override is not None else DATABASE_PATH
    )
    phase11_coordinator: Phase11SearchCoordinator | None = None
    feedback_worker: FeedbackRecalibrationWorker | None = None
    runtime_health: RuntimeHealthState = app.state.runtime_health
    runtime_health.reset()
    try:
        initialized_path = initialize_database(runtime_database_path)
        currentness = reconcile_source_currentness(initialized_path)
        logger.info(
            "Source currentness reconciliation completed | outcome=%s",
            currentness,
        )
        phase11_materializer = ResultSnapshotMaterializer(PROJECT_ROOT)
        phase11_coordinator = Phase11SearchCoordinator(
            initialized_path,
            materializer=phase11_materializer,
            project_root=PROJECT_ROOT,
        )
        configure_phase11_search_executor(phase11_coordinator.submit)
        feedback_worker = FeedbackRecalibrationWorker()
        configure_feedback_recalibration_executor(feedback_worker.submit)
        resumed_feedback = feedback_worker.resume_durable_decisions(initialized_path)
        runtime_health.mark_ready()
        logger.info(
            "Phase 11 runtime composition completed | workers=%s poll_seconds=%s resumed_feedback=%s",
            phase11_coordinator.max_workers,
            phase11_coordinator.poll_interval_seconds,
            resumed_feedback,
        )
    except Exception:
        runtime_health.mark_composition_failure()
        reset_phase11_search_executor()
        if phase11_coordinator is not None:
            phase11_coordinator.shutdown(wait=True)
            phase11_coordinator = None
        logger.exception(
            "Phase 11 runtime composition failed; workflow is unavailable"
        )
    try:
        stale_failed = reconcile_stale_model_training_jobs(runtime_database_path)
        logger.info(
            "Compute startup reconciliation completed | failed_stale_jobs=%s",
            stale_failed,
        )
    except Exception:
        logger.exception("Compute startup reconciliation failed")
    try:
        resumed_phase10 = reconcile_phase10_orchestrations(
            runtime_database_path,
            project_root=PROJECT_ROOT,
        )
        logger.info(
            "Phase 10 startup reconciliation completed | resumed_orchestrations=%s",
            resumed_phase10,
        )
    except Exception:
        logger.exception("Phase 10 startup reconciliation failed")
    try:
        resumed_phase11 = (
            phase11_coordinator.resume_durable_searches()
            if phase11_coordinator is not None
            else 0
        )
        logger.info(
            "Phase 11 startup reconciliation completed | scheduled_searches=%s",
            resumed_phase11,
        )
    except Exception:
        logger.exception("Phase 11 startup reconciliation failed")
    try:
        stale_campaign_exports = reconcile_stale_campaign_export_events(
            runtime_database_path
        )
        logger.info(
            "Campaign export startup reconciliation completed | reconciled_stale_exports=%s",
            stale_campaign_exports,
        )
    except Exception:
        logger.exception("Campaign export startup reconciliation failed")
    try:
        stale_result_exports = reconcile_stale_result_export_events(
            runtime_database_path
        )
        logger.info(
            "Result export startup reconciliation completed | reconciled_stale_exports=%s",
            stale_result_exports,
        )
    except Exception:
        logger.exception("Result export startup reconciliation failed")
    try:
        yield
    finally:
        reset_phase11_search_executor()
        configure_feedback_recalibration_executor(None)
        if phase11_coordinator is not None:
            phase11_coordinator.shutdown(wait=True)
        if feedback_worker is not None:
            feedback_worker.shutdown(wait=False)
        shutdown_model_training_executor(wait=False)
        runtime_health.reset()
        logger.info("Application stopping | name=%s", APP_NAME)


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=(
        "Campaign Implementation Intelligence POC with Phase 1-11 data, including "
        "Phase 2 aggregate historical campaign analysis, governed PU modeling, full "
        "prospect scoring, audience, Campaign, "
        "and business-search capabilities. Phase 10 automatically resolves exact "
        "intelligence compatibility and reuses or builds only the required analytical "
        "layers. The automatically initialized Phase 11 coordinator provides durable "
        "search execution, smart result reuse, immutable membership snapshots, and "
        "governed omnichannel downloads. The POC stops at governed export and does not "
        "integrate outbound activation or send platforms."
    ),
    lifespan=lifespan,
)
app.state.runtime_health = RuntimeHealthState()
app.include_router(health_router)
app.include_router(data_router)
app.include_router(reference_router)
app.include_router(historical_router)
app.include_router(model_router)
app.include_router(campaign_router)
app.include_router(campaign_targeting_router)
app.include_router(potential_customer_search_router)
app.include_router(business_router)
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
