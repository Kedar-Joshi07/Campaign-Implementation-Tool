"""FastAPI endpoints for Phase 4 model training jobs and model-run inspection."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Path as PathParameter, Query, status

from app.dependencies import get_database_path
from app.schemas.models import (
    JobDetailResponse,
    JobSummaryResponse,
    ModelRunDetailResponse,
    ModelRunStatus,
    ModelRunSummaryResponse,
    ScoringRunDetailResponse,
    ScoringRunStatus,
    ScoringRunSummaryResponse,
    ScoringStatusResponse,
    ModelTrainingOptionsResponse,
    ModelTrainingRequest,
)
from app.services.model_api_service import (
    ModelApiConflictError,
    ModelApiError,
    ModelApiNotFoundError,
    ModelApiValidationError,
    get_scoring_run_detail,
    get_scoring_status,
    get_job_detail,
    get_model_run_detail,
    get_model_training_options,
    list_scoring_run_summaries,
    list_model_summaries,
    submit_scoring_request,
    submit_training_request,
)


router = APIRouter(prefix="/api", tags=["model training"])
DatabasePath = Annotated[Path, Depends(get_database_path)]


def _raise_model_api_error(exc: ModelApiError) -> NoReturn:
    if isinstance(exc, ModelApiNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, ModelApiConflictError):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, ModelApiValidationError):
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post(
    "/models/train",
    response_model=JobSummaryResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit asynchronous model training",
)
def submit_model_training(
    request: ModelTrainingRequest,
    database_path: DatabasePath,
) -> dict:
    try:
        return submit_training_request(database_path, request.model_dump())
    except ModelApiError as exc:
        _raise_model_api_error(exc)


@router.post(
    "/models/{model_run_id}/score",
    response_model=JobSummaryResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit asynchronous prospect scoring",
)
def submit_model_scoring(
    model_run_id: Annotated[int, PathParameter(gt=0)],
    database_path: DatabasePath,
) -> dict:
    try:
        return submit_scoring_request(database_path, model_run_id)
    except ModelApiError as exc:
        _raise_model_api_error(exc)


@router.get(
    "/jobs/{job_id}",
    response_model=JobDetailResponse,
    response_model_exclude_none=True,
    summary="Get model-training job status",
)
def get_job(
    job_id: Annotated[int, PathParameter(gt=0)],
    database_path: DatabasePath,
) -> dict:
    try:
        return get_job_detail(database_path, job_id)
    except ModelApiError as exc:
        _raise_model_api_error(exc)


@router.get(
    "/models/{model_run_id}/scoring-status",
    response_model=ScoringStatusResponse,
    response_model_exclude_none=True,
    summary="Get prospect scoring readiness and status",
)
def get_model_scoring_status(
    model_run_id: Annotated[int, PathParameter(gt=0)],
    database_path: DatabasePath,
) -> dict:
    try:
        return get_scoring_status(database_path, model_run_id)
    except ModelApiError as exc:
        _raise_model_api_error(exc)


@router.get(
    "/models/training-options",
    response_model=ModelTrainingOptionsResponse,
    response_model_exclude_none=True,
    summary="Get model training options",
)
def model_training_options(database_path: DatabasePath) -> dict:
    try:
        return get_model_training_options(database_path)
    except ModelApiError as exc:
        _raise_model_api_error(exc)


@router.get(
    "/models",
    response_model=list[ModelRunSummaryResponse],
    response_model_exclude_none=True,
    summary="List model runs",
)
def list_models(
    database_path: DatabasePath,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[ModelRunStatus | None, Query(alias="status")] = None,
) -> list[dict]:
    try:
        return list_model_summaries(
            database_path,
            limit=limit,
            offset=offset,
            status=status_filter,
        )
    except ModelApiError as exc:
        _raise_model_api_error(exc)


@router.get(
    "/scoring-runs",
    response_model=list[ScoringRunSummaryResponse],
    response_model_exclude_none=True,
    summary="List scoring runs",
)
def list_scoring_runs(
    database_path: DatabasePath,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[ScoringRunStatus | None, Query(alias="status")] = None,
    model_run_id: Annotated[int | None, Query(gt=0)] = None,
) -> list[dict]:
    try:
        return list_scoring_run_summaries(
            database_path,
            limit=limit,
            offset=offset,
            status=status_filter,
            model_run_id=model_run_id,
        )
    except ModelApiError as exc:
        _raise_model_api_error(exc)


@router.get(
    "/models/{model_run_id}",
    response_model=ModelRunDetailResponse,
    response_model_exclude_none=True,
    summary="Get model run detail",
)
def get_model(
    model_run_id: Annotated[int, PathParameter(gt=0)],
    database_path: DatabasePath,
) -> dict:
    try:
        return get_model_run_detail(database_path, model_run_id)
    except ModelApiError as exc:
        _raise_model_api_error(exc)


@router.get(
    "/scoring-runs/{scoring_run_id}",
    response_model=ScoringRunDetailResponse,
    response_model_exclude_none=True,
    summary="Get scoring run detail",
)
def get_scoring_run(
    scoring_run_id: Annotated[int, PathParameter(gt=0)],
    database_path: DatabasePath,
) -> dict:
    try:
        return get_scoring_run_detail(database_path, scoring_run_id)
    except ModelApiError as exc:
        _raise_model_api_error(exc)
