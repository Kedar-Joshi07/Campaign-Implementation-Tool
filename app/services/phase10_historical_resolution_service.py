"""Exact Historical Analysis reuse/build and Phase 10 training eligibility."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from app.ml.preprocessing import FeatureSplitError, split_customer_cohort
from app.ml.pu_estimators import ELKAN_HOLD_OUT_RATIO
from app.ml.training import MINIMUM_POSITIVE_COUNT, MINIMUM_UNLABELED_COUNT
from app.repositories.historical_repository import HistoricalRepository
from app.schemas.phase10_intelligence import (
    ModelingContextContract,
    PHASE10_AUTOMATED_TRAINING_RANDOM_SEED,
    PHASE10_AUTOMATED_TRAINING_RUN_ELKAN_CHALLENGER,
    PHASE10_AUTOMATED_TRAINING_VALIDATION_FRACTION,
    PHASE10_INSUFFICIENT_HISTORY_MESSAGE,
    PHASE10_MINIMUM_POSITIVE_CUSTOMERS,
    PHASE10_MINIMUM_SELECTED_CUSTOMERS,
    PHASE10_MINIMUM_UNLABELED_CUSTOMERS,
    PHASE10_TRAINING_ELIGIBILITY_POLICY_VERSION,
    ResolvedHistoricalFiltersContract,
    TrainingEligibilityContract,
)
from app.services.historical_analysis_service import (
    HistoricalAnalysisError,
    HistoricalSavedRunError,
    NoMatchingObservationsError,
    create_historical_analysis,
    get_historical_analysis_run,
)
from app.services.historical_source_provenance_service import (
    HistoricalSourceProvenance,
    HistoricalSourceProvenanceError,
    resolve_current_historical_source_provenance,
)
from app.services.phase10_context_identity_service import (
    ModelingContextIdentity,
    normalize_modeling_context,
    resolve_phase10_historical_filters,
)
from app.services.training_cohort_service import (
    TrainingCohortError,
    reconstruct_training_cohort,
)


HistoricalResolutionStatus = Literal["READY", "BLOCKED"]


class Phase10HistoricalResolutionError(RuntimeError):
    """Raised when historical compatibility cannot be resolved safely."""


@dataclass(frozen=True)
class HistoricalCandidateRejection:
    analysis_run_id: int
    reason_code: str


@dataclass(frozen=True)
class HistoricalAnalysisResolution:
    status: HistoricalResolutionStatus
    modeling_context_sha256: str
    resolved_filters: ResolvedHistoricalFiltersContract
    analysis_run_id: int | None
    reused: bool
    created: bool
    eligibility: TrainingEligibilityContract
    compatible_candidate_ids: tuple[int, ...]
    rejected_candidates: tuple[HistoricalCandidateRejection, ...]
    business_message: str


def evaluate_training_eligibility(
    summary: Mapping[str, Any],
    *,
    deterministic_split_viable: bool,
) -> TrainingEligibilityContract:
    """Apply frozen v1 count thresholds plus an exact split-viability result."""

    counts: dict[str, int] = {}
    for field in (
        "selected_customer_count",
        "positive_customer_count",
        "unlabeled_customer_count",
    ):
        value = summary.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise Phase10HistoricalResolutionError(
                "Historical analysis customer counts are invalid."
            )
        counts[field] = value
    if counts["positive_customer_count"] + counts["unlabeled_customer_count"] != (
        counts["selected_customer_count"]
    ):
        raise Phase10HistoricalResolutionError(
            "Historical analysis customer counts do not reconcile."
        )

    reasons: list[str] = []
    if counts["selected_customer_count"] < PHASE10_MINIMUM_SELECTED_CUSTOMERS:
        reasons.append("INSUFFICIENT_SELECTED_CUSTOMERS")
    if counts["positive_customer_count"] < PHASE10_MINIMUM_POSITIVE_CUSTOMERS:
        reasons.append("INSUFFICIENT_POSITIVE_CUSTOMERS")
    if counts["unlabeled_customer_count"] < PHASE10_MINIMUM_UNLABELED_CUSTOMERS:
        reasons.append("INSUFFICIENT_UNLABELED_CUSTOMERS")
    if not deterministic_split_viable:
        reasons.append("DETERMINISTIC_SPLIT_NOT_VIABLE")

    blocked = bool(reasons)
    return TrainingEligibilityContract(
        training_eligibility_policy_version=(
            PHASE10_TRAINING_ELIGIBILITY_POLICY_VERSION
        ),
        status="BLOCKED" if blocked else "ELIGIBLE",
        **counts,
        minimum_selected_customer_count=PHASE10_MINIMUM_SELECTED_CUSTOMERS,
        minimum_positive_customer_count=PHASE10_MINIMUM_POSITIVE_CUSTOMERS,
        minimum_unlabeled_customer_count=PHASE10_MINIMUM_UNLABELED_CUSTOMERS,
        deterministic_split_viable=deterministic_split_viable,
        reason_codes=reasons,
        business_message=PHASE10_INSUFFICIENT_HISTORY_MESSAGE if blocked else None,
    )


def _source_matches(
    row: Mapping[str, Any],
    current: HistoricalSourceProvenance,
) -> bool:
    customer_checksum = row.get("customer_source_checksum")
    campaign_checksum = row.get("campaign_sales_source_checksum")
    return (
        row.get("customer_import_id") == current.customer_import_id
        and isinstance(customer_checksum, str)
        and customer_checksum.strip().lower() == current.customer_source_checksum
        and row.get("campaign_sales_import_id") == current.campaign_sales_import_id
        and isinstance(campaign_checksum, str)
        and campaign_checksum.strip().lower()
        == current.campaign_sales_source_checksum
    )


def _deterministic_split_viable(
    database_path: str | Path,
    analysis_run_id: int,
) -> bool:
    """Exercise the exact governed split and enabled challenger holdout preconditions."""

    try:
        cohort = reconstruct_training_cohort(database_path, analysis_run_id)
        split = split_customer_cohort(
            cohort.frame,
            validation_fraction=PHASE10_AUTOMATED_TRAINING_VALIDATION_FRACTION,
            random_seed=PHASE10_AUTOMATED_TRAINING_RANDOM_SEED,
        )
    except (TrainingCohortError, FeatureSplitError, ValueError):
        return False

    train_labels = np.asarray(split.train_labels, dtype=np.int8)
    validation_labels = np.asarray(split.validation_labels, dtype=np.int8)
    if (
        int(np.sum(train_labels == 1)) < MINIMUM_POSITIVE_COUNT
        or int(np.sum(train_labels == 0)) < MINIMUM_UNLABELED_COUNT
        or not np.any(validation_labels == 1)
        or not np.any(validation_labels == 0)
    ):
        return False
    if PHASE10_AUTOMATED_TRAINING_RUN_ELKAN_CHALLENGER:
        indices = np.arange(train_labels.size)
        np.random.RandomState(PHASE10_AUTOMATED_TRAINING_RANDOM_SEED).shuffle(indices)
        holdout_size = int(math.ceil(train_labels.size * ELKAN_HOLD_OUT_RATIO))
        if not np.any(train_labels[indices[:holdout_size]] == 1):
            return False
    return True


def _expected_filter_payload(
    resolved_filters: ResolvedHistoricalFiltersContract,
) -> dict[str, Any]:
    return resolved_filters.model_dump(mode="json")


def _find_compatible_candidates(
    database_path: str | Path,
    *,
    expected_filters: dict[str, Any],
    current_source: HistoricalSourceProvenance,
) -> tuple[list[dict[str, Any]], list[HistoricalCandidateRejection]]:
    compatible: list[dict[str, Any]] = []
    rejected: list[HistoricalCandidateRejection] = []
    rows = HistoricalRepository(database_path).list_completed_analysis_candidates()
    for row in rows:
        analysis_run_id = int(row["analysis_run_id"])
        if not _source_matches(row, current_source):
            rejected.append(
                HistoricalCandidateRejection(analysis_run_id, "SOURCE_PROVENANCE_MISMATCH")
            )
            continue
        try:
            reopened = get_historical_analysis_run(database_path, analysis_run_id)
        except (HistoricalSavedRunError, HistoricalAnalysisError, ValueError):
            rejected.append(
                HistoricalCandidateRejection(analysis_run_id, "INVALID_SAVED_ANALYSIS")
            )
            continue
        if reopened["filters"] != expected_filters:
            rejected.append(
                HistoricalCandidateRejection(analysis_run_id, "FILTER_IDENTITY_MISMATCH")
            )
            continue
        try:
            reconstruct_training_cohort(database_path, analysis_run_id)
        except TrainingCohortError:
            rejected.append(
                HistoricalCandidateRejection(
                    analysis_run_id,
                    "CURRENT_COHORT_RECONCILIATION_FAILED",
                )
            )
            continue
        compatible.append(reopened)
    return compatible, rejected


def find_reusable_phase10_historical_analysis(
    database_path: str | Path,
    modeling_context: (
        ModelingContextIdentity | ModelingContextContract | Mapping[str, Any]
    ),
) -> HistoricalAnalysisResolution | None:
    """Return the exact reusable Historical Analysis without creating one."""

    identity = (
        modeling_context
        if isinstance(modeling_context, ModelingContextIdentity)
        else normalize_modeling_context(modeling_context)
    )
    resolved_filters = resolve_phase10_historical_filters(database_path, identity)
    try:
        current_source = resolve_current_historical_source_provenance(database_path)
    except HistoricalSourceProvenanceError as exc:
        raise Phase10HistoricalResolutionError(
            "Current historical source provenance is unavailable."
        ) from exc
    compatible, rejected = _find_compatible_candidates(
        database_path,
        expected_filters=_expected_filter_payload(resolved_filters),
        current_source=current_source,
    )
    if not compatible:
        return None
    analysis = compatible[0]
    analysis_run_id = int(analysis["analysis_run_id"])
    count_decision = evaluate_training_eligibility(
        analysis["summary"],
        deterministic_split_viable=True,
    )
    split_viable = False
    if count_decision.status == "ELIGIBLE":
        split_viable = _deterministic_split_viable(database_path, analysis_run_id)
    eligibility = evaluate_training_eligibility(
        analysis["summary"],
        deterministic_split_viable=split_viable,
    )
    return HistoricalAnalysisResolution(
        status="READY" if eligibility.status == "ELIGIBLE" else "BLOCKED",
        modeling_context_sha256=identity.modeling_context_sha256,
        resolved_filters=resolved_filters,
        analysis_run_id=analysis_run_id,
        reused=True,
        created=False,
        eligibility=eligibility,
        compatible_candidate_ids=tuple(
            int(candidate["analysis_run_id"]) for candidate in compatible
        ),
        rejected_candidates=tuple(rejected),
        business_message=(
            "Verified past campaign history is ready."
            if eligibility.status == "ELIGIBLE"
            else PHASE10_INSUFFICIENT_HISTORY_MESSAGE
        ),
    )


def resolve_or_create_phase10_historical_analysis(
    database_path: str | Path,
    modeling_context: (
        ModelingContextIdentity | ModelingContextContract | Mapping[str, Any]
    ),
) -> HistoricalAnalysisResolution:
    """Reuse an exact current analysis or create it, then gate training eligibility."""

    identity = (
        modeling_context
        if isinstance(modeling_context, ModelingContextIdentity)
        else normalize_modeling_context(modeling_context)
    )
    resolved_filters = resolve_phase10_historical_filters(database_path, identity)
    expected_filters = _expected_filter_payload(resolved_filters)
    try:
        current_source = resolve_current_historical_source_provenance(database_path)
    except HistoricalSourceProvenanceError as exc:
        raise Phase10HistoricalResolutionError(
            "Current historical source provenance is unavailable."
        ) from exc

    compatible, rejected = _find_compatible_candidates(
        database_path,
        expected_filters=expected_filters,
        current_source=current_source,
    )
    if compatible:
        analysis = compatible[0]
        reused = True
        created = False
    else:
        try:
            analysis = create_historical_analysis(database_path, expected_filters)
        except NoMatchingObservationsError:
            eligibility = evaluate_training_eligibility(
                {
                    "selected_customer_count": 0,
                    "positive_customer_count": 0,
                    "unlabeled_customer_count": 0,
                },
                deterministic_split_viable=False,
            )
            return HistoricalAnalysisResolution(
                status="BLOCKED",
                modeling_context_sha256=identity.modeling_context_sha256,
                resolved_filters=resolved_filters,
                analysis_run_id=None,
                reused=False,
                created=False,
                eligibility=eligibility,
                compatible_candidate_ids=(),
                rejected_candidates=tuple(rejected),
                business_message=PHASE10_INSUFFICIENT_HISTORY_MESSAGE,
            )
        except HistoricalAnalysisError as exc:
            raise Phase10HistoricalResolutionError(
                "Historical analysis could not be resolved."
            ) from exc
        reused = False
        created = True

    analysis_run_id = int(analysis["analysis_run_id"])
    summary = analysis["summary"]
    count_decision = evaluate_training_eligibility(
        summary,
        deterministic_split_viable=True,
    )
    split_viable = False
    if count_decision.status == "ELIGIBLE":
        split_viable = _deterministic_split_viable(database_path, analysis_run_id)
    eligibility = evaluate_training_eligibility(
        summary,
        deterministic_split_viable=split_viable,
    )
    return HistoricalAnalysisResolution(
        status="READY" if eligibility.status == "ELIGIBLE" else "BLOCKED",
        modeling_context_sha256=identity.modeling_context_sha256,
        resolved_filters=resolved_filters,
        analysis_run_id=analysis_run_id,
        reused=reused,
        created=created,
        eligibility=eligibility,
        compatible_candidate_ids=tuple(
            int(candidate["analysis_run_id"]) for candidate in compatible
        ),
        rejected_candidates=tuple(rejected),
        business_message=(
            "Verified past campaign history is ready."
            if eligibility.status == "ELIGIBLE"
            else PHASE10_INSUFFICIENT_HISTORY_MESSAGE
        ),
    )


__all__ = (
    "HistoricalAnalysisResolution",
    "HistoricalCandidateRejection",
    "HistoricalResolutionStatus",
    "Phase10HistoricalResolutionError",
    "evaluate_training_eligibility",
    "find_reusable_phase10_historical_analysis",
    "resolve_or_create_phase10_historical_analysis",
)
