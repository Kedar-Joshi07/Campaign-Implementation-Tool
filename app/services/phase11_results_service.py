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
from app.services.phase11_run_lifecycle_service import (
    project_run_issue,
    project_run_progress,
)
from app.services.targeting_option_catalog_service import get_product_catalog_entries
from app.services.source_currentness_service import result_lineage_is_current


RESULT_SOURCE_LABELS = {
    "EXACT_RESULT_REUSE": "Reused previous exact result",
    "INTELLIGENCE_REUSE": "Reused existing targeting intelligence",
    "NEW_INTELLIGENCE_BUILD": "Prepared new targeting intelligence",
}
PROPENSITY_BUCKET_LABELS = {
    "0.90": "90% to 100%",
    "0.80": "80% to <90%",
    "0.70": "70% to <80%",
    "0.60": "60% to <70%",
    "0.50": "50% to <60%",
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
    database_path: Path,
    product_ids: list[str],
    *,
    catalog_version: str | None = None,
) -> list[dict[str, str]]:
    if not product_ids:
        return []
    catalog = get_product_catalog_entries(
        database_path, product_ids, catalog_version=catalog_version
    )
    missing = [product_id for product_id in product_ids if product_id not in catalog]
    if not missing:
        return [catalog[product_id] for product_id in product_ids]
    placeholders = ",".join("?" for _ in missing)
    with get_connection(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT product_id AS product_id,
                   COALESCE(MIN(NULLIF(product_name,'')), product_id) AS product_name,
                   COALESCE(MIN(NULLIF(product_category,'')), '') AS product_category
            FROM campaign_sales
            WHERE product_id IN ({placeholders})
            GROUP BY product_id
            """,
            tuple(missing),
        ).fetchall()
    known = catalog | {str(row["product_id"]): dict(row) for row in rows}
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
        "BLOCKED": "Your search is saved but cannot proceed with the current targeting intelligence.",
        "FAILED": "This search could not be completed. Review it before trying again.",
    }
    return messages[str(run["status"])]


def _selection_projection(
    run: Mapping[str, Any], criteria: Mapping[str, Any]
) -> dict[str, str]:
    if str(run.get("selection_contract_version") or "1") == "2":
        bucket = str(run.get("propensity_bucket") or "")
        label = PROPENSITY_BUCKET_LABELS.get(bucket)
        if label is None:
            raise Phase11ResultProjectionError(
                "Saved calibrated selection could not be reopened safely."
            )
        return {
            "selection_label": "Purchase Propensity",
            "selection_value": label,
            "selection_semantics": "CALIBRATED_PURCHASE_PROBABILITY",
        }
    return {
        "selection_label": "Match Strength",
        "selection_value": str(criteria["match_strength"]),
        "selection_semantics": "LEGACY_RAW_SCORE",
    }


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


def _result_lineage_is_current(
    database_path: Path,
    run: Mapping[str, Any],
    generation: Mapping[str, Any] | None,
) -> bool:
    calibration_id = run.get("calibration_artifact_id")
    return result_lineage_is_current(
        database_path,
        generation,
        selection_contract_version=str(run.get("selection_contract_version") or "1"),
        calibration_artifact_id=(
            int(calibration_id) if calibration_id is not None else None
        ),
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
    repository: CampaignResultRegistryRepository,
    stage_history: Mapping[tuple[str, str], list[float]] | None = None,
    product_catalog: Mapping[
        tuple[str | None, str], dict[str, str]
    ] | None = None,
    demographic_source_current: bool | None = None,
    runtime_override: Mapping[str, Any] | None = None,
    attempt_override: Mapping[str, Any] | None = None,
    queue_positions: Mapping[int, int] | None = None,
) -> dict[str, Any]:
    source = run.get("result_source")
    product_ids = list(context["product_ids"])
    products = (
        [
            product_catalog.get(
                (run.get("catalog_version"), product_id),
                product_catalog.get((None, product_id), {
                    "product_id": product_id, "product_name": product_id,
                    "product_category": "",
                }),
            )
            for product_id in product_ids
        ]
        if product_catalog is not None
        else _product_summaries(
            database_path,
            product_ids,
            catalog_version=run.get("catalog_version"),
        )
    )
    currentness = _recorded_currentness(
        snapshot,
        generation,
        _result_lineage_is_current(database_path, run, generation)
        if demographic_source_current is None else demographic_source_current,
    )
    channel = str(run["delivery_channel"])
    runtime = runtime_override or repository.fetch_search_runtime(int(run["search_run_id"]))
    attempt = attempt_override or repository.fetch_current_attempt(int(run["search_run_id"]))
    issue = project_run_issue(runtime)
    selection_projection = _selection_projection(run, criteria)
    targeting_summary = _targeting_summary(criteria)
    if selection_projection["selection_semantics"] == "CALIBRATED_PURCHASE_PROBABILITY":
        targeting_summary = [
            f"Purchase propensity: {selection_projection['selection_value']}",
            *targeting_summary,
        ]
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
        **selection_projection,
        "targeting_summary": targeting_summary,
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
        "progress": project_run_progress(
            run, runtime,
            attempt=attempt,
            stage_duration_samples=(stage_history or {}).get((
                str(runtime["workload_class"]), str(runtime["stage_code"])
            )) if runtime else None,
        ),
        "issue": issue,
        "retry_eligible": bool(issue and issue.get("retryable")),
        "attempt_number": int(run.get("current_attempt_number") or 1),
        "queue_position": (
            queue_positions.get(int(run["search_run_id"]))
            if queue_positions is not None and run["status"] == "QUEUED"
            else repository.queue_position(int(run["search_run_id"]))
            if run["status"] == "QUEUED"
            else None
        ),
        "propensity_bucket": run.get("propensity_bucket"),
        "selection_contract_version": str(run.get("selection_contract_version") or "1"),
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
    stage_history = repository.stage_duration_history()
    if not runs:
        return []
    context_ids = [int(run["targeting_context_id"]) for run in runs]
    snapshot_ids = [int(run["result_snapshot_id"]) for run in runs if run.get("result_snapshot_id") is not None]
    generation_ids = [int(run["generation_id"]) for run in runs if run.get("generation_id") is not None]
    run_ids = [int(run["search_run_id"]) for run in runs]
    queue_positions = repository.queue_positions(
        [int(run["search_run_id"]) for run in runs if run["status"] == "QUEUED"]
    )
    def bulk(table: str, key: str, identifiers: list[int]) -> dict[int, dict[str, Any]]:
        if not identifiers:
            return {}
        marks = ",".join("?" for _ in identifiers)
        with get_connection(path) as connection:
            rows = connection.execute(
                f"SELECT * FROM {table} WHERE {key} IN ({marks})", tuple(identifiers)
            ).fetchall()
        return {int(row[key]): dict(row) for row in rows}
    contexts = bulk("campaign_targeting_contexts", "targeting_context_id", context_ids)
    snapshots = bulk("campaign_result_snapshots", "result_snapshot_id", snapshot_ids)
    generations = bulk("phase10_intelligence_generations", "generation_id", generation_ids)
    runtimes = bulk("campaign_search_run_runtime", "search_run_id", run_ids)
    attempts = repository.fetch_current_attempts(run_ids)
    decoded: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]] = []
    all_product_ids: set[str] = set()
    for run in runs:
        context_row = contexts.get(int(run["targeting_context_id"]))
        if context_row is None:
            raise Phase11ResultProjectionError("Saved campaign context is unavailable.")
        context, criteria, branches = _decode_contracts(context_row, run)
        all_product_ids.update(context["product_ids"])
        decoded.append((run, context, criteria, branches))
    product_rows = _product_summaries(path, sorted(all_product_ids))
    product_catalog: dict[tuple[str | None, str], dict[str, str]] = {
        (None, row["product_id"]): row for row in product_rows
    }
    catalog_versions = sorted({
        str(run["catalog_version"])
        for run in runs if run.get("catalog_version") is not None
    })
    if catalog_versions and all_product_ids:
        version_marks = ",".join("?" for _ in catalog_versions)
        product_marks = ",".join("?" for _ in all_product_ids)
        with get_connection(path) as connection:
            historical_products = connection.execute(
                f"""SELECT catalog_version,product_id,product_name,product_category
                    FROM targeting_product_catalog
                    WHERE catalog_version IN ({version_marks})
                      AND product_id IN ({product_marks})""",
                (*catalog_versions, *sorted(all_product_ids)),
            ).fetchall()
        product_catalog.update({
            (str(row["catalog_version"]), str(row["product_id"])): {
                "product_id": str(row["product_id"]),
                "product_name": str(row["product_name"]),
                "product_category": str(row["product_category"]),
            }
            for row in historical_products
        })
    result = []
    for run in runs:
        _saved_run, context, criteria, _branches = next(
            item for item in decoded if item[0]["search_run_id"] == run["search_run_id"]
        )
        snapshot = snapshots.get(int(run["result_snapshot_id"])) if run.get("result_snapshot_id") is not None else None
        generation = generations.get(int(run["generation_id"])) if run.get("generation_id") is not None else None
        demographic_current = _result_lineage_is_current(path, run, generation)
        result.append(
            _base_projection(
                path, run, context, criteria, snapshot, generation, repository,
                stage_history,
                product_catalog, demographic_current,
                runtimes.get(int(run["search_run_id"])),
                attempts.get(int(run["search_run_id"])),
                queue_positions,
            )
        )
    _assert_no_forbidden_keys(result)
    return result


def _score_summary(
    database_path: Path, run: Mapping[str, Any]
) -> dict[str, Any] | None:
    if str(run.get("selection_contract_version") or "1") == "2":
        calibration_id = run.get("calibration_artifact_id")
        if isinstance(calibration_id, bool) or not isinstance(calibration_id, int):
            return None
        with get_connection(database_path) as connection:
            row = connection.execute(
                """SELECT COUNT(*) AS population_count,
                          MIN(scores.calibrated_probability) AS probability_min,
                          MAX(scores.calibrated_probability) AS probability_max,
                          AVG(scores.calibrated_probability) AS probability_mean
                   FROM calibrated_propensity_scores AS scores
                   JOIN score_calibration_artifacts AS artifact
                     ON artifact.calibration_artifact_id=scores.calibration_artifact_id
                   WHERE scores.calibration_artifact_id=?
                     AND artifact.status='PROMOTED'""",
                (calibration_id,),
            ).fetchone()
        if row is None or int(row["population_count"]) == 0:
            return None
        return {
            "scope": "Calibrated potential-customer universe",
            "metric_label": "Calibrated purchase probability",
            "semantics": "CALIBRATED_PURCHASE_PROBABILITY",
            "probability_bucket": str(run["propensity_bucket"]),
            "population_count": int(row["population_count"]),
            "minimum": float(row["probability_min"]),
            "maximum": float(row["probability_max"]),
            "mean": float(row["probability_mean"]),
        }

    scoring_run_id = run.get("scoring_run_id")
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
    base = _base_projection(
        path, run, context, criteria, snapshot, generation, repository,
        repository.stage_duration_history(),
    )
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
        "score_summary": _score_summary(path, run),
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
    "PROPENSITY_BUCKET_LABELS",
    "get_result_detail",
    "list_result_history",
)
