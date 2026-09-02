"""Campaign Builder API routes for Phase 7 Section 2."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Path as PathParameter, Query, Request, status
from fastapi.responses import StreamingResponse

from app.dependencies import get_database_path
from app.schemas.campaigns import (
    CampaignCreateRequest,
    CampaignCurrentnessResponse,
    CampaignDetailResponse,
    CampaignExportEventResponse,
    CampaignFinalizeResponse,
    CampaignOptionsResponse,
    CampaignSummaryResponse,
    CampaignUpdateRequest,
)
from app.services.campaign_service import (
    CampaignServiceConflictError,
    CampaignServiceError,
    CampaignServiceNotFoundError,
    CampaignServiceUnavailableError,
    CampaignServiceValidationError,
    create_campaign,
    evaluate_campaign_currentness,
    finalize_campaign,
    get_campaign,
    get_campaign_options,
    list_campaign_export_events,
    list_campaigns,
    stream_campaign_export_csv,
    update_campaign,
)


router = APIRouter(prefix="/api", tags=["campaigns"])
DatabasePath = Annotated[Path, Depends(get_database_path)]


def _raise_campaign_error(exc: CampaignServiceError) -> NoReturn:
    if isinstance(exc, CampaignServiceNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, CampaignServiceConflictError):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, CampaignServiceValidationError):
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    elif isinstance(exc, CampaignServiceUnavailableError):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get(
    "/campaigns/options",
    response_model=CampaignOptionsResponse,
    response_model_exclude_none=True,
    summary="Get campaign draft options and eligible saved audiences",
)
def campaign_options(database_path: DatabasePath) -> dict:
    try:
        return get_campaign_options(database_path)
    except CampaignServiceError as exc:
        _raise_campaign_error(exc)


@router.post(
    "/campaigns",
    response_model=CampaignDetailResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
    summary="Create campaign draft from a current saved audience",
)
def create_campaign_draft(request: CampaignCreateRequest, database_path: DatabasePath) -> dict:
    try:
        return create_campaign(database_path, request.model_dump(mode="json"))
    except CampaignServiceError as exc:
        _raise_campaign_error(exc)


@router.get(
    "/campaigns",
    response_model=list[CampaignSummaryResponse],
    response_model_exclude_none=True,
    summary="List campaigns with lightweight currentness",
)
def list_campaign_summaries(
    database_path: DatabasePath,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict]:
    try:
        return list_campaigns(database_path, limit=limit, offset=offset)
    except CampaignServiceError as exc:
        _raise_campaign_error(exc)


@router.get(
    "/campaigns/{campaign_id}",
    response_model=CampaignDetailResponse,
    response_model_exclude_none=True,
    summary="Get campaign detail",
)
def get_campaign_detail(
    campaign_id: Annotated[int, PathParameter(gt=0)],
    database_path: DatabasePath,
) -> dict:
    try:
        return get_campaign(database_path, campaign_id=campaign_id)
    except CampaignServiceError as exc:
        _raise_campaign_error(exc)


@router.patch(
    "/campaigns/{campaign_id}",
    response_model=CampaignDetailResponse,
    response_model_exclude_none=True,
    summary="Update a DRAFT campaign",
)
def update_campaign_draft(
    campaign_id: Annotated[int, PathParameter(gt=0)],
    request: CampaignUpdateRequest,
    database_path: DatabasePath,
) -> dict:
    try:
        return update_campaign(
            database_path,
            campaign_id=campaign_id,
            request_payload=request.model_dump(mode="json", exclude_none=True),
        )
    except CampaignServiceError as exc:
        _raise_campaign_error(exc)


@router.get(
    "/campaigns/{campaign_id}/currentness",
    response_model=CampaignCurrentnessResponse,
    response_model_exclude_none=True,
    summary="Evaluate campaign currentness and eligibility",
)
def get_campaign_currentness(
    campaign_id: Annotated[int, PathParameter(gt=0)],
    database_path: DatabasePath,
) -> dict:
    try:
        return evaluate_campaign_currentness(database_path, campaign_id=campaign_id)
    except CampaignServiceError as exc:
        _raise_campaign_error(exc)


@router.post(
    "/campaigns/{campaign_id}/finalize",
    response_model=CampaignFinalizeResponse,
    response_model_exclude_none=True,
    summary="Finalize a current DRAFT campaign",
)
def finalize_campaign_draft(
    campaign_id: Annotated[int, PathParameter(gt=0)],
    database_path: DatabasePath,
) -> dict:
    try:
        return finalize_campaign(database_path, campaign_id=campaign_id)
    except CampaignServiceError as exc:
        _raise_campaign_error(exc)


@router.get(
    "/campaigns/{campaign_id}/exports",
    response_model=list[CampaignExportEventResponse],
    response_model_exclude_none=True,
    summary="List aggregate campaign export events",
)
def get_campaign_export_events(
    campaign_id: Annotated[int, PathParameter(gt=0)],
    database_path: DatabasePath,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict]:
    try:
        return list_campaign_export_events(database_path, campaign_id=campaign_id, limit=limit)
    except CampaignServiceError as exc:
        _raise_campaign_error(exc)


@router.get(
    "/campaigns/{campaign_id}/export.csv",
    summary="Stream finalized campaign targets as CSV",
)
async def export_campaign_csv(
    campaign_id: Annotated[int, PathParameter(gt=0)],
    request: Request,
    database_path: DatabasePath,
    acknowledge_pii: Annotated[bool, Query()] = False,
) -> StreamingResponse:
    try:
        return stream_campaign_export_csv(
            database_path,
            campaign_id=campaign_id,
            acknowledge_pii=acknowledge_pii,
            request=request,
        )
    except CampaignServiceError as exc:
        _raise_campaign_error(exc)
