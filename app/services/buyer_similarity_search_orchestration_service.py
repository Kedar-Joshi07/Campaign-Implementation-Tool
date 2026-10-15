"""Fenced v3 search preparation and immutable similarity result publication.

This path deliberately does not call Phase 10 probability/model/calibration APIs.
"""

from __future__ import annotations

import json
import logging
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from app.repositories.campaign_result_registry_repository import CampaignResultRegistryRepository
from app.repositories.campaign_targeting_context_repository import CampaignTargetingContextRepository
from app.repositories.buyer_similarity_profile_repository import (
    BuyerSimilarityProfileLeaseBusy, publish_buyer_similarity_profile,
)
from app.repositories.buyer_similarity_scoring_repository import BuyerSimilarityGenerationBusy
from app.selection_contracts import BUYER_SIMILARITY_SELECTION_CONTRACT_VERSION
from app.services.buyer_similarity_cohort_service import build_product_buyer_cohorts
from app.services.buyer_similarity_partition_service import freeze_partition_manifest
from app.services.buyer_similarity_profile_service import fit_buyer_similarity_profile
from app.services.buyer_similarity_result_service import (
    find_similarity_result_snapshot, materialize_similarity_result,
    validate_similarity_result_snapshot,
)
from app.services.buyer_similarity_scoring_service import (
    BuyerSimilarityScoringCancelled, run_similarity_generation,
)
from app.services.buyer_similarity_selection_service import (
    SimilaritySelectionError, count_similarity_selection, resolve_similarity_context,
)
from app.services.phase11_result_contracts import Phase11RegistryStateError
from app.services.phase11_search_orchestration_service import (
    SearchOrchestrationOutcome, _heartbeat_during, _PHASE10_HEAVY_GATE,
    validate_persisted_search_identity,
)
from app.database.connection import get_connection
from app.qa_guard import assert_qa_runtime


logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _stale_before() -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


@contextmanager
def _heavy_slot_with_wait(progress: Callable[[str, str, int, str], None]):
    """Expose actual capacity wait while the outer attempt heartbeat stays live."""

    acquired = _PHASE10_HEAVY_GATE.acquire(blocking=False)
    if not acquired:
        progress(
            "WAITING_FOR_HEAVY_SLOT",
            "Waiting for intelligence capacity",
            8,
            "This search is active and waiting for bounded intelligence processing capacity.",
        )
        _PHASE10_HEAVY_GATE.acquire()
    try:
        yield
    finally:
        _PHASE10_HEAVY_GATE.release()


def execute_similarity_search_safely(
    database_path: str | Path, search_run_id: int, *, attempt_number: int,
    execution_lease_token: str, project_root: str | Path,
    cancellation_check: Callable[[], bool] | None = None,
) -> SearchOrchestrationOutcome:
    """Run or resume one exact v3 attempt under its durable execution fence."""

    path = Path(database_path)
    root = Path(project_root)
    assert_qa_runtime(path, project_root=root, operation="v3_search_worker",
                      record_admission=True)
    repository = CampaignResultRegistryRepository(path)
    fence = dict(attempt_number=attempt_number, execution_lease_token=execution_lease_token)
    initial_runtime = repository.fetch_search_runtime(search_run_id)
    last_percent = int(initial_runtime["progress_percent"]) if initial_runtime else 0
    last_processed = int(initial_runtime["processed_count"]) if initial_runtime else 0

    def progress(stage: str, label: str, percent: int, message: str, *,
                 processed: int | None = None, total: int | None = None,
                 unit: str | None = None,
                 workload: str = "NEW_INTELLIGENCE_BUILD") -> None:
        nonlocal last_percent, last_processed
        percent = max(last_percent, percent)
        if processed is not None:
            # A search spans several product generations. The durable counter is
            # cumulative across the attempt, not a per-generation counter that
            # resets to zero at each QUEUE_WAIT callback.
            processed = max(last_processed, processed)
            total = max(processed, total) if total is not None else None
        repository.update_search_progress(
            search_run_id, **fence, stage_code=stage, stage_label=label,
            progress_percent=percent, status_message=message,
            processed_count=processed, total_count=total, progress_unit=unit,
            workload_class=workload,
        )
        last_percent = percent
        if processed is not None:
            last_processed = processed

    def cancelled() -> bool:
        return cancellation_check is not None and cancellation_check()

    try:
        run = repository.fetch_search_run(search_run_id)
        if run is None or str(run.get("selection_contract_version")) != BUYER_SIMILARITY_SELECTION_CONTRACT_VERSION:
            raise Phase11RegistryStateError("The saved similarity search is unavailable.")
        validate_persisted_search_identity(run)
        context_row = CampaignTargetingContextRepository(path).fetch_context(
            int(run["targeting_context_id"])
        )
        if context_row is None:
            raise Phase11RegistryStateError("The saved campaign context is unavailable.")
        context = json.loads(context_row["campaign_context_json"])
        if run["status"] == "QUEUED":
            repository.mark_processing(search_run_id, **fence)
        elif run["status"] != "PROCESSING":
            raise Phase11RegistryStateError("The search attempt is no longer active.")
        with _heartbeat_during(repository, search_run_id, fence):
            progress("PREPARING_BUYER_PATTERNS", "Preparing buyer patterns", 8,
                     "Checking buyer patterns for the selected products.")
            resolution = resolve_similarity_context(path, context, project_root=root)
            missing = set(resolution.missing_products)
            unready = set(resolution.unready_products)
            built = False
            if missing or unready:
                with _heavy_slot_with_wait(progress):
                    if cancelled():
                        return SearchOrchestrationOutcome(search_run_id, "PROCESSING", waiting_on="CANCELLED")
                    # Rejoin a generation another worker may have completed while
                    # this attempt waited for the heavy-work slot.
                    resolution = resolve_similarity_context(path, context, project_root=root)
                    missing = set(resolution.missing_products)
                    unready = set(resolution.unready_products)
                    if missing or unready:
                        progress("PREPARING_BUYER_PATTERNS", "Preparing buyer patterns", 12,
                                 "Verifying the frozen buyer partition for this exact history.")
                        cohort = build_product_buyer_cohorts(
                            path, product_ids=context["product_ids"],
                            window_start=resolution.window_start,
                            window_end=resolution.window_end,
                            campaign_types=context.get("campaign_types"),
                            campaign_categories=context.get("campaign_categories"),
                            offer_types=context.get("offer_types"),
                            historical_campaign_channels=context.get("historical_campaign_channels"),
                            demographic_reference_date=resolution.window_end,
                            product_catalog_path=root / "data" / "product_master.csv",
                            expected_customer_source_checksum=resolution.source_identity["customers"][1],
                            expected_campaign_sales_source_checksum=resolution.source_identity["campaign_sales"][1],
                        )
                        unsupported = [item.product_id for item in cohort.manifest.product_support
                                       if item.status != "ELIGIBLE"]
                        if unsupported:
                            unresolved = cohort.manifest.split_status == "UNRESOLVED"
                            repository.fail_search_run(
                                search_run_id, **fence, blocked=True,
                                failure_code=("SPLIT_SOLVER_UNRESOLVED" if unresolved
                                              else "PROFILE_NOT_ELIGIBLE"),
                                failure_category=("CAPACITY" if unresolved
                                                  else "INSUFFICIENT_HISTORY"),
                                failure_summary=(
                                    "The exact buyer split could not be resolved within its bounded limit."
                                    if unresolved else
                                    "The selected products do not have a feasible shared buyer split."
                                ),
                                resolution_steps=(
                                    "Retry after capacity is available."
                                    if unresolved else
                                    "Import additional verified attributed-buyer history for the selected products.",
                                ), retryable=unresolved,
                            )
                            return SearchOrchestrationOutcome(search_run_id, "BLOCKED")
                        freeze_partition_manifest(cohort, project_root=root, database_path=path)
                        for product in sorted(missing):
                            if cancelled():
                                return SearchOrchestrationOutcome(search_run_id, "PROCESSING", waiting_on="CANCELLED")
                            artifact = fit_buyer_similarity_profile(cohort, product_id=product)
                            publish_buyer_similarity_profile(
                                path, artifact, project_root=root,
                                execution_owner=f"search-{search_run_id}",
                                execution_token=secrets.token_hex(32), now=_now(),
                                stale_before=_stale_before(),
                            )
                            built = True
                    resolution = resolve_similarity_context(path, context, project_root=root)
                    if resolution.missing_products:
                        raise SimilaritySelectionError("A supported buyer profile was not published.")
                    if resolution.unready_products:
                        profiles = {str(row["product_id"]): int(row["profile_id"])
                                    for row in resolution.profile_rows}
                        product_order = {
                            product_id: index for index, product_id in enumerate(
                                sorted(context["product_ids"])
                            )
                        }
                        for product in sorted(resolution.unready_products):
                            if cancelled():
                                return SearchOrchestrationOutcome(search_run_id, "PROCESSING", waiting_on="CANCELLED")
                            progress("SCORING_PROSPECTS", "Scoring potential customers", 30,
                                     "Scoring current potential customers against buyer patterns.",
                                     unit="score evaluations")

                            def scoring_progress(stage: str, processed: int, total: int,
                                                 message: str) -> None:
                                code = "VERIFYING_SIMILARITY" if stage in {"DEEP_VERIFY", "PUBLISH"} else "SCORING_PROSPECTS"
                                cumulative_processed = product_order[product] * total + processed
                                cumulative_total = len(product_order) * total
                                percent = 30 + min(40, int(40 * cumulative_processed / max(cumulative_total, 1)))
                                progress(code,
                                         "Verifying buyer similarity" if code == "VERIFYING_SIMILARITY" else "Scoring potential customers",
                                         percent, message, processed=cumulative_processed,
                                         total=cumulative_total, unit="score evaluations")

                            run_similarity_generation(
                                path, profiles[product], project_root=root,
                                execution_owner=f"search-{search_run_id}",
                                execution_token=secrets.token_hex(32),
                                stale_before=_stale_before(),
                                progress_callback=scoring_progress,
                                cancellation_check=cancelled,
                            )
                            built = True
            if cancelled():
                return SearchOrchestrationOutcome(search_run_id, "PROCESSING", waiting_on="CANCELLED")
            resolution = resolve_similarity_context(path, context, project_root=root)
            if not resolution.ready:
                raise SimilaritySelectionError("Current buyer similarity is not available.")
            progress("VERIFYING_SIMILARITY", "Verifying buyer similarity", 76,
                     "Checking the exact published score generation and source lineage.",
                     workload="NEW_INTELLIGENCE_BUILD" if built else "DIRECT_INTELLIGENCE_REUSE")
            repository.bind_similarity_lineage(
                search_run_id, **fence,
                profile_set_sha256=str(resolution.profile_set_sha256),
                composite_context_sha256=resolution.composite_context_sha256,
                similarity_generation_id=resolution.generation_ids[0],
            )
            run = repository.fetch_search_run(search_run_id)
            assert run is not None
            progress("SELECTING_CUSTOMERS", "Selecting potential customers", 80,
                     "Applying exact demographic and similarity selection.",
                     workload="NEW_RESULT_MATERIALIZATION")
            with get_connection(path) as connection:
                connection.execute("BEGIN")
                _, _, _, _, exact_count = count_similarity_selection(
                    connection, json.loads(run["filter_branches_json"]),
                    resolution.generation_ids, float(run["similarity_minimum"]),
                    selection_mode=run["selection_mode"], top_n=run["target_count"],
                )
            snapshot = find_similarity_result_snapshot(path, run, resolution, project_root=root)
            reused = snapshot is not None
            if snapshot is None:
                progress("MATERIALIZING_RESULT", "Saving result", 90,
                         "Saving the immutable customer membership snapshot.",
                         workload="NEW_RESULT_MATERIALIZATION")
                snapshot = materialize_similarity_result(
                    path, run, context, resolution, project_root=root,
                    **fence,
                )
            else:
                progress("REUSING_RESULT", "Reusing exact result", 90,
                         "Reopening the verified immutable result membership.",
                         workload="EXACT_RESULT_REUSE")
            if int(snapshot["resolved_count"]) != exact_count:
                raise SimilaritySelectionError("Exact count and saved membership differ.")
            after = resolve_similarity_context(path, context, project_root=root)
            if (not after.ready or after.composite_context_sha256 != resolution.composite_context_sha256
                or not validate_similarity_result_snapshot(snapshot, run, after, project_root=root)):
                raise SimilaritySelectionError("Source or result lineage changed before completion.")
            progress("VERIFYING_SIMILARITY", "Verifying result", 96,
                     "Checking result membership and source currentness.",
                     workload="EXACT_RESULT_REUSE" if reused else "NEW_RESULT_MATERIALIZATION")
            repository.complete_similarity_search_run(
                search_run_id, **fence,
                similarity_result_snapshot_id=int(snapshot["similarity_result_snapshot_id"]),
                result_source=("EXACT_RESULT_REUSE" if reused else
                               "NEW_INTELLIGENCE_BUILD" if built else "INTELLIGENCE_REUSE"),
            )
            return SearchOrchestrationOutcome(
                search_run_id, "COMPLETED", result_source=("EXACT_RESULT_REUSE" if reused else
                "NEW_INTELLIGENCE_BUILD" if built else "INTELLIGENCE_REUSE"),
                result_snapshot_id=int(snapshot["similarity_result_snapshot_id"]),
                generation_id=resolution.generation_ids[0],
            )
    except (BuyerSimilarityProfileLeaseBusy, BuyerSimilarityGenerationBusy):
        return SearchOrchestrationOutcome(
            search_run_id, "PROCESSING", waiting_on="SIMILARITY_DEPENDENCY"
        )
    except BuyerSimilarityScoringCancelled:
        return SearchOrchestrationOutcome(search_run_id, "PROCESSING", waiting_on="CANCELLED")
    except Phase11RegistryStateError:
        # A stale worker must not convert another attempt to failure.
        logger.info("Similarity search lease ended | search_run_id=%s", search_run_id)
        return SearchOrchestrationOutcome(search_run_id, "PROCESSING", waiting_on="CANCELLED")
    except Exception as exc:
        logger.exception("Similarity search failed | search_run_id=%s exception_type=%s",
                         search_run_id, type(exc).__name__)
        try:
            repository.fail_search_run(
                search_run_id, **fence, blocked=False,
                failure_code=("SIMILARITY_SOURCE_CHANGED" if isinstance(exc, SimilaritySelectionError)
                              else "SIMILARITY_PREPARATION_FAILED"),
                failure_category="PROCESSING_FAILURE",
                failure_summary="Buyer similarity could not be prepared from current verified data.",
                resolution_steps=(
                    "Refresh the current campaign choices and retry this saved search.",
                    "If the issue continues, ask an operator to review source and profile health.",
                ), retryable=True,
            )
        except Phase11RegistryStateError:
            return SearchOrchestrationOutcome(search_run_id, "PROCESSING", waiting_on="CANCELLED")
        return SearchOrchestrationOutcome(search_run_id, "FAILED")


__all__ = ("execute_similarity_search_safely",)
