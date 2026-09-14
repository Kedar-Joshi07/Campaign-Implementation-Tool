"""Business-safe Phase 10 API projection and Phase 9 readiness bridge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.repositories.campaign_targeting_context_repository import (
    CampaignTargetingContextRepository,
)
from app.repositories.phase10_intelligence_repository import (
    Phase10IntelligenceRepository,
)
from app.services.phase10_orchestration_service import (
    SAFE_FAILURE_MESSAGE,
    OrchestrationSubmitter,
    Phase10OrchestrationError,
    Phase10RequestedIntelligence,
    build_phase10_requested_intelligence,
    build_phase10_reuse_plan,
    prepare_phase10_orchestration,
)


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]
PHASE10_API_SUBMITTER: OrchestrationSubmitter | None = None

NOT_STARTED_MESSAGE = "Targeting intelligence has not been prepared yet."
STALE_MESSAGE = (
    "Campaign details or current data changed. Prepare targeting intelligence again."
)


class Phase10ApiServiceError(RuntimeError):
    """Base class for stable Phase 10 API errors."""


class Phase10ApiContextNotFoundError(Phase10ApiServiceError):
    """Raised when the requested Campaign Context does not exist."""


class Phase10ApiValidationError(Phase10ApiServiceError):
    """Raised when a persisted or requested identity is invalid."""


class Phase10ApiConflictError(Phase10ApiServiceError):
    """Raised when the requested transition conflicts with current readiness."""


def _root(project_root: str | Path | None) -> Path:
    return DEFAULT_PROJECT_ROOT if project_root is None else Path(project_root)


def _requested(
    database_path: str | Path,
    targeting_context_id: int,
) -> Phase10RequestedIntelligence:
    if CampaignTargetingContextRepository(database_path).fetch_context(
        targeting_context_id
    ) is None:
        raise Phase10ApiContextNotFoundError("Campaign Context was not found.")
    try:
        return build_phase10_requested_intelligence(database_path, targeting_context_id)
    except Phase10OrchestrationError as exc:
        raise Phase10ApiValidationError("Campaign Context is invalid.") from exc


def _reuse_summary(value: Any) -> dict[str, str]:
    try:
        parsed = json.loads(value) if isinstance(value, str) else dict(value)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise Phase10ApiValidationError(
            "Targeting-intelligence preparation state is invalid."
        ) from exc
    expected = {"analysis", "model", "scoring", "rank"}
    if set(parsed) != expected or any(
        decision not in {"REUSE", "BUILD"} for decision in parsed.values()
    ):
        raise Phase10ApiValidationError(
            "Targeting-intelligence preparation state is invalid."
        )
    return {name: parsed[name] for name in ("analysis", "model", "scoring", "rank")}


def _all_reusable(reuse_summary: dict[str, str]) -> bool:
    return all(value == "REUSE" for value in reuse_summary.values())


def _identity_response(requested: Phase10RequestedIntelligence) -> dict[str, Any]:
    return {
        "modeling_context_sha256": requested.modeling_context.modeling_context_sha256,
        "context": requested.modeling_context.payload,
    }


def _technical_details(
    requested: Phase10RequestedIntelligence,
    orchestration: dict[str, Any] | None,
) -> dict[str, Any]:
    def positive_id(name: str) -> int | None:
        if orchestration is None or orchestration.get(name) is None:
            return None
        return int(orchestration[name])

    return {
        "orchestration_id": positive_id("orchestration_id"),
        "modeling_context_sha256": requested.modeling_context.modeling_context_sha256,
        "intelligence_key_sha256": requested.intelligence_key_sha256,
        "generation_id": positive_id("generation_id"),
        "analysis_run_id": positive_id("analysis_run_id"),
        "model_run_id": positive_id("model_run_id"),
        "scoring_run_id": positive_id("scoring_run_id"),
        "training_job_id": positive_id("training_job_id"),
        "scoring_job_id": positive_id("scoring_job_id"),
        # Step 8 persists an exception class only, never a traceback or raw values.
        "technical_message": (
            None if orchestration is None else orchestration.get("technical_message")
        ),
    }


def _response(
    *,
    targeting_context_id: int,
    requested: Phase10RequestedIntelligence,
    status: str,
    stage: str,
    progress_percent: int,
    business_message: str,
    reuse_summary: dict[str, str],
    orchestration: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "targeting_context_id": targeting_context_id,
        "status": status,
        "stage": stage,
        "progress_percent": progress_percent,
        "business_message": business_message,
        "can_retry": status in {"NOT_STARTED", "BLOCKED", "FAILED", "STALE"},
        "is_ready": status == "READY",
        "reuse_summary": reuse_summary,
        "technical_details": _technical_details(requested, orchestration),
    }


def _verified_state(
    database_path: str | Path,
    targeting_context_id: int,
    requested: Phase10RequestedIntelligence,
    *,
    project_root: str | Path | None,
) -> tuple[dict[str, Any] | None, dict[str, str], bool]:
    """Resolve the current binding and re-verify every READY compatibility gate."""

    repository = Phase10IntelligenceRepository(database_path)
    binding = repository.fetch_context_binding(targeting_context_id)
    if binding is None:
        return (
            None,
            build_phase10_reuse_plan(
                database_path,
                requested,
                project_root=_root(project_root),
            ),
            False,
        )
    orchestration = repository.fetch_orchestration(int(binding["orchestration_id"]))
    if orchestration is None:
        raise Phase10ApiValidationError(
            "Targeting-intelligence preparation state is invalid."
        )
    exact = (
        binding["modeling_context_sha256"]
        == requested.modeling_context.modeling_context_sha256
        and orchestration["modeling_context_sha256"]
        == requested.modeling_context.modeling_context_sha256
        and orchestration["intelligence_key_sha256"]
        == requested.intelligence_key_sha256
    )
    if not exact:
        return (
            orchestration,
            build_phase10_reuse_plan(
                database_path,
                requested,
                project_root=_root(project_root),
            ),
            False,
        )
    persisted_reuse = _reuse_summary(orchestration["reuse_plan_json"])
    if orchestration["status"] != "READY":
        # Polling is a state read. It must never repeat compatibility scans or
        # analytical work while a durable parent is active/terminal.
        return orchestration, persisted_reuse, True
    reuse = build_phase10_reuse_plan(
        database_path,
        requested,
        project_root=_root(project_root),
    )
    generation_id = orchestration.get("generation_id")
    if generation_id is None or binding.get("generation_id") != generation_id:
        return orchestration, reuse, False
    context_row = CampaignTargetingContextRepository(database_path).fetch_context(
        targeting_context_id
    )
    if (
        context_row is None
        or context_row.get("source_scoring_run_id") is None
        or int(context_row["source_scoring_run_id"])
        != int(orchestration["scoring_run_id"])
    ):
        return orchestration, reuse, False
    try:
        repository.verify_generation_record(int(generation_id))
    except Exception:
        return orchestration, reuse, False
    return orchestration, reuse, _all_reusable(reuse)


def get_phase10_intelligence_plan(
    database_path: str | Path,
    targeting_context_id: int,
    *,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    requested = _requested(database_path, targeting_context_id)
    orchestration, reuse, compatible = _verified_state(
        database_path,
        targeting_context_id,
        requested,
        project_root=project_root,
    )
    if orchestration is None:
        readiness, message = "NEEDS_PREPARATION", NOT_STARTED_MESSAGE
    elif not compatible:
        readiness, message = "STALE", STALE_MESSAGE
    elif orchestration["status"] in {"QUEUED", "RUNNING"}:
        readiness, message = "PREPARING", str(orchestration["business_message"])
    else:
        readiness, message = (
            str(orchestration["status"]),
            str(orchestration["business_message"]),
        )
    return {
        "targeting_context_id": targeting_context_id,
        "readiness": readiness,
        "is_ready": readiness == "READY",
        "business_message": message,
        "modeling_context": _identity_response(requested),
        "reuse_summary": reuse,
    }


def prepare_phase10_targeting_intelligence(
    database_path: str | Path,
    targeting_context_id: int,
    *,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    _requested(database_path, targeting_context_id)
    kwargs: dict[str, Any] = {"project_root": _root(project_root)}
    if PHASE10_API_SUBMITTER is not None:
        kwargs["submitter"] = PHASE10_API_SUBMITTER
    try:
        prepare_phase10_orchestration(
            database_path,
            targeting_context_id,
            **kwargs,
        )
    except Phase10OrchestrationError as exc:
        if str(exc) == SAFE_FAILURE_MESSAGE:
            raise Phase10ApiServiceError(SAFE_FAILURE_MESSAGE) from exc
        raise Phase10ApiValidationError("Campaign Context is invalid.") from exc
    return get_phase10_preparation(
        database_path,
        targeting_context_id,
        project_root=project_root,
    )


def get_phase10_preparation(
    database_path: str | Path,
    targeting_context_id: int,
    *,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    requested = _requested(database_path, targeting_context_id)
    orchestration, reuse, compatible = _verified_state(
        database_path,
        targeting_context_id,
        requested,
        project_root=project_root,
    )
    if orchestration is None:
        return _response(
            targeting_context_id=targeting_context_id,
            requested=requested,
            status="NOT_STARTED",
            stage="NOT_STARTED",
            progress_percent=0,
            business_message=NOT_STARTED_MESSAGE,
            reuse_summary=reuse,
            orchestration=None,
        )
    if not compatible:
        return _response(
            targeting_context_id=targeting_context_id,
            requested=requested,
            status="STALE",
            stage="STALE",
            progress_percent=0,
            business_message=STALE_MESSAGE,
            reuse_summary=reuse,
            orchestration=orchestration,
        )
    return _response(
        targeting_context_id=targeting_context_id,
        requested=requested,
        status=str(orchestration["status"]),
        stage=str(orchestration["stage"]),
        progress_percent=int(orchestration["progress_percent"]),
        business_message=str(orchestration["business_message"]),
        reuse_summary=_reuse_summary(orchestration["reuse_plan_json"]),
        orchestration=orchestration,
    )


def retry_phase10_targeting_intelligence(
    database_path: str | Path,
    targeting_context_id: int,
    *,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    current = get_phase10_preparation(
        database_path,
        targeting_context_id,
        project_root=project_root,
    )
    if current["status"] in {"QUEUED", "RUNNING"}:
        raise Phase10ApiConflictError("Targeting intelligence is already being prepared.")
    if current["status"] == "READY":
        raise Phase10ApiConflictError("Targeting intelligence is already ready.")
    return prepare_phase10_targeting_intelligence(
        database_path,
        targeting_context_id,
        project_root=project_root,
    )


__all__ = (
    "Phase10ApiConflictError",
    "Phase10ApiContextNotFoundError",
    "Phase10ApiServiceError",
    "Phase10ApiValidationError",
    "get_phase10_intelligence_plan",
    "get_phase10_preparation",
    "prepare_phase10_targeting_intelligence",
    "retry_phase10_targeting_intelligence",
)
