"""Step 8 submission boundary; Step 9 owns durable smart-reuse execution.

Never claim readiness or start Phase 10 work from field/profile edits. Without
the later executor, save an inspectable BLOCKED run rather than a fake result.
"""
from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories.campaign_result_registry_repository import CampaignResultRegistryRepository
from app.repositories.campaign_targeting_context_repository import CampaignTargetingContextRepository
from app.schemas.campaign_targeting import TARGETING_SEGMENT_CONTRACT_VERSION, BUSINESS_MATCH_STRENGTH_CONTRACT_VERSION
from app.schemas.potential_customer_search import PotentialCustomerSearchRequest
from app.services.campaign_targeting_context_service import (
    _allowed_values, _targeting_allowed_values,
    decorate_context_options, decorate_targeting_options,
)
from app.services.campaign_targeting_contract_service import (
    normalize_campaign_targeting_context, normalize_business_targeting_criteria,
)
from app.services.phase10_context_identity_service import derive_modeling_context_from_campaign_context
from app.services.phase11_run_lifecycle_service import (
    project_run_issue,
    project_run_progress,
)
from app.services.phase11_dependency_retry_service import (
    classify_failure_ownership,
    retry_or_rejoin_phase10_dependency,
)
from app.services.phase11_result_contracts import Phase11RegistryStateError
from app.services.omnichannel_profile_contracts import (
    OMNICHANNEL_PROFILE_REGISTRY, get_omnichannel_profile, get_omnichannel_profile_for_channel, resolve_profile_availability,
)
from app.services.targeting_option_catalog_service import (
    get_or_build_targeting_catalog, get_targeting_catalog,
)
from app.services.calibrated_selection_contract_service import propensity_bucket_bounds

SearchExecutor = Callable[[Path, int], None]
# Explicit composition seam. Step 9 owns decisions/filtering and Step 11 owns
# safe membership publication; enable only when both production collaborators exist.
PHASE11_SEARCH_EXECUTOR: SearchExecutor | None = None
PHASE11_CAMPAIGN_CONTEXT_CONTRACT_VERSION = "PHASE11_1"


def configure_phase11_search_executor(executor: SearchExecutor) -> None:
    """Configure the production runtime handoff during application startup."""

    if not callable(executor):
        raise TypeError("Phase 11 search executor must be callable.")
    global PHASE11_SEARCH_EXECUTOR
    PHASE11_SEARCH_EXECUTOR = executor


def reset_phase11_search_executor() -> None:
    """Disconnect the runtime handoff during application shutdown."""

    global PHASE11_SEARCH_EXECUTOR
    PHASE11_SEARCH_EXECUTOR = None


def normalize_search_context(raw_context: dict, allowed_values: dict) -> dict:
    """Reuse all five Phase 9 reference/list rules, but keep Phase 11 delivery separate.

    The legacy channel enum remains frozen. Its validator is used only for the
    analytical dimensions; the real channel is registry-validated, restored and
    persisted under an explicitly additive context version, never as fake EMAIL.
    """
    channel = get_omnichannel_profile_for_channel(raw_context.get("campaign_channel")).channel_code
    legacy_projection = dict(raw_context, campaign_channel="EMAIL")
    payload = normalize_campaign_targeting_context(legacy_projection, allowed_values=allowed_values).payload
    return payload | {"campaign_channel": channel,
                      "campaign_targeting_context_contract_version": PHASE11_CAMPAIGN_CONTEXT_CONTRACT_VERSION}


def export_profile_options(database_path: str | Path) -> list[dict]:
    path = initialize_database(database_path)
    with get_connection(path) as connection:
        fields = {row["name"] for row in connection.execute("PRAGMA table_info(demographics)")}
    result = []
    for profile in OMNICHANNEL_PROFILE_REGISTRY.values():
        availability = resolve_profile_availability(profile.export_profile, available_source_fields=fields)
        result.append(dict(
            channel_code=profile.channel_code, export_profile=profile.export_profile,
            profile_version=profile.profile_version,
            label=profile.channel_code.replace("_", " ").title(), availability=availability,
            unavailable_reason=None if availability == "AVAILABLE" else "Required source identifiers or contact permissions are unavailable.",
        ))
    return result


def search_form_options(database_path: str | Path) -> dict:
    path = initialize_database(database_path)
    catalog = get_or_build_targeting_catalog(path)
    targeting = decorate_targeting_options(catalog["targeting"])
    targeting["default_propensity_bucket"] = "0.70"
    targeting["propensity_buckets"] = [
        {"value": value, "label": label, "minimum": minimum,
         "maximum": maximum, "maximum_inclusive": inclusive,
         "recommended": value == "0.70"}
        for value, label, minimum, maximum, inclusive in (
            ("0.90", "90% to 100% purchase propensity", .9, 1.0, True),
            ("0.80", "80% to under 90% purchase propensity", .8, .9, False),
            ("0.70", "70% to under 80% purchase propensity", .7, .8, False),
            ("0.60", "60% to under 70% purchase propensity", .6, .7, False),
            ("0.50", "50% to under 60% purchase propensity", .5, .6, False),
        )
    ]
    return dict(catalog_version=catalog["catalog_version"],
                catalog_created_at=catalog["catalog_created_at"],
                context=decorate_context_options(catalog["context"]),
                targeting=targeting,
                profiles=export_profile_options(database_path),
                workflow_available=PHASE11_SEARCH_EXECUTOR is not None)


def _project_search_status(
    row: dict,
    *,
    repository: CampaignResultRegistryRepository | None,
    runtime: dict | None,
    attempt: dict | None,
    stage_history: dict[tuple[str, str], list[float]],
    queue_positions: dict[int, int],
) -> dict:
    messages = {
        "QUEUED": "Your search is saved and waiting to prepare targeting intelligence.",
        "PROCESSING": "Preparing targeting intelligence. You can leave; your search stays in Results.",
        "COMPLETED": "Your potential-customer result is ready in Results.",
        "BLOCKED": "Your search is saved but cannot proceed with the current targeting intelligence.",
        "FAILED": "Your search could not be completed. It remains saved in Results; please try again.",
    }
    if row["status"] == "BLOCKED" and PHASE11_SEARCH_EXECUTOR is None:
        messages["BLOCKED"] = "Your search is saved. Targeting intelligence preparation is not connected in this release yet."
    payload = {key: row[key] for key in (
        "search_run_id", "campaign_name", "status", "created_at", "completed_at",
        "selected_count", "delivery_channel", "export_profile",
    )} | {
        "safe_message": messages[row["status"]],
    }
    if str(row.get("selection_contract_version") or "1") != "2":
        return payload

    issue = project_run_issue(runtime)
    stage_samples = (
        stage_history.get((
            str(runtime["workload_class"]), str(runtime["stage_code"])
        )) if runtime is not None else None
    )
    payload.update({
        "selection_contract_version": str(row.get("selection_contract_version") or "1"),
        "attempt_number": int(row.get("current_attempt_number") or 1),
        "queue_position": (
            queue_positions.get(int(row["search_run_id"]))
            if repository is not None and row["status"] == "QUEUED"
            else None
        ),
        "propensity_bucket": row.get("propensity_bucket"),
        "progress": project_run_progress(
            row,
            runtime,
            attempt=attempt,
            stage_duration_samples=stage_samples,
        ),
        "issue": issue,
        "retry_eligible": bool(issue and issue.get("retryable")),
    })
    return payload


def project_search_status(row: dict, database_path: str | Path | None = None) -> dict:
    repository = CampaignResultRegistryRepository(database_path) if database_path else None
    runtime = repository.fetch_search_runtime(int(row["search_run_id"])) if repository else None
    attempt = repository.fetch_current_attempt(int(row["search_run_id"])) if repository else None
    stage_history = (
        repository.stage_duration_history()
        if repository is not None and row["status"] == "PROCESSING"
        else {}
    )
    queue_positions = (
        repository.queue_positions([int(row["search_run_id"])])
        if repository is not None and row["status"] == "QUEUED"
        else {}
    )
    return _project_search_status(
        row,
        repository=repository,
        runtime=runtime,
        attempt=attempt,
        stage_history=stage_history,
        queue_positions=queue_positions,
    )


def project_search_statuses(
    rows: list[dict], database_path: str | Path,
) -> list[dict]:
    """Project saved-search history with a bounded number of metadata queries."""

    if not rows:
        return []
    repository = CampaignResultRegistryRepository(database_path)
    identifiers = [int(row["search_run_id"]) for row in rows]
    runtimes = repository.fetch_search_runtimes(identifiers)
    attempts = repository.fetch_current_attempts(identifiers)
    stage_history = repository.stage_duration_history()
    queue_positions = repository.queue_positions(
        [int(row["search_run_id"]) for row in rows if row["status"] == "QUEUED"]
    )
    return [
        _project_search_status(
            row,
            repository=repository,
            runtime=runtimes.get(int(row["search_run_id"])),
            attempt=attempts.get(int(row["search_run_id"])),
            stage_history=stage_history,
            queue_positions=queue_positions,
        )
        for row in rows
    ]


def normalize_search_definition(
    path: Path,
    *,
    raw_context: dict,
    raw_criteria: dict,
    propensity_bucket: str | None,
    catalog_version: str | None,
    require_current_catalog: bool = True,
) -> tuple[dict, object, dict]:
    """Validate a search or preflight against one exact catalog snapshot."""

    catalog = (
        get_targeting_catalog(path, catalog_version)
        if catalog_version else get_or_build_targeting_catalog(path)
    )
    if catalog is None or (
        require_current_catalog and not catalog.get("is_current", True)
    ):
        raise ValueError("Reload current campaign choices before submitting.")
    context_options = decorate_context_options(catalog["context"])
    targeting_options = decorate_targeting_options(catalog["targeting"])
    context = normalize_search_context(raw_context, _allowed_values(context_options))
    normalized_raw_criteria = dict(raw_criteria)
    if propensity_bucket is not None:
        normalized_raw_criteria["match_strength"] = {
            "0.90": "VERY_STRONG", "0.80": "STRONG", "0.70": "GOOD",
            "0.60": "BROAD", "0.50": "BROAD",
        }[propensity_bucket]
    criteria = normalize_business_targeting_criteria(
        normalized_raw_criteria,
        allowed_values=_targeting_allowed_values(targeting_options),
    )
    if propensity_bucket is not None:
        lower, upper, maximum_inclusive = propensity_bucket_bounds(propensity_bucket)
        branches = []
        for branch in criteria.audience_filter_branches:
            branches.append(dict(
                branch, score_min=lower,
                score_max=upper if maximum_inclusive else math.nextafter(upper, 0.0),
            ))
        payload = dict(criteria.payload)
        payload["propensity_bucket"] = propensity_bucket
        payload["selection_contract_version"] = "2"
        canonical = json.dumps(payload, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))
        criteria = type(criteria)(
            payload=payload, canonical_json=canonical,
            sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            audience_filter_branches=tuple(branches),
            audience_selection=criteria.audience_selection,
        )
    return context, criteria, catalog


def submit_potential_customer_search(database_path: str | Path, request: PotentialCustomerSearchRequest) -> dict:
    path = initialize_database(database_path)
    profiles = export_profile_options(path)
    profile = get_omnichannel_profile(request.export_profile)
    selected = next(item for item in profiles if item["export_profile"] == profile.export_profile)
    if selected["availability"] != "AVAILABLE":
        raise ValueError("Choose an available download profile.")
    if request.context.get("campaign_channel") != profile.channel_code:
        raise ValueError("The delivery channel and download profile must match.")
    context, criteria, catalog = normalize_search_definition(
        path, raw_context=request.context, raw_criteria=request.criteria,
        propensity_bucket=request.propensity_bucket,
        catalog_version=request.catalog_version,
    )
    identity = derive_modeling_context_from_campaign_context(context)
    # A fresh context per submission prevents later form edits changing a prior run's context.
    context_json = json.dumps(context, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))
    repository = CampaignResultRegistryRepository(path)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    with get_connection(path, write=True) as connection:
        connection.execute("BEGIN IMMEDIATE")
        context_id = CampaignTargetingContextRepository(path).create_context(
            campaign_context_contract_version=PHASE11_CAMPAIGN_CONTEXT_CONTRACT_VERSION,
            targeting_segment_contract_version=TARGETING_SEGMENT_CONTRACT_VERSION,
            business_match_strength_contract_version=BUSINESS_MATCH_STRENGTH_CONTRACT_VERSION,
            campaign_context_json=context_json, campaign_context_sha256=hashlib.sha256(context_json.encode("utf-8")).hexdigest(),
            targeting_criteria_json=criteria.canonical_json, targeting_criteria_sha256=criteria.sha256,
            timestamp=timestamp, connection=connection,
        )
        run_id = repository.create_search_run(
            campaign_name=request.campaign_name, description=request.description or None,
            planned_launch_date=request.planned_launch_date.isoformat() if request.planned_launch_date else None,
            targeting_context_id=context_id, modeling_context_sha256=identity.modeling_context_sha256,
            targeting_criteria=criteria.payload, filter_branches=list(criteria.audience_filter_branches),
            selection_mode=criteria.audience_selection["mode"], target_count=criteria.audience_selection["target_count"],
            delivery_channel=profile.channel_code, export_profile=profile.export_profile,
            selection_contract_version="2" if request.propensity_bucket else "1",
            propensity_bucket=request.propensity_bucket,
            catalog_version=catalog["catalog_version"], connection=connection,
            timestamp=timestamp,
        )
    if PHASE11_SEARCH_EXECUTOR is None:
        fence = repository.claim_search_attempt(
            run_id, lease_owner="phase11-submission-failure"
        )
        repository.fail_search_run(
            run_id,
            **fence.as_kwargs(),
            blocked=True,
            failure_code="SEARCH_RUNTIME_UNAVAILABLE",
            failure_category="SYSTEM_AVAILABILITY",
            failure_summary="Search processing is temporarily unavailable.",
            resolution_steps=(
                "Wait until the application reports that search processing is available.",
                "Retry this saved search when the service is available.",
            ),
            retryable=True,
        )
    else:
        try:
            PHASE11_SEARCH_EXECUTOR(path, run_id)
        except Exception:
            # Preserve the run and a fixed safe failure; never expose executor exceptions.
            current = repository.fetch_search_run(run_id)
            if current["status"] in {"QUEUED", "PROCESSING"}:
                fence = repository.claim_search_attempt(
                    run_id, lease_owner="phase11-submission-failure"
                )
                repository.fail_search_run(run_id, **fence.as_kwargs())
    return project_search_status(repository.fetch_search_run(run_id), path)


def retry_potential_customer_search(
    database_path: str | Path,
    search_run_id: int,
    *,
    idempotency_key: str,
) -> dict:
    path = initialize_database(database_path)
    repository = CampaignResultRegistryRepository(path)
    previous_runtime = repository.fetch_search_runtime(search_run_id)
    ownership = classify_failure_ownership(previous_runtime)
    if ownership == "PHASE10_BUSINESS":
        raise Phase11RegistryStateError(
            "This search needs revised business criteria or additional verified history; retry would repeat the same block."
        )
    if ownership == "PERMANENT_VALIDATION":
        raise Phase11RegistryStateError(
            "This search has a permanent validation failure and cannot be retried."
        )
    repository.retry_search_run(
        search_run_id, idempotency_key=idempotency_key,
    )
    if ownership == "PHASE10_TRANSIENT":
        fence = repository.claim_search_attempt(
            search_run_id, lease_owner="phase11-dependency-retry"
        )
        run = repository.fetch_search_run(search_run_id)
        assert run is not None
        retry_or_rejoin_phase10_dependency(path, run, fence=fence)
    if PHASE11_SEARCH_EXECUTOR is None:
        fence = repository.claim_search_attempt(
            search_run_id, lease_owner="phase11-retry-failure"
        )
        repository.fail_search_run(
            search_run_id,
            **fence.as_kwargs(),
            blocked=True,
            failure_code="SEARCH_RUNTIME_UNAVAILABLE",
            failure_category="SYSTEM_AVAILABILITY",
            failure_summary="Search processing is temporarily unavailable.",
            resolution_steps=(
                "Wait until the application reports that search processing is available.",
                "Retry this saved search when the service is available.",
            ),
        )
    else:
        PHASE11_SEARCH_EXECUTOR(path, search_run_id)
    return project_search_status(repository.fetch_search_run(search_run_id), path)
