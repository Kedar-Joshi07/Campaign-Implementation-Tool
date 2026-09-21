"""Step 8 submission boundary; Step 9 owns durable smart-reuse execution.

Never claim readiness or start Phase 10 work from field/profile edits. Without
the later executor, save an inspectable BLOCKED run rather than a fake result.
"""
from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories.campaign_result_registry_repository import CampaignResultRegistryRepository
from app.repositories.campaign_targeting_context_repository import CampaignTargetingContextRepository
from app.schemas.campaign_targeting import TARGETING_SEGMENT_CONTRACT_VERSION, BUSINESS_MATCH_STRENGTH_CONTRACT_VERSION
from app.schemas.potential_customer_search import PotentialCustomerSearchRequest
from app.services.campaign_targeting_context_service import (
    get_campaign_context_options, get_business_targeting_options,
    _allowed_values, _targeting_allowed_values,
)
from app.services.campaign_targeting_contract_service import (
    normalize_campaign_targeting_context, normalize_business_targeting_criteria,
)
from app.services.phase10_context_identity_service import derive_modeling_context_from_campaign_context
from app.services.omnichannel_profile_contracts import (
    OMNICHANNEL_PROFILE_REGISTRY, get_omnichannel_profile, get_omnichannel_profile_for_channel, resolve_profile_availability,
)

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
    return dict(context=get_campaign_context_options(database_path),
                targeting=get_business_targeting_options(database_path),
                profiles=export_profile_options(database_path),
                workflow_available=PHASE11_SEARCH_EXECUTOR is not None)


def project_search_status(row: dict) -> dict:
    messages = {
        "QUEUED": "Your search is saved and waiting to prepare targeting intelligence.",
        "PROCESSING": "Preparing targeting intelligence. You can leave; your search stays in Results.",
        "COMPLETED": "Your potential-customer result is ready in Results.",
        "BLOCKED": "Your search is saved but cannot proceed with the current targeting intelligence.",
        "FAILED": "Your search could not be completed. It remains saved in Results; please try again.",
    }
    if row["status"] == "BLOCKED" and PHASE11_SEARCH_EXECUTOR is None:
        messages["BLOCKED"] = "Your search is saved. Targeting intelligence preparation is not connected in this release yet."
    return {key: row[key] for key in (
        "search_run_id", "campaign_name", "status", "created_at", "completed_at",
        "selected_count", "delivery_channel", "export_profile",
    )} | {"safe_message": messages[row["status"]]}


def submit_potential_customer_search(database_path: str | Path, request: PotentialCustomerSearchRequest) -> dict:
    path = initialize_database(database_path)
    profiles = export_profile_options(path)
    profile = get_omnichannel_profile(request.export_profile)
    selected = next(item for item in profiles if item["export_profile"] == profile.export_profile)
    if selected["availability"] != "AVAILABLE":
        raise ValueError("Choose an available download profile.")
    if request.context.get("campaign_channel") != profile.channel_code:
        raise ValueError("The delivery channel and download profile must match.")
    # Validate all business/reference selections BEFORE persisting either object.
    context = normalize_search_context(request.context, _allowed_values(get_campaign_context_options(path)))
    criteria = normalize_business_targeting_criteria(request.criteria, allowed_values=_targeting_allowed_values(get_business_targeting_options(path)))
    identity = derive_modeling_context_from_campaign_context(context)
    # A fresh context per submission prevents later form edits changing a prior run's context.
    context_json = json.dumps(context, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))
    context_id = CampaignTargetingContextRepository(path).create_context(
        campaign_context_contract_version=PHASE11_CAMPAIGN_CONTEXT_CONTRACT_VERSION,
        targeting_segment_contract_version=TARGETING_SEGMENT_CONTRACT_VERSION,
        business_match_strength_contract_version=BUSINESS_MATCH_STRENGTH_CONTRACT_VERSION,
        campaign_context_json=context_json, campaign_context_sha256=hashlib.sha256(context_json.encode("utf-8")).hexdigest(),
        targeting_criteria_json=criteria.canonical_json, targeting_criteria_sha256=criteria.sha256,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    )
    repository = CampaignResultRegistryRepository(path)
    run_id = repository.create_search_run(
        campaign_name=request.campaign_name, description=request.description or None,
        planned_launch_date=request.planned_launch_date.isoformat() if request.planned_launch_date else None,
        targeting_context_id=context_id, modeling_context_sha256=identity.modeling_context_sha256,
        targeting_criteria=criteria.payload, filter_branches=list(criteria.audience_filter_branches),
        selection_mode=criteria.audience_selection["mode"], target_count=criteria.audience_selection["target_count"],
        delivery_channel=profile.channel_code, export_profile=profile.export_profile,
    )
    if PHASE11_SEARCH_EXECUTOR is None:
        repository.fail_search_run(run_id, blocked=True)
    else:
        try:
            PHASE11_SEARCH_EXECUTOR(path, run_id)
        except Exception:
            # Preserve the run and a fixed safe failure; never expose executor exceptions.
            current = repository.fetch_search_run(run_id)
            if current["status"] in {"QUEUED", "PROCESSING"}:
                repository.fail_search_run(run_id)
    return project_search_status(repository.fetch_search_run(run_id))
