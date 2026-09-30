"""Governed ownership and retry/rejoin handling for Phase 11 dependencies."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.repositories.campaign_result_registry_repository import (
    AttemptExecutionFence,
    CampaignResultRegistryRepository,
)
from app.services.phase10_api_service import (
    Phase10ApiConflictError,
    get_phase10_preparation,
    retry_phase10_targeting_intelligence,
)
from app.services.phase11_result_contracts import Phase11RegistryStateError


PHASE11_FAILURE_OWNERSHIP = {
    "TARGETING_INTELLIGENCE_FAILED": "PHASE10_TRANSIENT",
    "PHASE10_TRANSIENT_FAILED": "PHASE10_TRANSIENT",
    "TARGETING_INTELLIGENCE_BLOCKED": "PHASE10_BUSINESS",
    "PHASE10_BUSINESS_BLOCKED": "PHASE10_BUSINESS",
    "CALIBRATED_PROPENSITY_NOT_READY": "CALIBRATION",
    "STALE_PROCESSING_ATTEMPT": "STALE_WORKER",
    "SAVED_SEARCH_NO_LONGER_VALID": "PERMANENT_VALIDATION",
    "INVALID_IMMUTABLE_CONTRACT": "PERMANENT_VALIDATION",
    "PHASE10_PERMANENT_VALIDATION_FAILED": "PERMANENT_VALIDATION",
}


@dataclass(frozen=True)
class Phase10DependencyDecision:
    status: str
    orchestration_id: int
    rejoined: bool


def classify_failure_ownership(runtime: Mapping[str, Any] | None) -> str:
    """Map only allowlisted persisted failures to their governing subsystem."""

    if runtime is None or runtime.get("failure_code") is None:
        return "PHASE11_LOCAL_TRANSIENT"
    return PHASE11_FAILURE_OWNERSHIP.get(
        str(runtime["failure_code"]), "PHASE11_LOCAL_TRANSIENT"
    )


def _orchestration_id(response: Mapping[str, Any]) -> int:
    details = response.get("technical_details")
    if not isinstance(details, Mapping):
        raise Phase11RegistryStateError(
            "Targeting-intelligence dependency lineage is unavailable."
        )
    identifier = details.get("orchestration_id")
    if isinstance(identifier, bool) or not isinstance(identifier, int) or identifier <= 0:
        raise Phase11RegistryStateError(
            "Targeting-intelligence dependency lineage is unavailable."
        )
    return identifier


def retry_or_rejoin_phase10_dependency(
    database_path: str | Path,
    search_run: Mapping[str, Any],
    *,
    fence: AttemptExecutionFence,
    project_root: str | Path | None = None,
) -> Phase10DependencyDecision:
    """Rejoin active exact work or govern creation of one new Phase 10 attempt."""

    path = Path(database_path)
    targeting_context_id = int(search_run["targeting_context_id"])
    response = get_phase10_preparation(
        path, targeting_context_id, project_root=project_root
    )
    initial_status = str(response.get("status") or "")
    if initial_status == "BLOCKED":
        raise Phase11RegistryStateError(
            "Targeting intelligence is blocked by business-data insufficiency and cannot be retried automatically."
        )
    if initial_status == "FAILED" and not bool(response.get("can_retry")):
        raise Phase11RegistryStateError(
            "Targeting intelligence has a permanent validation failure and cannot be retried automatically."
        )

    rejoined = initial_status in {"QUEUED", "RUNNING"}
    if initial_status not in {"QUEUED", "RUNNING", "READY"}:
        concurrent_rejoin = False
        try:
            response = retry_phase10_targeting_intelligence(
                path, targeting_context_id, project_root=project_root
            )
        except Phase10ApiConflictError:
            # A concurrent exact-context retry may have won. Re-read and rejoin
            # only if it is now durably active; all other conflicts remain errors.
            response = get_phase10_preparation(
                path, targeting_context_id, project_root=project_root
            )
            if response.get("status") not in {"QUEUED", "RUNNING", "READY"}:
                raise
            concurrent_rejoin = True
        rejoined = concurrent_rejoin

    status = str(response.get("status") or "")
    if status not in {"QUEUED", "RUNNING", "READY"}:
        raise Phase11RegistryStateError(
            "Targeting intelligence did not enter a retryable dependency state."
        )
    orchestration_id = _orchestration_id(response)
    CampaignResultRegistryRepository(path).bind_phase10_dependency(
        int(search_run["search_run_id"]),
        **fence.as_kwargs(),
        orchestration_id=orchestration_id,
        dependency_status=status,
        rejoined=rejoined,
    )
    return Phase10DependencyDecision(status, orchestration_id, rejoined)


__all__ = (
    "PHASE11_FAILURE_OWNERSHIP",
    "Phase10DependencyDecision",
    "classify_failure_ownership",
    "retry_or_rejoin_phase10_dependency",
)
