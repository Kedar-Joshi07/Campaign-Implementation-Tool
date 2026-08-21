"""Bounded API endpoints for Phase 2 historical campaign analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Path as PathParameter, Query, status

from app.dependencies import get_database_path
from app.schemas.historical import (
    HistoricalAnalysisFilters,
    HistoricalAnalysisListItemResponse,
    HistoricalAnalysisRunResponse,
    HistoricalOptionsResponse,
    HistoricalOverviewResponse,
)
from app.services.historical_analysis_service import (
    HistoricalAnalysisExecutionError,
    HistoricalAnalysisNotFoundError,
    HistoricalAnalysisValidationError,
    HistoricalDataIntegrityError,
    HistoricalDataNotReadyError,
    HistoricalSavedRunError,
    NoMatchingObservationsError,
    create_historical_analysis,
    get_historical_analysis_run,
    list_historical_analysis_runs,
)
from app.services.historical_service import (
    get_historical_options,
    get_historical_overview,
)


router = APIRouter(prefix="/api/historical", tags=["historical analysis"])
DatabasePath = Annotated[Path, Depends(get_database_path)]


def _raise_public_domain_error(exc: Exception) -> NoReturn:
    """Translate known service failures to one sanitized FastAPI error shape."""
    if isinstance(exc, HistoricalAnalysisNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, HistoricalAnalysisValidationError):
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    elif isinstance(
        exc,
        (NoMatchingObservationsError, HistoricalDataNotReadyError, HistoricalDataIntegrityError),
    ):
        status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(exc, (HistoricalAnalysisExecutionError, HistoricalSavedRunError)):
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    else:  # pragma: no cover - callers pass only the explicit domain exceptions above
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get(
    "/options",
    response_model=HistoricalOptionsResponse,
    summary="List historical analysis options",
)
def historical_options(database_path: DatabasePath) -> dict:
    """Return real, bounded filter values and normalized analysis defaults."""
    return get_historical_options(database_path)


@router.get(
    "/overview",
    response_model=HistoricalOverviewResponse,
    summary="Get the historical campaign overview",
)
def historical_overview(database_path: DatabasePath) -> dict:
    """Return aggregate-only full-history performance and label distribution."""
    return get_historical_overview(database_path)


@router.post(
    "/analyses",
    response_model=HistoricalAnalysisRunResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
    summary="Run and save a historical cohort analysis",
)
def create_analysis(
    filters: HistoricalAnalysisFilters,
    database_path: DatabasePath,
) -> dict:
    """Synchronously create and return one bounded saved aggregate snapshot."""
    try:
        return create_historical_analysis(database_path, filters)
    except (
        HistoricalAnalysisValidationError,
        HistoricalDataNotReadyError,
        NoMatchingObservationsError,
        HistoricalDataIntegrityError,
        HistoricalAnalysisExecutionError,
        HistoricalSavedRunError,
    ) as exc:
        _raise_public_domain_error(exc)


@router.get(
    "/analyses",
    response_model=list[HistoricalAnalysisListItemResponse],
    response_model_exclude_none=True,
    summary="List saved historical analyses",
)
def list_analyses(
    database_path: DatabasePath,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict]:
    """Return bounded saved-run summaries newest first, without full results."""
    try:
        return list_historical_analysis_runs(
            database_path,
            limit=limit,
            offset=offset,
        )
    except (HistoricalAnalysisValidationError, HistoricalSavedRunError) as exc:
        _raise_public_domain_error(exc)


@router.get(
    "/analyses/{analysis_run_id}",
    response_model=HistoricalAnalysisRunResponse,
    response_model_exclude_none=True,
    summary="Get a saved historical analysis",
)
def get_analysis(
    analysis_run_id: Annotated[int, PathParameter(gt=0)],
    database_path: DatabasePath,
) -> dict:
    """Return a full completed snapshot or sanitized failed-run metadata."""
    try:
        return get_historical_analysis_run(database_path, analysis_run_id)
    except (
        HistoricalAnalysisValidationError,
        HistoricalAnalysisNotFoundError,
        HistoricalSavedRunError,
    ) as exc:
        _raise_public_domain_error(exc)
