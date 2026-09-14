"""Durable, idempotent Phase 10 reuse-or-build parent orchestration."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.ml.evaluation import EVALUATION_CONTRACT_VERSION
from app.ml.feature_contract import FEATURE_CONTRACT_SHA256, FEATURE_CONTRACT_VERSION
from app.ml.model_roles import MODEL_ROLE_POLICY_VERSION
from app.repositories.campaign_targeting_context_repository import (
    CampaignTargetingContextRepository,
)
from app.repositories.phase10_intelligence_repository import (
    Phase10IntelligenceRepository,
)
from app.repositories.prospect_scoring_repository import ProspectScoringRepository
from app.repositories.scoring_repository import ScoringRepository
from app.schemas.phase10_intelligence import (
    PHASE10_AUTOMATED_TRAINING_POLICY_VERSION,
    PHASE10_AUTOMATED_TRAINING_RANDOM_SEED,
    PHASE10_AUTOMATED_TRAINING_RUN_ELKAN_CHALLENGER,
    PHASE10_AUTOMATED_TRAINING_VALIDATION_FRACTION,
    PHASE10_COMPATIBILITY_CONTRACT_VERSION,
    PHASE10_HISTORICAL_WINDOW_POLICY_VERSION,
    PHASE10_INTELLIGENCE_GENERATION_CONTRACT_VERSION,
    PHASE10_LIFECYCLE_POLICY_VERSION,
    PHASE10_MULTI_PRODUCT_POSITIVE_POLICY_VERSION,
    PHASE10_ORCHESTRATION_CONTRACT_VERSION,
    PHASE10_TRAINING_ELIGIBILITY_POLICY_VERSION,
    ScoreSemanticsContract,
)
from app.services.audience_preparation_service import (
    AUDIENCE_ANALYTICS_CONTRACT_VERSION,
    DEFAULT_PREPARATION_SCAN_CHUNK_SIZE,
    DEFAULT_RANK_CONTRACT_VERSION,
)
from app.services.historical_source_provenance_service import (
    resolve_current_historical_source_provenance,
)
from app.services.model_training_service import DEFAULT_ARTIFACT_ROOT
from app.services.phase10_context_identity_service import (
    ModelingContextIdentity,
    derive_modeling_context_from_campaign_context,
    resolve_phase10_historical_filters,
)
from app.services.phase10_historical_resolution_service import (
    HistoricalAnalysisResolution,
    find_reusable_phase10_historical_analysis,
    resolve_or_create_phase10_historical_analysis,
)
from app.services.phase10_model_resolution_service import (
    Phase10ModelResolution,
    find_reusable_phase10_model,
    resolve_or_train_phase10_model,
)
from app.services.phase10_lifecycle_service import classify_phase10_lifecycle
from app.services.phase10_scoring_resolution_service import (
    Phase10ScoringValidationError,
    finalize_phase10_ready_context,
    get_phase10_rank_analytics_readiness,
    resolve_or_build_phase10_scoring_rank,
    validate_phase10_scoring_candidate,
)
from app.services.prospect_scoring_service import DEFAULT_SCORING_CHUNK_SIZE


logger = logging.getLogger(__name__)

ReuseDecision = Literal["REUSE", "BUILD"]
OrchestrationSubmitter = Callable[[str | Path, int, str | Path | None], Any]

TECHNICAL_STAGES = (
    "CHECKING_COMPATIBILITY",
    "RESOLVING_HISTORICAL_CONTEXT",
    "CHECKING_TRAINING_ELIGIBILITY",
    "RESOLVING_MODEL",
    "VALIDATING_MODEL",
    "RESOLVING_SCORING",
    "SCORING_POTENTIAL_CUSTOMERS",
    "PREPARING_TARGET_GROUP",
    "VERIFYING_FINAL_CURRENTNESS",
    "READY",
)

BUSINESS_LABELS = {
    "CHECKING_COMPATIBILITY": "Checking available targeting intelligence",
    "RESOLVING_HISTORICAL_CONTEXT": "Checking verified past campaign history",
    "CHECKING_TRAINING_ELIGIBILITY": "Confirming enough past examples",
    "RESOLVING_MODEL": "Preparing targeting intelligence",
    "VALIDATING_MODEL": "Verifying targeting quality",
    "RESOLVING_SCORING": "Checking potential-customer coverage",
    "SCORING_POTENTIAL_CUSTOMERS": "Matching the full potential-customer universe",
    "PREPARING_TARGET_GROUP": "Preparing Target Group insights",
    "VERIFYING_FINAL_CURRENTNESS": "Final verification",
    "READY": "Targeting intelligence ready",
}

SAFE_FAILURE_MESSAGE = (
    "Targeting intelligence could not be prepared. Please retry this step."
)


class Phase10OrchestrationError(RuntimeError):
    """Raised when the durable parent workflow cannot be safely resolved."""


@dataclass(frozen=True)
class Phase10RequestedIntelligence:
    modeling_context: ModelingContextIdentity
    intelligence_key_sha256: str


@dataclass(frozen=True)
class Phase10OrchestrationStart:
    orchestration: dict[str, Any]
    created: bool
    already_ready: bool
    submitted: bool


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _load_modeling_context(
    database_path: str | Path,
    targeting_context_id: int,
) -> ModelingContextIdentity:
    row = CampaignTargetingContextRepository(database_path).fetch_context(
        targeting_context_id
    )
    if row is None:
        raise Phase10OrchestrationError("Campaign Context was not found.")
    raw = row.get("campaign_context_json")
    if not isinstance(raw, str):
        raise Phase10OrchestrationError("Campaign Context is invalid.")
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise Phase10OrchestrationError("Campaign Context is invalid.") from exc
    if not isinstance(payload, dict):
        raise Phase10OrchestrationError("Campaign Context is invalid.")
    stored_sha = row.get("campaign_context_sha256")
    if not isinstance(stored_sha, str) or hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest() != stored_sha.lower():
        raise Phase10OrchestrationError("Campaign Context identity is invalid.")
    return derive_modeling_context_from_campaign_context(payload)


def build_phase10_requested_intelligence(
    database_path: str | Path,
    targeting_context_id: int,
) -> Phase10RequestedIntelligence:
    """Build the pre-work exact key from context, sources, and frozen policies."""

    identity = _load_modeling_context(database_path, targeting_context_id)
    filters = resolve_phase10_historical_filters(database_path, identity)
    historical_source = resolve_current_historical_source_provenance(database_path)
    demographic = ProspectScoringRepository(
        database_path
    ).fetch_completed_demographic_import_provenance()
    payload = {
        "orchestration_contract_version": PHASE10_ORCHESTRATION_CONTRACT_VERSION,
        "intelligence_generation_contract_version": (
            PHASE10_INTELLIGENCE_GENERATION_CONTRACT_VERSION
        ),
        "compatibility_contract_version": PHASE10_COMPATIBILITY_CONTRACT_VERSION,
        "modeling_context": identity.payload,
        "modeling_context_sha256": identity.modeling_context_sha256,
        "resolved_historical_filters": filters.model_dump(mode="json"),
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
        "automated_training_random_seed": PHASE10_AUTOMATED_TRAINING_RANDOM_SEED,
        "automated_training_validation_fraction": (
            PHASE10_AUTOMATED_TRAINING_VALIDATION_FRACTION
        ),
        "automated_training_run_elkan_challenger": (
            PHASE10_AUTOMATED_TRAINING_RUN_ELKAN_CHALLENGER
        ),
        "customer_import_id": historical_source.customer_import_id,
        "customer_source_checksum": historical_source.customer_source_checksum,
        "campaign_sales_import_id": historical_source.campaign_sales_import_id,
        "campaign_sales_source_checksum": (
            historical_source.campaign_sales_source_checksum
        ),
        "demographic_import_id": demographic.demographic_import_id,
        "demographic_source_checksum": demographic.demographic_source_checksum,
        "demographic_snapshot_count": demographic.demographic_snapshot_count,
        "demographic_min_person_id": demographic.demographic_min_person_id,
        "demographic_max_person_id": demographic.demographic_max_person_id,
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "feature_contract_sha256": FEATURE_CONTRACT_SHA256,
        "model_role_policy_version": MODEL_ROLE_POLICY_VERSION,
        "evaluation_contract_version": EVALUATION_CONTRACT_VERSION,
        "score_semantics": ScoreSemanticsContract().model_dump(mode="json"),
        "rank_contract_version": DEFAULT_RANK_CONTRACT_VERSION,
        "analytics_contract_version": AUDIENCE_ANALYTICS_CONTRACT_VERSION,
        "lifecycle_policy_version": PHASE10_LIFECYCLE_POLICY_VERSION,
    }
    return Phase10RequestedIntelligence(
        modeling_context=identity,
        intelligence_key_sha256=_json_sha256(payload),
    )


def _all_build_plan() -> dict[str, ReuseDecision]:
    return {
        "analysis": "BUILD",
        "model": "BUILD",
        "scoring": "BUILD",
        "rank": "BUILD",
    }


def build_phase10_reuse_plan(
    database_path: str | Path,
    requested: Phase10RequestedIntelligence,
    *,
    project_root: str | Path | None = None,
) -> dict[str, ReuseDecision]:
    """Inspect exact durable assets without starting any analytical work."""

    historical = find_reusable_phase10_historical_analysis(
        database_path,
        requested.modeling_context,
    )
    if historical is None:
        return _all_build_plan()
    plan = _all_build_plan()
    plan["analysis"] = "REUSE"
    if historical.status != "READY":
        return plan
    model = find_reusable_phase10_model(
        database_path,
        requested.modeling_context,
        historical,
        project_root=project_root,
    )
    if model is None or model.status != "READY":
        return plan
    plan["model"] = "REUSE"
    for row in ScoringRepository(database_path).list_model_candidates(
        int(model.model_run_id)
    ):
        try:
            validate_phase10_scoring_candidate(
                database_path,
                int(row["scoring_run_id"]),
                model,
                project_root=project_root,
            )
        except Phase10ScoringValidationError:
            continue
        plan["scoring"] = "REUSE"
        readiness = get_phase10_rank_analytics_readiness(
            database_path,
            int(row["scoring_run_id"]),
        )
        if readiness.ready:
            plan["rank"] = "REUSE"
        break
    return plan


def _default_submitter(
    database_path: str | Path,
    orchestration_id: int,
    project_root: str | Path | None,
):
    from app.jobs.executor import submit_phase10_orchestration_job

    return submit_phase10_orchestration_job(
        database_path,
        orchestration_id,
        project_root=project_root,
    )


def prepare_phase10_orchestration(
    database_path: str | Path,
    targeting_context_id: int,
    *,
    project_root: str | Path | None = None,
    submitter: OrchestrationSubmitter = _default_submitter,
) -> Phase10OrchestrationStart:
    """Idempotently return READY/active work or persist and submit one parent."""

    requested = build_phase10_requested_intelligence(
        database_path,
        targeting_context_id,
    )
    # Classification is deliberately metadata-only here; the full score-row
    # footprint scan belongs to the explicit lifecycle report.
    classify_phase10_lifecycle(database_path)
    repository = Phase10IntelligenceRepository(database_path)
    active = repository.find_active_orchestration(
        requested.intelligence_key_sha256
    )
    if active is not None:
        repository.upsert_context_binding(
            targeting_context_id=targeting_context_id,
            modeling_context_sha256=requested.modeling_context.modeling_context_sha256,
            orchestration_id=int(active["orchestration_id"]),
            binding_status="PREPARING",
            timestamp=_utc_timestamp(),
        )
        return Phase10OrchestrationStart(active, False, False, False)

    reuse_plan = build_phase10_reuse_plan(
        database_path,
        requested,
        project_root=project_root,
    )
    ready = repository.find_ready_orchestration_for_context(
        targeting_context_id,
        requested.intelligence_key_sha256,
    )
    if ready is not None and all(
        decision == "REUSE" for decision in reuse_plan.values()
    ):
        assert ready["generation_id"] is not None
        repository.verify_generation_record(int(ready["generation_id"]))
        repository.touch_generation_usage(
            int(ready["generation_id"]), used_at=_utc_timestamp()
        )
        # A Phase 9 context update intentionally clears its source link.  A
        # delivery-channel-only edit does not change Modeling Context identity,
        # so re-publish the already verified lineage atomically without doing
        # analytical work.
        repository.finalize_ready_context(
            targeting_context_id=targeting_context_id,
            modeling_context_sha256=(
                requested.modeling_context.modeling_context_sha256
            ),
            orchestration_id=int(ready["orchestration_id"]),
            generation_id=int(ready["generation_id"]),
            analysis_run_id=int(ready["analysis_run_id"]),
            model_run_id=int(ready["model_run_id"]),
            scoring_run_id=int(ready["scoring_run_id"]),
            business_message=BUSINESS_LABELS["READY"],
            timestamp=_utc_timestamp(),
        )
        return Phase10OrchestrationStart(ready, False, True, False)

    orchestration, created = repository.create_or_get_active_orchestration(
        orchestration_contract_version=PHASE10_ORCHESTRATION_CONTRACT_VERSION,
        targeting_context_id=targeting_context_id,
        modeling_context_sha256=requested.modeling_context.modeling_context_sha256,
        intelligence_key_sha256=requested.intelligence_key_sha256,
        business_message=BUSINESS_LABELS["CHECKING_COMPATIBILITY"],
        reuse_plan=reuse_plan,
        created_at=_utc_timestamp(),
    )
    repository.upsert_context_binding(
        targeting_context_id=targeting_context_id,
        modeling_context_sha256=requested.modeling_context.modeling_context_sha256,
        orchestration_id=int(orchestration["orchestration_id"]),
        binding_status="PREPARING",
        timestamp=_utc_timestamp(),
    )
    submitted = False
    if created and all(decision == "REUSE" for decision in reuse_plan.values()):
        run_phase10_orchestration(
            database_path,
            int(orchestration["orchestration_id"]),
            project_root=project_root,
        )
    elif created:
        try:
            submitter(
                database_path,
                int(orchestration["orchestration_id"]),
                project_root,
            )
            submitted = True
        except Exception as exc:
            logger.exception(
                "Phase 10 parent submission failed | orchestration_id=%s",
                orchestration["orchestration_id"],
            )
            repository.mark_orchestration_terminal(
                int(orchestration["orchestration_id"]),
                status="FAILED",
                business_message=SAFE_FAILURE_MESSAGE,
                safe_error_message=SAFE_FAILURE_MESSAGE,
                technical_message=type(exc).__name__,
                completed_at=_utc_timestamp(),
            )
            raise Phase10OrchestrationError(SAFE_FAILURE_MESSAGE) from exc
    current = repository.fetch_orchestration(int(orchestration["orchestration_id"]))
    assert current is not None
    return Phase10OrchestrationStart(current, created, False, submitted)


def _actual_reuse_plan(
    historical: HistoricalAnalysisResolution,
    model: Phase10ModelResolution,
    *,
    scoring_reused: bool,
    rank_reused: bool,
) -> dict[str, ReuseDecision]:
    return {
        "analysis": "REUSE" if historical.reused else "BUILD",
        "model": "REUSE" if model.reused else "BUILD",
        "scoring": "REUSE" if scoring_reused else "BUILD",
        "rank": "REUSE" if rank_reused else "BUILD",
    }


def run_phase10_orchestration(
    database_path: str | Path,
    orchestration_id: int,
    *,
    project_root: str | Path | None = None,
    artifact_root: str | Path = DEFAULT_ARTIFACT_ROOT,
    scoring_chunk_size: int = DEFAULT_SCORING_CHUNK_SIZE,
    rank_chunk_size: int = DEFAULT_PREPARATION_SCAN_CHUNK_SIZE,
) -> dict[str, Any]:
    """Run or resume one durable parent from its highest persisted progress."""

    repository = Phase10IntelligenceRepository(database_path)
    initial = repository.fetch_orchestration(orchestration_id)
    if initial is None:
        raise Phase10OrchestrationError("Phase 10 orchestration was not found.")
    if initial["status"] in {"READY", "BLOCKED", "FAILED"}:
        return initial

    def advance(
        stage: str,
        progress: int,
        *,
        reuse_plan: Mapping[str, Any] | None = None,
        analysis_run_id: int | None = None,
        model_run_id: int | None = None,
        scoring_run_id: int | None = None,
        training_job_id: int | None = None,
        scoring_job_id: int | None = None,
    ) -> None:
        current = repository.fetch_orchestration(orchestration_id)
        if current is None or current["status"] != "RUNNING":
            return
        if progress < int(current["progress_percent"]):
            return
        repository.update_orchestration_stage(
            orchestration_id,
            stage=stage,
            progress_percent=progress,
            business_message=BUSINESS_LABELS[stage],
            updated_at=_utc_timestamp(),
            technical_message=None,
            reuse_plan=reuse_plan,
            analysis_run_id=analysis_run_id,
            model_run_id=model_run_id,
            scoring_run_id=scoring_run_id,
            training_job_id=training_job_id,
            scoring_job_id=scoring_job_id,
        )

    try:
        if initial["status"] == "QUEUED":
            repository.mark_orchestration_running(
                orchestration_id,
                stage="CHECKING_COMPATIBILITY",
                progress_percent=2,
                business_message=BUSINESS_LABELS["CHECKING_COMPATIBILITY"],
                started_at=_utc_timestamp(),
            )
        current = repository.fetch_orchestration(orchestration_id)
        assert current is not None
        requested = build_phase10_requested_intelligence(
            database_path,
            int(current["targeting_context_id"]),
        )
        if (
            requested.modeling_context.modeling_context_sha256
            != current["modeling_context_sha256"]
            or requested.intelligence_key_sha256
            != current["intelligence_key_sha256"]
        ):
            raise Phase10OrchestrationError(
                "The campaign context or source identity changed during preparation."
            )
        persisted_plan = json.loads(current["reuse_plan_json"])
        if set(persisted_plan) != {"analysis", "model", "scoring", "rank"} or any(
            value not in {"REUSE", "BUILD"} for value in persisted_plan.values()
        ):
            raise Phase10OrchestrationError("The persisted reuse plan is invalid.")

        advance("RESOLVING_HISTORICAL_CONTEXT", 12)
        historical = resolve_or_create_phase10_historical_analysis(
            database_path,
            requested.modeling_context,
        )
        advance(
            "CHECKING_TRAINING_ELIGIBILITY",
            22,
            analysis_run_id=historical.analysis_run_id,
        )
        if historical.status == "BLOCKED":
            repository.mark_orchestration_terminal(
                orchestration_id,
                status="BLOCKED",
                business_message=historical.business_message,
                completed_at=_utc_timestamp(),
            )
            blocked = repository.fetch_orchestration(orchestration_id)
            assert blocked is not None
            return blocked

        advance("RESOLVING_MODEL", 27, analysis_run_id=historical.analysis_run_id)

        def model_progress(_stage: str, child_progress: int, _message: str | None) -> None:
            mapped = min(44, 25 + int((child_progress * 20) / 100))
            advance(
                "RESOLVING_MODEL",
                max(27, mapped),
                analysis_run_id=historical.analysis_run_id,
            )

        model = resolve_or_train_phase10_model(
            database_path,
            requested.modeling_context,
            historical,
            project_root=project_root,
            artifact_root=artifact_root,
            training_progress_observer=model_progress,
        )
        if model is None or model.status != "READY" or model.model_run_id is None:
            raise Phase10OrchestrationError("A compatible model was not resolved.")
        advance(
            "VALIDATING_MODEL",
            47,
            analysis_run_id=historical.analysis_run_id,
            model_run_id=model.model_run_id,
            training_job_id=model.training_job_id,
        )
        advance(
            "RESOLVING_SCORING",
            50,
            analysis_run_id=historical.analysis_run_id,
            model_run_id=model.model_run_id,
            training_job_id=model.training_job_id,
        )

        def scoring_progress(
            _stage: str,
            child_progress: int,
            _message: str | None,
        ) -> None:
            mapped = min(89, 50 + int((child_progress * 40) / 100))
            advance(
                "SCORING_POTENTIAL_CUSTOMERS",
                max(51, mapped),
                analysis_run_id=historical.analysis_run_id,
                model_run_id=model.model_run_id,
                training_job_id=model.training_job_id,
            )

        scoring = resolve_or_build_phase10_scoring_rank(
            database_path,
            model,
            project_root=project_root,
            scoring_chunk_size=scoring_chunk_size,
            rank_chunk_size=rank_chunk_size,
            scoring_progress_observer=scoring_progress,
        )
        if scoring.status != "READY" or scoring.scoring_run_id is None:
            raise Phase10OrchestrationError("Compatible prospect scoring was not resolved.")
        actual_plan = _actual_reuse_plan(
            historical,
            model,
            scoring_reused=scoring.scoring_reused,
            rank_reused=scoring.rank_reused,
        )
        advance(
            "PREPARING_TARGET_GROUP",
            94,
            reuse_plan=actual_plan,
            analysis_run_id=historical.analysis_run_id,
            model_run_id=model.model_run_id,
            scoring_run_id=scoring.scoring_run_id,
            training_job_id=model.training_job_id,
            scoring_job_id=scoring.scoring_job_id,
        )
        advance(
            "VERIFYING_FINAL_CURRENTNESS",
            99,
            reuse_plan=actual_plan,
            analysis_run_id=historical.analysis_run_id,
            model_run_id=model.model_run_id,
            scoring_run_id=scoring.scoring_run_id,
            training_job_id=model.training_job_id,
            scoring_job_id=scoring.scoring_job_id,
        )
        finalize_phase10_ready_context(
            database_path,
            targeting_context_id=int(current["targeting_context_id"]),
            orchestration_id=orchestration_id,
            modeling_context=requested.modeling_context,
            historical_resolution=historical,
            model_resolution=model,
            scoring_resolution=scoring,
            intelligence_key_sha256=requested.intelligence_key_sha256,
            business_message=BUSINESS_LABELS["READY"],
        )
        classify_phase10_lifecycle(database_path)
    except Exception as exc:
        logger.exception(
            "Phase 10 orchestration failed | orchestration_id=%s",
            orchestration_id,
        )
        failed = repository.fetch_orchestration(orchestration_id)
        if failed is not None and failed["status"] in {"QUEUED", "RUNNING"}:
            repository.mark_orchestration_terminal(
                orchestration_id,
                status="FAILED",
                business_message=SAFE_FAILURE_MESSAGE,
                safe_error_message=SAFE_FAILURE_MESSAGE,
                technical_message=type(exc).__name__,
                completed_at=_utc_timestamp(),
            )
        terminal = repository.fetch_orchestration(orchestration_id)
        assert terminal is not None
        return terminal
    ready = repository.fetch_orchestration(orchestration_id)
    assert ready is not None
    return ready


def reconcile_phase10_orchestrations(
    database_path: str | Path,
    *,
    project_root: str | Path | None = None,
    submitter: OrchestrationSubmitter = _default_submitter,
) -> int:
    """Resubmit durable QUEUED/RUNNING parents for verified-stage recovery."""

    rows = Phase10IntelligenceRepository(database_path).list_active_orchestrations()
    for row in rows:
        submitter(database_path, int(row["orchestration_id"]), project_root)
    return len(rows)


__all__ = (
    "BUSINESS_LABELS",
    "SAFE_FAILURE_MESSAGE",
    "TECHNICAL_STAGES",
    "Phase10OrchestrationError",
    "Phase10OrchestrationStart",
    "Phase10RequestedIntelligence",
    "build_phase10_requested_intelligence",
    "build_phase10_reuse_plan",
    "prepare_phase10_orchestration",
    "reconcile_phase10_orchestrations",
    "run_phase10_orchestration",
)
