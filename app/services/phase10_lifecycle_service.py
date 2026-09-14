"""Non-destructive Phase 10 intelligence lifecycle classification and reporting."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.ml.evaluation import EVALUATION_CONTRACT_VERSION
from app.ml.feature_contract import FEATURE_CONTRACT_SHA256, FEATURE_CONTRACT_VERSION
from app.ml.model_roles import MODEL_ROLE_POLICY_VERSION
from app.repositories.campaign_targeting_context_repository import (
    CampaignTargetingContextRepository,
)
from app.repositories.phase10_intelligence_repository import (
    LIFECYCLE_STATES,
    Phase10IntelligenceRepository,
)
from app.repositories.prospect_scoring_repository import ProspectScoringRepository
from app.schemas.phase10_intelligence import (
    PHASE10_AUTOMATED_TRAINING_POLICY_VERSION,
    PHASE10_COMPATIBILITY_CONTRACT_VERSION,
    PHASE10_HISTORICAL_WINDOW_POLICY_VERSION,
    PHASE10_INTELLIGENCE_GENERATION_CONTRACT_VERSION,
    PHASE10_LIFECYCLE_POLICY_VERSION,
    PHASE10_MULTI_PRODUCT_POSITIVE_POLICY_VERSION,
    PHASE10_TRAINING_ELIGIBILITY_POLICY_VERSION,
    Phase10LifecycleReport,
)
from app.services.audience_preparation_service import (
    AUDIENCE_ANALYTICS_CONTRACT_VERSION,
    DEFAULT_RANK_CONTRACT_VERSION,
)
from app.services.historical_source_provenance_service import (
    resolve_current_historical_source_provenance,
)


PROTECTION_REASON_ORDER = (
    "SAVED_AUDIENCE",
    "PHASE9_SAVED_TARGET_GROUP",
    "CAMPAIGN",
    "FINALIZED_CAMPAIGN",
    "EXPORT_AUDIT_HISTORY",
    "ACTIVE_ORCHESTRATION",
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _current_source_identity(database_path: str | Path) -> dict[str, Any]:
    historical = resolve_current_historical_source_provenance(database_path)
    demographic = ProspectScoringRepository(
        database_path
    ).fetch_completed_demographic_import_provenance()
    return {
        "customer_import_id": historical.customer_import_id,
        "customer_source_checksum": historical.customer_source_checksum,
        "campaign_sales_import_id": historical.campaign_sales_import_id,
        "campaign_sales_source_checksum": historical.campaign_sales_source_checksum,
        "demographic_import_id": demographic.demographic_import_id,
        "demographic_source_checksum": demographic.demographic_source_checksum,
    }


def _uses_current_sources_and_policies(
    generation: dict[str, Any],
    current_source: dict[str, Any],
) -> bool:
    expected = {
        **current_source,
        "intelligence_generation_contract_version": (
            PHASE10_INTELLIGENCE_GENERATION_CONTRACT_VERSION
        ),
        "compatibility_contract_version": PHASE10_COMPATIBILITY_CONTRACT_VERSION,
        "historical_window_policy_version": PHASE10_HISTORICAL_WINDOW_POLICY_VERSION,
        "multi_product_positive_policy_version": (
            PHASE10_MULTI_PRODUCT_POSITIVE_POLICY_VERSION
        ),
        "training_eligibility_policy_version": (
            PHASE10_TRAINING_ELIGIBILITY_POLICY_VERSION
        ),
        "automated_training_policy_version": (
            PHASE10_AUTOMATED_TRAINING_POLICY_VERSION
        ),
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "feature_contract_sha256": FEATURE_CONTRACT_SHA256,
        "model_role_policy_version": MODEL_ROLE_POLICY_VERSION,
        "evaluation_contract_version": EVALUATION_CONTRACT_VERSION,
        "rank_contract_version": DEFAULT_RANK_CONTRACT_VERSION,
        "analytics_contract_version": AUDIENCE_ANALYTICS_CONTRACT_VERSION,
        "lifecycle_policy_version": PHASE10_LIFECYCLE_POLICY_VERSION,
    }
    return all(generation.get(field) == value for field, value in expected.items())


def _protection_reasons(reference_counts: dict[str, int]) -> list[str]:
    reasons: list[str] = []
    if reference_counts["saved_audience_count"]:
        reasons.append("SAVED_AUDIENCE")
    if reference_counts["saved_target_group_count"]:
        reasons.append("PHASE9_SAVED_TARGET_GROUP")
    if reference_counts["campaign_count"]:
        reasons.append("CAMPAIGN")
    if reference_counts["finalized_campaign_count"]:
        reasons.append("FINALIZED_CAMPAIGN")
    if reference_counts["export_event_count"]:
        reasons.append("EXPORT_AUDIT_HISTORY")
    if reference_counts["orchestration_count"]:
        reasons.append("ACTIVE_ORCHESTRATION")
    return [reason for reason in PROTECTION_REASON_ORDER if reason in reasons]


def touch_phase10_usage_for_context(
    database_path: str | Path,
    *,
    targeting_context_id: int,
    used_at: str | None = None,
) -> bool:
    """Touch an exact READY Phase 10 binding; leave Phase 9-only sources unchanged."""

    repository = Phase10IntelligenceRepository(database_path)
    binding = repository.fetch_context_binding(targeting_context_id)
    if binding is None or binding["binding_status"] != "READY":
        return False
    generation_id = binding.get("generation_id")
    if generation_id is None:
        return False
    generation = repository.fetch_generation(int(generation_id))
    context = CampaignTargetingContextRepository(database_path).fetch_context(
        targeting_context_id
    )
    if (
        generation is None
        or context is None
        or context.get("source_scoring_run_id") is None
        or int(context["source_scoring_run_id"]) != int(generation["scoring_run_id"])
    ):
        return False
    timestamp = _timestamp() if used_at is None else used_at
    repository.touch_generation_usage(int(generation_id), used_at=timestamp)
    repository.touch_context_binding(targeting_context_id, used_at=timestamp)
    return True


def reconcile_phase10_lifecycle(
    database_path: str | Path,
    *,
    generated_at: str | None = None,
    _include_score_footprint: bool = True,
) -> dict[str, Any]:
    """Classify every generation and return a strict no-PII lifecycle report."""

    timestamp = _timestamp() if generated_at is None else generated_at
    repository = Phase10IntelligenceRepository(database_path)
    generations = repository.list_all_generations()
    if not generations:
        empty_counts = {state: 0 for state in sorted(LIFECYCLE_STATES)}
        return Phase10LifecycleReport(
            lifecycle_policy_version=PHASE10_LIFECYCLE_POLICY_VERSION,
            generated_at=timestamp,
            total_generation_count=0,
            counts_by_state=empty_counts,
            score_row_footprint_count=0,
            reusable_contexts={},
            retirement_eligible_generation_ids=[],
            generations=[],
        ).model_dump(mode="json")

    current_source = _current_source_identity(database_path)
    source_current: dict[int, bool] = {}
    for generation in generations:
        generation_id = int(generation["generation_id"])
        try:
            repository.verify_generation_record(generation_id)
            valid = True
        except Exception:
            valid = False
        source_current[generation_id] = valid and _uses_current_sources_and_policies(
            generation, current_source
        )

    lifecycle_updates: dict[int, str] = {}
    report_rows: list[dict[str, Any]] = []
    reusable_contexts: dict[int, list[int]] = {}
    retirement_ids: list[int] = []

    for generation in generations:
        generation_id = int(generation["generation_id"])
        references = repository.fetch_generation_reference_counts(generation_id)
        context_ids = repository.fetch_generation_context_ids(generation_id)
        has_newer = any(
            int(candidate["generation_id"]) > generation_id
            and candidate["modeling_context_sha256"]
            == generation["modeling_context_sha256"]
            for candidate in generations
        )
        if not source_current[generation_id]:
            base_state = "STALE"
        elif has_newer:
            base_state = "SUPERSEDED"
        elif references["ready_context_binding_count"]:
            base_state = "CURRENT"
        else:
            base_state = "REUSABLE"

        protection_reasons = _protection_reasons(references)
        if protection_reasons:
            lifecycle_state = "PROTECTED"
        elif (
            base_state in {"STALE", "SUPERSEDED"}
            and references["context_binding_count"] == 0
        ):
            lifecycle_state = "RETIREMENT_ELIGIBLE"
        else:
            lifecycle_state = base_state

        lifecycle_updates[generation_id] = lifecycle_state
        if lifecycle_state == "RETIREMENT_ELIGIBLE":
            retirement_ids.append(generation_id)
        if source_current[generation_id] and base_state == "CURRENT" and context_ids:
            reusable_contexts[generation_id] = context_ids
        report_rows.append(
            {
                "generation_id": generation_id,
                "lifecycle_state": lifecycle_state,
                "classification_before_protection": base_state,
                "source_current": source_current[generation_id],
                "score_row_count": (
                    repository.count_generation_score_rows(generation_id)
                    if _include_score_footprint
                    else 0
                ),
                "protection_reasons": protection_reasons,
                "reusable_targeting_context_ids": context_ids,
                "last_verified_at": timestamp,
                "last_used_at": str(generation["last_used_at"]),
            }
        )

    repository.apply_generation_lifecycle_states(
        lifecycle_updates,
        verified_at=timestamp,
    )
    counts = {state: 0 for state in sorted(LIFECYCLE_STATES)}
    for lifecycle_state in lifecycle_updates.values():
        counts[lifecycle_state] += 1
    return Phase10LifecycleReport(
        lifecycle_policy_version=PHASE10_LIFECYCLE_POLICY_VERSION,
        generated_at=timestamp,
        total_generation_count=len(generations),
        counts_by_state=counts,
        score_row_footprint_count=(
            repository.count_registered_score_footprint()
            if _include_score_footprint
            else 0
        ),
        reusable_contexts=reusable_contexts,
        retirement_eligible_generation_ids=retirement_ids,
        generations=report_rows,
    ).model_dump(mode="json")


def classify_phase10_lifecycle(
    database_path: str | Path,
    *,
    classified_at: str | None = None,
) -> int:
    """Apply lifecycle states without scanning the full score-row footprint."""

    report = reconcile_phase10_lifecycle(
        database_path,
        generated_at=classified_at,
        _include_score_footprint=False,
    )
    return int(report["total_generation_count"])


__all__ = (
    "PROTECTION_REASON_ORDER",
    "classify_phase10_lifecycle",
    "reconcile_phase10_lifecycle",
    "touch_phase10_usage_for_context",
)
