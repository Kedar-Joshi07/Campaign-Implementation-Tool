"""Phase 9 business campaign-targeting routes."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Path as PathParameter, status

from app.dependencies import get_database_path
from app.schemas.campaign_targeting import (
    BusinessTargetingCriteriaResponse,
    BusinessTargetingCriteriaSaveRequest,
    BusinessTargetingOptionsResponse,
    CampaignContextOptionsResponse,
    CampaignContextResponse,
    CampaignContextSaveRequest,
    MatchStrengthRecommendationResponse,
    Phase9CampaignDraftResponse,
    SaveTargetGroupCampaignDraftRequest,
    TargetingIntelligenceLinkRequest,
    TargetingIntelligenceResolutionResponse,
    TargetGroupPreviewResponse,
    TargetGroupSearchRequest,
    TargetGroupSearchResponse,
)
from app.services.campaign_targeting_context_service import (
    CampaignContextNotFoundError,
    CampaignContextServiceError,
    CampaignContextValidationError,
    get_business_targeting_criteria,
    get_business_targeting_options,
    get_campaign_context_options,
    get_campaign_targeting_context,
    save_campaign_targeting_context,
    save_business_targeting_criteria,
)
from app.services.targeting_intelligence_service import (
    link_targeting_intelligence,
    resolve_targeting_intelligence,
    unlink_targeting_intelligence,
)
from app.services.target_group_preview_service import (
    TargetGroupPreviewNotReadyError,
    get_target_group_preview,
    search_target_group_preview,
)
from app.services.match_strength_recommendation_service import (
    get_match_strength_recommendation,
)
from app.services.target_group_campaign_service import (
    TargetGroupCampaignConflictError,
    reopen_phase9_campaign_draft,
    save_target_group_and_create_campaign_draft,
)


router = APIRouter(prefix="/api/campaign-planner", tags=["campaign targeting"])
DatabasePath = Annotated[Path, Depends(get_database_path)]


def _raise_context_error(exc: CampaignContextServiceError) -> NoReturn:
    if isinstance(exc, CampaignContextNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(
        exc, (TargetGroupPreviewNotReadyError, TargetGroupCampaignConflictError)
    ):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, CampaignContextValidationError):
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "The Campaign Planner could not complete this request. "
                "Your saved information is unchanged; try again."
            ),
        ) from exc
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get(
    "/context-options",
    response_model=CampaignContextOptionsResponse,
    summary="Get current campaign-context choices",
)
def campaign_context_options(database_path: DatabasePath) -> dict:
    try:
        return get_campaign_context_options(database_path)
    except CampaignContextServiceError as exc:
        _raise_context_error(exc)


@router.post(
    "/contexts",
    response_model=CampaignContextResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save a canonical campaign context",
)
def create_campaign_context(
    request: CampaignContextSaveRequest, database_path: DatabasePath
) -> dict:
    try:
        return save_campaign_targeting_context(
            database_path,
            request.context,
        )
    except CampaignContextServiceError as exc:
        _raise_context_error(exc)


@router.get(
    "/contexts/{targeting_context_id}",
    response_model=CampaignContextResponse,
    summary="Reopen a saved campaign context",
)
def campaign_context_detail(
    targeting_context_id: Annotated[int, PathParameter(gt=0)],
    database_path: DatabasePath,
) -> dict:
    try:
        return get_campaign_targeting_context(
            database_path, targeting_context_id=targeting_context_id
        )
    except CampaignContextServiceError as exc:
        _raise_context_error(exc)


@router.put(
    "/contexts/{targeting_context_id}",
    response_model=CampaignContextResponse,
    summary="Update a canonical campaign context",
)
def update_campaign_context(
    targeting_context_id: Annotated[int, PathParameter(gt=0)],
    request: CampaignContextSaveRequest,
    database_path: DatabasePath,
) -> dict:
    try:
        return save_campaign_targeting_context(
            database_path,
            request.context,
            targeting_context_id=targeting_context_id,
        )
    except CampaignContextServiceError as exc:
        _raise_context_error(exc)


@router.get(
    "/targeting-options",
    response_model=BusinessTargetingOptionsResponse,
    summary="Get business-friendly targeting controls",
)
def business_targeting_options(database_path: DatabasePath) -> dict:
    try:
        return get_business_targeting_options(database_path)
    except CampaignContextServiceError as exc:
        _raise_context_error(exc)


@router.get(
    "/contexts/{targeting_context_id}/targeting-criteria",
    response_model=BusinessTargetingCriteriaResponse,
    summary="Reopen saved business targeting criteria",
)
def business_targeting_criteria_detail(
    targeting_context_id: Annotated[int, PathParameter(gt=0)],
    database_path: DatabasePath,
) -> dict:
    try:
        return get_business_targeting_criteria(
            database_path, targeting_context_id=targeting_context_id
        )
    except CampaignContextServiceError as exc:
        _raise_context_error(exc)


@router.put(
    "/contexts/{targeting_context_id}/targeting-criteria",
    response_model=BusinessTargetingCriteriaResponse,
    summary="Validate and save business targeting criteria",
)
def update_business_targeting_criteria(
    targeting_context_id: Annotated[int, PathParameter(gt=0)],
    request: BusinessTargetingCriteriaSaveRequest,
    database_path: DatabasePath,
) -> dict:
    try:
        return save_business_targeting_criteria(
            database_path,
            request.criteria,
            targeting_context_id=targeting_context_id,
        )
    except CampaignContextServiceError as exc:
        _raise_context_error(exc)


@router.get(
    "/contexts/{targeting_context_id}/targeting-intelligence",
    response_model=TargetingIntelligenceResolutionResponse,
    summary="Resolve the explicitly linked targeting-intelligence source",
)
def targeting_intelligence_resolution(
    targeting_context_id: Annotated[int, PathParameter(gt=0)],
    database_path: DatabasePath,
) -> dict:
    try:
        return resolve_targeting_intelligence(
            database_path, targeting_context_id=targeting_context_id
        ).as_dict()
    except CampaignContextServiceError as exc:
        _raise_context_error(exc)


@router.put(
    "/contexts/{targeting_context_id}/targeting-intelligence",
    response_model=TargetingIntelligenceResolutionResponse,
    summary="Advanced analyst/admin: explicitly link a verified scoring source",
)
def attach_targeting_intelligence(
    targeting_context_id: Annotated[int, PathParameter(gt=0)],
    request: TargetingIntelligenceLinkRequest,
    database_path: DatabasePath,
) -> dict:
    try:
        return link_targeting_intelligence(
            database_path,
            targeting_context_id=targeting_context_id,
            scoring_run_id=request.scoring_run_id,
        ).as_dict()
    except CampaignContextServiceError as exc:
        _raise_context_error(exc)


@router.delete(
    "/contexts/{targeting_context_id}/targeting-intelligence",
    response_model=TargetingIntelligenceResolutionResponse,
    summary="Advanced analyst/admin: remove an explicit scoring-source link",
)
def detach_targeting_intelligence(
    targeting_context_id: Annotated[int, PathParameter(gt=0)],
    database_path: DatabasePath,
) -> dict:
    try:
        return unlink_targeting_intelligence(
            database_path, targeting_context_id=targeting_context_id
        ).as_dict()
    except CampaignContextServiceError as exc:
        _raise_context_error(exc)


@router.get(
    "/contexts/{targeting_context_id}/target-group-preview",
    response_model=TargetGroupPreviewResponse,
    summary="Build an exact business target-group preview",
)
def target_group_preview(
    targeting_context_id: Annotated[int, PathParameter(gt=0)],
    database_path: DatabasePath,
) -> dict:
    try:
        return get_target_group_preview(
            database_path, targeting_context_id=targeting_context_id
        )
    except CampaignContextServiceError as exc:
        _raise_context_error(exc)


@router.get(
    "/contexts/{targeting_context_id}/match-strength-recommendation",
    response_model=MatchStrengthRecommendationResponse,
    summary="Compare exact match-strength counts and get deterministic guidance",
)
def match_strength_recommendation(
    targeting_context_id: Annotated[int, PathParameter(gt=0)],
    database_path: DatabasePath,
) -> dict:
    try:
        return get_match_strength_recommendation(
            database_path, targeting_context_id=targeting_context_id
        )
    except CampaignContextServiceError as exc:
        _raise_context_error(exc)


@router.post(
    "/contexts/{targeting_context_id}/target-group-search",
    response_model=TargetGroupSearchResponse,
    summary="Page through an exact target-group preview",
)
def target_group_search(
    targeting_context_id: Annotated[int, PathParameter(gt=0)],
    request: TargetGroupSearchRequest,
    database_path: DatabasePath,
) -> dict:
    try:
        return search_target_group_preview(
            database_path,
            targeting_context_id=targeting_context_id,
            page_size=request.page_size,
            cursor=request.cursor,
        )
    except CampaignContextServiceError as exc:
        _raise_context_error(exc)


@router.post(
    "/contexts/{targeting_context_id}/save-target-group-and-create-draft",
    response_model=Phase9CampaignDraftResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save an immutable Target Group and create or update its Campaign draft",
)
def create_target_group_and_campaign_draft(
    targeting_context_id: Annotated[int, PathParameter(gt=0)],
    request: SaveTargetGroupCampaignDraftRequest,
    database_path: DatabasePath,
) -> dict:
    try:
        return save_target_group_and_create_campaign_draft(
            database_path,
            targeting_context_id=targeting_context_id,
            request_payload=request.model_dump(mode="json"),
        )
    except CampaignContextServiceError as exc:
        _raise_context_error(exc)


@router.get(
    "/contexts/{targeting_context_id}/campaign-draft",
    response_model=Phase9CampaignDraftResponse,
    summary="Reopen the Campaign draft and its immutable Saved Target Group",
)
def campaign_draft_detail(
    targeting_context_id: Annotated[int, PathParameter(gt=0)],
    database_path: DatabasePath,
) -> dict:
    try:
        return reopen_phase9_campaign_draft(
            database_path, targeting_context_id=targeting_context_id
        )
    except CampaignContextServiceError as exc:
        _raise_context_error(exc)


__all__ = ("router",)
