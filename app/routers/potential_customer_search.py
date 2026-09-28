"""Additive Phase 11 business search, result, and governed download APIs."""
from typing import Annotated
from pathlib import Path
import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Path as PathParameter, Request
from starlette.responses import Response, StreamingResponse

from app.dependencies import get_database_path
from app.repositories.campaign_result_registry_repository import CampaignResultRegistryRepository
from app.schemas.potential_customer_search import (
    PotentialCustomerSearchRequest,
    PotentialCustomerPreflightRequest,
    PotentialCustomerPreflightResponse,
    FeedbackBatchResponse,
    SearchResultDetail,
    SearchResultHistoryItem,
    SearchSubmissionStatus,
    SearchSubmissionV2Status,
)
from app.services import potential_customer_search_submission_service as service
from app.services import phase11_results_service as results_service
from app.services import phase11_export_service as export_service
from app.services.potential_customer_preflight_service import exact_preflight
from app.services.phase11_feedback_service import (
    FEEDBACK_CSV_TEMPLATE, FEEDBACK_JSON_TEMPLATE,
    FeedbackConflictError, FeedbackValidationError, ingest_feedback,
    list_feedback, parse_feedback_csv,
)
from app.main_paths import PROJECT_ROOT
from app.services.campaign_targeting_context_service import CampaignContextValidationError
from app.services.phase11_result_contracts import Phase11RegistryValidationError, Phase11RegistryStateError

router = APIRouter(tags=["potential customer search"])
DatabasePath = Annotated[Path, Depends(get_database_path)]
logger = logging.getLogger(__name__)


@router.get("/api/potential-customer-search/feedback-template.csv")
def download_feedback_csv_template() -> Response:
    return Response(
        FEEDBACK_CSV_TEMPLATE,
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                'attachment; filename="purchase_outcome_feedback_template.csv"'
            ),
        },
    )


@router.get("/api/potential-customer-search/feedback-template.json")
def download_feedback_json_template() -> Response:
    return Response(
        json.dumps(FEEDBACK_JSON_TEMPLATE, indent=2) + "\n",
        media_type="application/json",
        headers={
            "Content-Disposition": (
                'attachment; filename="purchase_outcome_feedback_template.json"'
            ),
        },
    )


@router.get("/api/export-profiles")
def export_profiles(database_path: DatabasePath) -> list[dict]:
    return service.export_profile_options(database_path)


@router.get("/api/potential-customer-search/options")
def search_options(database_path: DatabasePath) -> dict:
    return service.search_form_options(database_path)


@router.post("/api/potential-customer-search/runs", response_model=SearchSubmissionV2Status | SearchSubmissionStatus, status_code=201)
def create_search(request: PotentialCustomerSearchRequest, database_path: DatabasePath) -> dict:
    try:
        return service.submit_potential_customer_search(database_path, request)
    except (ValueError, CampaignContextValidationError, Phase11RegistryValidationError) as exc:
        raise HTTPException(422, "Review your campaign choices, targeting preferences and available download profile.") from exc
    except Exception as exc:
        logger.exception("Search submission failed")
        raise HTTPException(500, "Your search could not be saved. Please try again.") from exc


@router.post(
    "/api/potential-customer-search/preflight",
    response_model=PotentialCustomerPreflightResponse,
)
def preflight_search(request: PotentialCustomerPreflightRequest, database_path: DatabasePath) -> dict:
    try:
        return exact_preflight(
            database_path, context=request.context, criteria=request.criteria,
            propensity_bucket=request.propensity_bucket,
            catalog_version=request.catalog_version,
        )
    except (ValueError, CampaignContextValidationError, Phase11RegistryValidationError) as exc:
        raise HTTPException(422, "Review the targeting choices before checking the exact count.") from exc


@router.get("/api/potential-customer-search/runs", response_model=list[SearchSubmissionV2Status | SearchSubmissionStatus])
def search_history(database_path: DatabasePath, limit: Annotated[int, Query(ge=1, le=100)] = 20,
                   before_search_run_id: Annotated[int | None, Query(gt=0, le=2**63-1)] = None) -> list[dict]:
    try:
        rows = CampaignResultRegistryRepository(database_path).list_search_runs(limit=limit, before_search_run_id=before_search_run_id)
    except Phase11RegistryStateError as exc:
        raise HTTPException(404, "The search history position was not found.") from exc
    return service.project_search_statuses(rows, database_path)


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
    return service.project_search_status(row, database_path)


@router.get(
    "/api/potential-customer-search/runs/{search_run_id}",
    response_model=SearchSubmissionV2Status | SearchSubmissionStatus,
)
def get_search_run(
    search_run_id: Annotated[int, PathParameter(gt=0, le=2**63 - 1)],
    database_path: DatabasePath,
) -> dict:
    return _project_search_run(search_run_id, database_path)


@router.get(
    "/api/potential-customer-search/runs/{search_run_id}/status",
    response_model=SearchSubmissionV2Status | SearchSubmissionStatus,
)
def search_status(
    search_run_id: Annotated[int, PathParameter(gt=0, le=2**63 - 1)],
    database_path: DatabasePath,
) -> dict:
    return _project_search_run(search_run_id, database_path)


@router.post(
    "/api/potential-customer-search/runs/{search_run_id}/retry",
    response_model=SearchSubmissionV2Status | SearchSubmissionStatus,
    status_code=202,
)
def retry_search_run(
    search_run_id: Annotated[int, PathParameter(gt=0, le=2**63 - 1)],
    database_path: DatabasePath,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
) -> dict:
    try:
        return service.retry_potential_customer_search(
            database_path, search_run_id, idempotency_key=idempotency_key,
        )
    except Phase11RegistryStateError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, Phase11RegistryValidationError) as exc:
        raise HTTPException(422, "This saved search cannot be retried safely.") from exc


@router.post(
    "/api/potential-customer-search/runs/{search_run_id}/feedback",
    response_model=FeedbackBatchResponse,
    status_code=201,
)
async def upload_search_feedback(
    search_run_id: Annotated[int, PathParameter(gt=0, le=2**63 - 1)],
    request: Request,
    database_path: DatabasePath,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
    feedback_source: Annotated[str, Header(alias="X-Feedback-Source", min_length=1, max_length=120)] = "governed-upload",
) -> dict:
    try:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type in {"text/csv", "application/csv"}:
            rows = parse_feedback_csv(await request.body())
        elif content_type == "application/json":
            payload = await request.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
                raise FeedbackValidationError("JSON feedback requires a rows array.")
            rows = payload["rows"]
            source = payload.get("source_name")
            if source is not None:
                feedback_source = str(source)
        else:
            raise FeedbackValidationError("Use application/json or text/csv feedback.")
        return ingest_feedback(
            database_path, search_run_id, rows=rows,
            source_name=feedback_source, idempotency_key=idempotency_key,
            project_root=PROJECT_ROOT,
        )
    except FeedbackValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    except FeedbackConflictError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get(
    "/api/potential-customer-search/runs/{search_run_id}/feedback",
    response_model=list[FeedbackBatchResponse],
)
def get_search_feedback(
    search_run_id: Annotated[int, PathParameter(gt=0, le=2**63 - 1)],
    database_path: DatabasePath,
) -> list[dict]:
    return list_feedback(database_path, search_run_id)


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
