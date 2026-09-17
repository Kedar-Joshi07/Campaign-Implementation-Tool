"""Additive Phase 11 business search, result, and governed download APIs."""
from typing import Annotated
from pathlib import Path
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Path as PathParameter, Request
from starlette.responses import StreamingResponse

from app.dependencies import get_database_path
from app.repositories.campaign_result_registry_repository import CampaignResultRegistryRepository
from app.schemas.potential_customer_search import (
    PotentialCustomerSearchRequest,
    SearchResultDetail,
    SearchResultHistoryItem,
    SearchSubmissionStatus,
)
from app.services import potential_customer_search_submission_service as service
from app.services import phase11_results_service as results_service
from app.services import phase11_export_service as export_service
from app.services.campaign_targeting_context_service import CampaignContextValidationError
from app.services.phase11_result_contracts import Phase11RegistryValidationError, Phase11RegistryStateError

router = APIRouter(tags=["potential customer search"])
DatabasePath = Annotated[Path, Depends(get_database_path)]
logger = logging.getLogger(__name__)


@router.get("/api/export-profiles")
def export_profiles(database_path: DatabasePath) -> list[dict]:
    return service.export_profile_options(database_path)


@router.get("/api/potential-customer-search/options")
def search_options(database_path: DatabasePath) -> dict:
    return service.search_form_options(database_path)


@router.post("/api/potential-customer-search/runs", response_model=SearchSubmissionStatus, status_code=201)
def create_search(request: PotentialCustomerSearchRequest, database_path: DatabasePath) -> dict:
    try:
        return service.submit_potential_customer_search(database_path, request)
    except (ValueError, CampaignContextValidationError, Phase11RegistryValidationError) as exc:
        raise HTTPException(422, "Review your campaign choices, targeting preferences and available download profile.") from exc
    except Exception as exc:
        logger.exception("Search submission failed")
        raise HTTPException(500, "Your search could not be saved. Please try again.") from exc


@router.get("/api/potential-customer-search/runs", response_model=list[SearchSubmissionStatus])
def search_history(database_path: DatabasePath, limit: Annotated[int, Query(ge=1, le=100)] = 20,
                   before_search_run_id: Annotated[int | None, Query(gt=0, le=2**63-1)] = None) -> list[dict]:
    try:
        rows = CampaignResultRegistryRepository(database_path).list_search_runs(limit=limit, before_search_run_id=before_search_run_id)
    except Phase11RegistryStateError as exc:
        raise HTTPException(404, "The search history position was not found.") from exc
    return [service.project_search_status(row) for row in rows]


@router.get(
    "/api/potential-customer-search/results",
    response_model=list[SearchResultHistoryItem],
)
def result_history(
    database_path: DatabasePath,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    before_search_run_id: Annotated[int | None, Query(gt=0, le=2**63-1)] = None,
) -> list[dict]:
    try:
        return results_service.list_result_history(
            database_path, limit=limit,
            before_search_run_id=before_search_run_id,
        )
    except Phase11RegistryStateError as exc:
        raise HTTPException(404, "The result history position was not found.") from exc
    except results_service.Phase11ResultProjectionError as exc:
        logger.exception("Result history projection failed")
        raise HTTPException(500, "Results could not be loaded safely.") from exc


def _project_search_run(search_run_id: int, database_path: Path) -> dict:
    row = CampaignResultRegistryRepository(database_path).fetch_search_run(search_run_id)
    if row is None:
        raise HTTPException(404, "The saved search was not found.")
    return service.project_search_status(row)


@router.get(
    "/api/potential-customer-search/runs/{search_run_id}",
    response_model=SearchSubmissionStatus,
)
def get_search_run(
    search_run_id: Annotated[int, PathParameter(gt=0, le=2**63 - 1)],
    database_path: DatabasePath,
) -> dict:
    return _project_search_run(search_run_id, database_path)


@router.get(
    "/api/potential-customer-search/runs/{search_run_id}/status",
    response_model=SearchSubmissionStatus,
)
def search_status(
    search_run_id: Annotated[int, PathParameter(gt=0, le=2**63 - 1)],
    database_path: DatabasePath,
) -> dict:
    return _project_search_run(search_run_id, database_path)


@router.get(
    "/api/potential-customer-search/runs/{search_run_id}/result",
    response_model=SearchResultDetail,
)
def search_result(
    search_run_id: Annotated[int, PathParameter(gt=0, le=2**63-1)],
    database_path: DatabasePath,
) -> dict:
    try:
        return results_service.get_result_detail(database_path, search_run_id)
    except results_service.Phase11ResultNotFoundError as exc:
        raise HTTPException(404, "The saved result was not found.") from exc
    except results_service.Phase11ResultProjectionError as exc:
        logger.exception("Result detail projection failed")
        raise HTTPException(500, "The result could not be loaded safely.") from exc


@router.get(
    "/api/potential-customer-search/runs/{search_run_id}/download",
    response_class=StreamingResponse,
)
async def download_search_result(
    search_run_id: Annotated[int, PathParameter(gt=0, le=2**63-1)],
    request: Request,
    database_path: DatabasePath,
) -> StreamingResponse:
    try:
        return export_service.stream_phase11_result_export_csv(
            database_path,
            search_run_id=search_run_id,
            request=request,
        )
    except export_service.Phase11ExportNotFoundError as exc:
        raise HTTPException(404, "The saved result was not found.") from exc
    except export_service.Phase11ExportValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    except export_service.Phase11ExportConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (Phase11RegistryValidationError, Phase11RegistryStateError) as exc:
        raise HTTPException(409, "The saved result is not ready for download.") from exc
    except Exception as exc:
        logger.exception("Result download failed")
        raise HTTPException(500, "The result download could not be prepared safely.") from exc
