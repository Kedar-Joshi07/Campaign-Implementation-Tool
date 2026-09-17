"""Business-safe Phase 11 result history and detail projections."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.database.connection import get_connection
from app.repositories.campaign_result_registry_repository import (
    CampaignResultRegistryRepository,
)
from app.repositories.campaign_targeting_context_repository import (
    CampaignTargetingContextRepository,
)
from app.repositories.phase10_intelligence_repository import (
    Phase10IntelligenceRepository,
)
from app.schemas.campaign_targeting import (
    CanonicalBusinessTargetingCriteria,
)
from app.schemas.potential_customer_search import Phase11SavedCampaignContext
from app.services.phase11_result_snapshot_service import validate_result_snapshot


RESULT_SOURCE_LABELS = {
    "EXACT_RESULT_REUSE": "Reused previous exact result",
    "INTELLIGENCE_REUSE": "Reused existing targeting intelligence",
    "NEW_INTELLIGENCE_BUILD": "Prepared new targeting intelligence",
}
ACTIVE_SEARCH_STATUSES = frozenset({"QUEUED", "PROCESSING"})
DOWNLOAD_ENGINE_AVAILABLE = True
_READY_LIFECYCLES = frozenset({"CURRENT", "REUSABLE", "PROTECTED"})
_FORBIDDEN_RESPONSE_KEYS = frozenset({
    "first_name", "last_name", "name", "email", "phone", "phone_number",
    "address", "address_line_1", "address_line_2", "street", "postal_code",
    "push_token", "advertising_id", "web_visitor_id", "storage_uri",
})


class Phase11ResultNotFoundError(LookupError):
    """A requested immutable search run does not exist."""


class Phase11ResultProjectionError(RuntimeError):
    """Persisted result metadata cannot be safely projected."""


def _decode_contracts(
    context_row: Mapping[str, Any], run: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    try:
        context = Phase11SavedCampaignContext.model_validate_json(
            str(context_row["campaign_context_json"])
        ).model_dump(mode="json")
        criteria = CanonicalBusinessTargetingCriteria.model_validate_json(
            str(run["targeting_criteria_json"])
        ).model_dump(mode="json")
        branches = json.loads(str(run["filter_branches_json"]))
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise Phase11ResultProjectionError(
            "Saved result criteria could not be reopened safely."
        ) from exc
    if not isinstance(branches, list) or not 1 <= len(branches) <= 49 or not all(
        isinstance(branch, dict) for branch in branches
    ):
        raise Phase11ResultProjectionError(
            "Saved result criteria could not be reopened safely."
        )
    return context, criteria, branches


def _product_summaries(
    database_path: Path, product_ids: list[str]
) -> list[dict[str, str]]:
    if not product_ids:
        return []
    placeholders = ",".join("?" for _ in product_ids)
    with get_connection(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT TRIM(product_id) AS product_id,
                   COALESCE(MIN(NULLIF(TRIM(product_name),'')), TRIM(product_id)) AS product_name,
                   COALESCE(MIN(NULLIF(TRIM(product_category),'')), '') AS product_category
            FROM campaign_sales
            WHERE TRIM(product_id) IN ({placeholders})
            GROUP BY TRIM(product_id)
            """,
            tuple(product_ids),
        ).fetchall()
    known = {str(row["product_id"]): dict(row) for row in rows}
    return [
        known.get(product_id, {
            "product_id": product_id,
            "product_name": product_id,
            "product_category": "",
        })
        for product_id in product_ids
    ]


def _targeting_summary(criteria: Mapping[str, Any]) -> list[str]:
    definitions = (
        ("genders", "Gender"), ("age_groups", "Age"),
        ("states", "State"), ("income_groups", "Income"),
        ("marital_statuses", "Marital status"),
        ("education_levels", "Education"),
        ("employment_statuses", "Employment status"),
        ("resident_statuses", "Resident status"),
        ("resident_types", "Resident type"),
        ("employment_types", "Employment type"),
    )
    summary = []
    for key, label in definitions:
        values = criteria.get(key)
        if isinstance(values, list) and values:
            summary.append(f"{label}: {', '.join(str(value) for value in values)}")
    family_min = criteria.get("family_member_count_min")
    family_max = criteria.get("family_member_count_max")
    if family_min is not None or family_max is not None:
        summary.append(
            f"Family size: {family_min if family_min is not None else 'Any'}–"
            f"{family_max if family_max is not None else 'Any'}"
        )
    if criteria.get("top_matching_percent") is not None:
        summary.append(f"Top matching: {criteria['top_matching_percent']}%")
    return summary or ["All available demographic groups"]


def _safe_message(run: Mapping[str, Any]) -> str:
    messages = {
        "QUEUED": "Saved and waiting to prepare targeting intelligence.",
        "PROCESSING": "Preparing potential-customer results. You can leave and return later.",
        "COMPLETED": "Potential-customer results are ready.",
        "BLOCKED": "This search is saved. Targeting intelligence preparation is not connected in this release yet.",
        "FAILED": "This search could not be completed. Review it before trying again.",
    }
    return messages[str(run["status"])]


def _recorded_currentness(
    snapshot: Mapping[str, Any] | None,
    generation: Mapping[str, Any] | None,
    demographic_source_current: bool,
) -> str:
    if snapshot is None:
        return "NOT_AVAILABLE"
    if (
        snapshot.get("currentness_state") == "CURRENT"
        and generation is not None
        and generation.get("generation_status") == "READY"
        and generation.get("lifecycle_state") in _READY_LIFECYCLES
        and demographic_source_current
    ):
        return "CURRENT"
    if snapshot.get("currentness_state") == "UNVERIFIED":
        return "UNVERIFIED"
    return "STALE"


def _demographic_source_is_current(
    database_path: Path, generation: Mapping[str, Any] | None
) -> bool:
    if generation is None:
        return False
    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT import_id, source_checksum
            FROM data_import_runs
            WHERE dataset_name='demographics' AND status='COMPLETED'
            ORDER BY import_id DESC
            LIMIT 1
            """
        ).fetchone()
    return bool(
        row is not None
        and int(row["import_id"]) == generation.get("demographic_import_id")
        and str(row["source_checksum"]) == generation.get(
            "demographic_source_checksum"
        )
    )


def _lineage(
    database_path: Path, run: Mapping[str, Any], repository: CampaignResultRegistryRepository
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    snapshot = None
    generation = None
    if run.get("result_snapshot_id") is not None:
        snapshot = repository.fetch_snapshot(int(run["result_snapshot_id"]))
    if run.get("generation_id") is not None:
        generation = Phase10IntelligenceRepository(database_path).fetch_generation(
            int(run["generation_id"])
        )
    return snapshot, generation


def _base_projection(
    database_path: Path, run: Mapping[str, Any], context: Mapping[str, Any],
    criteria: Mapping[str, Any], snapshot: Mapping[str, Any] | None,
    generation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    source = run.get("result_source")
    products = _product_summaries(database_path, list(context["product_ids"]))
    currentness = _recorded_currentness(
        snapshot,
        generation,
        _demographic_source_is_current(database_path, generation),
    )
    channel = str(run["delivery_channel"])
    return {
        "search_run_id": int(run["search_run_id"]),
        "campaign_name": str(run["campaign_name"]),
        "created_at": str(run["created_at"]),
        "completed_at": run.get("completed_at"),
        "status": str(run["status"]),
        "selected_products": products,
        "campaign_types": list(context["campaign_types"]),
        "campaign_categories": list(context["campaign_categories"]),
        "offer_types": list(context["offer_types"]),
        "delivery_channel": channel,
        "export_profile": str(run["export_profile"]),
        "delivery_profile_label": channel.replace("_", " ").title(),
        "match_strength": str(criteria["match_strength"]),
        "targeting_summary": _targeting_summary(criteria),
        "selected_count": run.get("selected_count"),
        "result_source": source,
        "result_source_label": RESULT_SOURCE_LABELS.get(
            str(source), "Not available until completion"
        ),
        "processing_seconds": run.get("processing_seconds"),
        "currentness": currentness,
        "download_eligible": bool(
            DOWNLOAD_ENGINE_AVAILABLE
            and run.get("status") == "COMPLETED"
            and currentness == "CURRENT"
        ),
        "safe_message": _safe_message(run),
    }


def _load_run_projection(
    database_path: Path, run: Mapping[str, Any],
    repository: CampaignResultRegistryRepository,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any] | None, dict[str, Any] | None]:
    context_row = CampaignTargetingContextRepository(database_path).fetch_context(
        int(run["targeting_context_id"])
    )
    if context_row is None:
        raise Phase11ResultProjectionError("Saved campaign context is unavailable.")
    context, criteria, branches = _decode_contracts(context_row, run)
    snapshot, generation = _lineage(database_path, run, repository)
    return context, criteria, branches, snapshot, generation


def list_result_history(
    database_path: str | Path, *, limit: int = 20,
    before_search_run_id: int | None = None,
) -> list[dict[str, Any]]:
    path = Path(database_path)
    repository = CampaignResultRegistryRepository(path)
    runs = repository.list_search_runs(
        limit=limit, before_search_run_id=before_search_run_id
    )
    result = []
    for run in runs:
        context, criteria, _branches, snapshot, generation = _load_run_projection(
            path, run, repository
        )
        result.append(
            _base_projection(path, run, context, criteria, snapshot, generation)
        )
    _assert_no_forbidden_keys(result)
    return result


def _score_summary(database_path: Path, scoring_run_id: Any) -> dict[str, Any] | None:
    if not isinstance(scoring_run_id, int):
        return None
    with get_connection(database_path) as connection:
        row = connection.execute(
            """SELECT scored_person_count,score_min,score_max,score_mean
               FROM scoring_runs WHERE scoring_run_id=? AND status='COMPLETED'""",
            (scoring_run_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "scope": "Scored potential-customer universe",
        "population_count": int(row["scored_person_count"]),
        "minimum": float(row["score_min"]),
        "maximum": float(row["score_max"]),
        "mean": float(row["score_mean"]),
    }


def _demographic_summary(criteria: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "genders", "age_groups", "states", "income_groups",
        "marital_statuses", "education_levels", "employment_statuses",
        "resident_statuses", "resident_types", "employment_types",
        "family_member_count_min", "family_member_count_max",
        "top_matching_percent",
    )
    return {key: criteria[key] for key in keys}


def get_result_detail(
    database_path: str | Path, search_run_id: int, *,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(database_path)
    repository = CampaignResultRegistryRepository(path)
    run = repository.fetch_search_run(search_run_id)
    if run is None:
        raise Phase11ResultNotFoundError("The saved search was not found.")
    context, criteria, branches, snapshot, generation = _load_run_projection(
        path, run, repository
    )
    base = _base_projection(path, run, context, criteria, snapshot, generation)
    currentness = base["currentness"]
    if snapshot is not None and generation is not None:
        validation = validate_result_snapshot(
            snapshot, run, generation,
            str(snapshot["result_cache_key_sha256"]),
            project_root=project_root,
        )
        if not validation.is_valid:
            currentness = "STALE"
            base["currentness"] = currentness
            base["download_eligible"] = False
    source = run.get("result_source")
    provenance = None
    if snapshot is not None and generation is not None:
        provenance = {
            "result_snapshot_id": int(snapshot["result_snapshot_id"]),
            "membership_contract_version": str(
                snapshot["result_membership_contract_version"]
            ),
            "resolved_count": int(snapshot["resolved_count"]),
            "snapshot_sha256": str(snapshot["snapshot_sha256"]),
            "created_at": str(snapshot["created_at"]),
            "last_verified_at": str(snapshot["last_verified_at"]),
            "generation_id": int(generation["generation_id"]),
            "scoring_run_id": int(generation["scoring_run_id"]),
            "model_run_id": int(generation["model_run_id"]),
            "analysis_run_id": int(generation["analysis_run_id"]),
            "currentness": currentness,
        }
    detail = base | {
        "description": run.get("description"),
        "planned_launch_date": run.get("planned_launch_date"),
        "campaign_context": context,
        "targeting_criteria": criteria,
        "filter_branches": branches,
        "selection": {
            "mode": str(run["selection_mode"]),
            "target_count": run.get("target_count"),
            "resolved_count": run.get("selected_count"),
        },
        "result_source_explanation": RESULT_SOURCE_LABELS.get(
            str(source), "Result source will be available after completion."
        ),
        "score_summary": _score_summary(path, run.get("scoring_run_id")),
        "demographic_summary": _demographic_summary(criteria),
        "snapshot_provenance": provenance,
        "technical_details": {
            "targeting_context_id": int(run["targeting_context_id"]),
            "modeling_context_sha256": str(run["modeling_context_sha256"]),
            "targeting_criteria_sha256": str(run["targeting_criteria_sha256"]),
            "filter_branches_sha256": str(run["filter_branches_sha256"]),
            "generation_id": run.get("generation_id"),
            "analysis_run_id": run.get("analysis_run_id"),
            "model_run_id": run.get("model_run_id"),
            "scoring_run_id": run.get("scoring_run_id"),
            "result_snapshot_id": run.get("result_snapshot_id"),
        },
    }
    _assert_no_forbidden_keys(detail)
    return detail


def _assert_no_forbidden_keys(value: Any) -> None:
    if isinstance(value, dict):
        if _FORBIDDEN_RESPONSE_KEYS.intersection(
            str(key).strip().lower() for key in value
        ):
            raise Phase11ResultProjectionError(
                "Result projection contains prohibited fields."
            )
        for nested in value.values():
            _assert_no_forbidden_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_keys(nested)


__all__ = (
    "ACTIVE_SEARCH_STATUSES",
    "DOWNLOAD_ENGINE_AVAILABLE",
    "Phase11ResultNotFoundError",
    "Phase11ResultProjectionError",
    "RESULT_SOURCE_LABELS",
    "get_result_detail",
    "list_result_history",
)
