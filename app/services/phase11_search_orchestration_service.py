"""Phase 11 three-layer search reuse orchestration.

This service owns decisions and durable search state.  It delegates Phase 10
compatibility to the frozen Phase 10 API service and membership artifact creation
to the Step 11 materializer boundary.  Exact-cache validation never scans the
propensity-score table.
"""
from __future__ import annotations

import hashlib
import json
import logging
import heapq
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.repositories.campaign_result_registry_repository import (
    CampaignResultRegistryRepository,
)
from app.repositories.phase10_intelligence_repository import (
    Phase10IntelligenceRepository,
)
from app.services.audience_query_service import (
    AUDIENCE_FILTER_CONTRACT_VERSION,
    AUDIENCE_RANK_CONTRACT_VERSION,
    AUDIENCE_SELECTION_CONTRACT_VERSION,
    search_audience,
)
from app.services.phase10_api_service import (
    get_phase10_preparation,
    prepare_phase10_targeting_intelligence,
)
from app.services.phase11_result_contracts import (
    RESULT_MEMBERSHIP_CONTRACT_VERSION,
    Phase11RegistryStateError,
    canonical_metadata_json,
)
from app.services.phase11_result_snapshot_service import validate_result_snapshot

logger = logging.getLogger(__name__)

RESULT_CACHE_KEY_CONTRACT_VERSION = "1"
DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REUSABLE_LIFECYCLES = frozenset({"CURRENT", "REUSABLE", "PROTECTED"})
_TERMINAL_SEARCH_STATES = frozenset({"COMPLETED", "BLOCKED", "FAILED"})

Phase10Reader = Callable[..., dict[str, Any]]
Phase10Preparer = Callable[..., dict[str, Any]]
SnapshotMaterializer = Callable[
    [Path, dict[str, Any], dict[str, Any], str, dict[str, Any] | None, Any], int
]
MembershipSource = Callable[[Path, Mapping[str, Any], Mapping[str, Any]], Any]


class Phase11SearchOrchestrationError(RuntimeError):
    """Search state or collaborator output is not safe to use."""


class Phase11SearchBlockedError(Phase11SearchOrchestrationError):
    """Current verified intelligence cannot satisfy the request."""


@dataclass(frozen=True)
class SearchOrchestrationOutcome:
    search_run_id: int
    status: str
    result_source: str | None = None
    result_snapshot_id: int | None = None
    generation_id: int | None = None
    waiting_on: str | None = None


def _canonical_json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            dict(value), ensure_ascii=True, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise Phase11SearchOrchestrationError(
            "Result cache identity is invalid."
        ) from exc


def _sha256_json(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def build_generation_fingerprint(generation: Mapping[str, Any]) -> str:
    """Hash immutable currentness/lineage fields from a verified generation."""

    fields = (
        "generation_id", "intelligence_generation_contract_version",
        "compatibility_contract_version", "intelligence_key_sha256",
        "modeling_context_sha256", "historical_filters_sha256",
        "customer_import_id", "customer_source_checksum",
        "campaign_sales_import_id", "campaign_sales_source_checksum",
        "demographic_import_id", "demographic_source_checksum",
        "feature_contract_version", "feature_contract_sha256",
        "model_role_policy_version", "evaluation_contract_version",
        "automated_training_policy_version", "analysis_run_id", "model_run_id",
        "scoring_run_id", "artifact_sha256", "score_semantics_sha256",
        "rank_contract_version", "analytics_contract_version",
        "lifecycle_policy_version",
    )
    if any(generation.get(field) is None for field in fields):
        raise Phase11SearchOrchestrationError(
            "READY generation lineage is incomplete."
        )
    return _sha256_json({field: generation[field] for field in fields})


def build_result_cache_key(
    run: Mapping[str, Any], generation: Mapping[str, Any]
) -> str:
    """Build the exact membership identity; delivery is deliberately absent."""

    required_run = (
        "targeting_criteria_sha256", "filter_branches_sha256",
        "selection_mode", "target_count", "modeling_context_sha256",
    )
    if any(field not in run for field in required_run):
        raise Phase11SearchOrchestrationError("Search identity is incomplete.")
    if run["modeling_context_sha256"] != generation.get("modeling_context_sha256"):
        raise Phase11SearchBlockedError(
            "Search and READY intelligence Modeling Context differ."
        )
    payload = {
        "result_cache_key_contract_version": RESULT_CACHE_KEY_CONTRACT_VERSION,
        "generation_id": generation["generation_id"],
        "generation_fingerprint_sha256": build_generation_fingerprint(generation),
        "targeting_criteria_sha256": run["targeting_criteria_sha256"],
        "filter_branches_sha256": run["filter_branches_sha256"],
        "selection_mode": run["selection_mode"],
        "target_count": run["target_count"],
        "audience_filter_contract_version": AUDIENCE_FILTER_CONTRACT_VERSION,
        "audience_selection_contract_version": AUDIENCE_SELECTION_CONTRACT_VERSION,
        "audience_rank_contract_version": AUDIENCE_RANK_CONTRACT_VERSION,
        "result_membership_contract_version": RESULT_MEMBERSHIP_CONTRACT_VERSION,
    }
    return _sha256_json(payload)


def validate_persisted_search_identity(run: Mapping[str, Any]) -> None:
    """Reopen the immutable normalized criteria/branches before any work."""

    try:
        criteria_json, criteria_sha = canonical_metadata_json(
            run["targeting_criteria_json"]
        )
        branches_json, branches_sha = canonical_metadata_json(
            run["filter_branches_json"], branches=True
        )
        criteria = json.loads(criteria_json)
    except (KeyError, TypeError, ValueError) as exc:
        raise Phase11SearchBlockedError("Persisted search identity is invalid.") from exc
    if (
        criteria_json != run["targeting_criteria_json"]
        or criteria_sha != run["targeting_criteria_sha256"]
        or branches_json != run["filter_branches_json"]
        or branches_sha != run["filter_branches_sha256"]
        or criteria.get("selection_mode", run["selection_mode"])
        != run["selection_mode"]
        or criteria.get("target_count", run["target_count"]) != run["target_count"]
    ):
        raise Phase11SearchBlockedError("Persisted search identity is invalid.")


def _validated_member(row: Mapping[str, Any]) -> dict[str, Any]:
    try:
        person_id = row["person_id"]
        score = float(row["propensity_score"])
        percentile = int(row["percentile_bucket"])
        decile = int(row["decile"])
        rank_band = row["rank_band"]
    except (KeyError, TypeError, ValueError) as exc:
        raise Phase11SearchOrchestrationError(
            "Audience Engine returned invalid membership."
        ) from exc
    if (
        not isinstance(person_id, str) or not person_id
        or not math.isfinite(score) or not 0.0 <= score <= 1.0
        or not 1 <= percentile <= 100 or not 1 <= decile <= 10
        or not isinstance(rank_band, str) or not rank_band
    ):
        raise Phase11SearchOrchestrationError(
            "Audience Engine returned invalid membership."
        )
    return {
        "person_id": person_id, "propensity_score": score,
        "percentile_bucket": percentile, "decile": decile,
        "rank_band": rank_band,
    }


def _branch_members(
    database_path: Path,
    scoring_run_id: int,
    branch: Mapping[str, Any],
    *,
    audience_search: Callable[..., dict[str, Any]],
):
    cursor = None
    seen_cursors: set[str] = set()
    while True:
        request = {
            "scoring_run_id": scoring_run_id,
            "filters": dict(branch),
            "page_size": 100,
            "cursor": cursor,
        }
        response = audience_search(database_path, request)
        if response.get("scoring_run_id") != scoring_run_id:
            raise Phase11SearchOrchestrationError(
                "Audience Engine lineage changed during filtering."
            )
        rows = response.get("rows")
        if not isinstance(rows, list) or len(rows) > 100:
            raise Phase11SearchOrchestrationError(
                "Audience Engine returned an invalid page."
            )
        for row in rows:
            if not isinstance(row, Mapping):
                raise Phase11SearchOrchestrationError(
                    "Audience Engine returned invalid membership."
                )
            yield _validated_member(row)
        if not response.get("has_more"):
            if response.get("next_cursor") is not None:
                raise Phase11SearchOrchestrationError(
                    "Audience Engine pagination is invalid."
                )
            return
        next_cursor = response.get("next_cursor")
        if (
            not isinstance(next_cursor, str) or not next_cursor
            or next_cursor == cursor or next_cursor in seen_cursors
        ):
            raise Phase11SearchOrchestrationError(
                "Audience Engine pagination is invalid."
            )
        seen_cursors.add(next_cursor)
        cursor = next_cursor


def iter_selected_members(
    database_path: Path,
    run: Mapping[str, Any],
    generation: Mapping[str, Any],
    *,
    audience_search: Callable[..., dict[str, Any]] = search_audience,
):
    """K-way merge exact OR branches in global score/person order.

    Phase 9 branches contain AND predicates; the branch list is their exact OR.
    At most 49 paged iterators are live and TOP_N stops without materializing the
    remaining rows.  Adjacent identity de-duplication safely handles overlapping
    externally seeded branches without a population-sized in-memory set.
    """

    try:
        branches = json.loads(str(run["filter_branches_json"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise Phase11SearchBlockedError("Persisted filter branches are invalid.") from exc
    if not isinstance(branches, list) or not 1 <= len(branches) <= 49:
        raise Phase11SearchBlockedError("Persisted filter branches are invalid.")
    scoring_run_id = int(generation["scoring_run_id"])
    iterators = [
        iter(_branch_members(
            database_path, scoring_run_id, branch,
            audience_search=audience_search,
        ))
        for branch in branches
    ]
    heap: list[tuple[float, str, int, dict[str, Any]]] = []
    for index, iterator in enumerate(iterators):
        try:
            row = next(iterator)
        except StopIteration:
            continue
        heapq.heappush(
            heap, (-row["propensity_score"], row["person_id"], index, row)
        )
    target = run.get("target_count") if run.get("selection_mode") == "TOP_N" else None
    emitted = 0
    last_identity: tuple[float, str] | None = None
    while heap and (target is None or emitted < int(target)):
        negative_score, person_id, index, row = heapq.heappop(heap)
        identity = (negative_score, person_id)
        if identity != last_identity:
            yield row
            emitted += 1
            last_identity = identity
        try:
            following = next(iterators[index])
        except StopIteration:
            continue
        heapq.heappush(
            heap,
            (-following["propensity_score"], following["person_id"], index, following),
        )


def validate_exact_snapshot(
    snapshot: Mapping[str, Any],
    run: Mapping[str, Any],
    generation: Mapping[str, Any],
    cache_key: str,
    *,
    project_root: str | Path | None = None,
) -> bool:
    """Bounded-memory metadata/artifact verification; never reads score rows."""

    return validate_result_snapshot(
        snapshot,
        run,
        generation,
        cache_key,
        project_root=DEFAULT_PROJECT_ROOT if project_root is None else project_root,
    ).is_valid


def _ready_generation(
    database_path: Path,
    run: Mapping[str, Any],
    response: Mapping[str, Any],
) -> dict[str, Any]:
    details = response.get("technical_details")
    if not isinstance(details, Mapping) or not response.get("is_ready"):
        raise Phase11SearchOrchestrationError(
            "Phase 10 READY lineage is unavailable."
        )
    generation_id = details.get("generation_id")
    if isinstance(generation_id, bool) or not isinstance(generation_id, int):
        raise Phase11SearchOrchestrationError(
            "Phase 10 READY generation is unavailable."
        )
    generation = Phase10IntelligenceRepository(database_path).verify_generation_record(
        generation_id
    )
    if (
        generation["modeling_context_sha256"] != run["modeling_context_sha256"]
        or details.get("modeling_context_sha256") != run["modeling_context_sha256"]
        or any(
            details.get(field) != generation[field]
            for field in ("analysis_run_id", "model_run_id", "scoring_run_id")
        )
    ):
        raise Phase11SearchBlockedError(
            "Phase 10 READY lineage does not match the search."
        )
    return generation


def _result_source(response: Mapping[str, Any]) -> str:
    reuse = response.get("reuse_summary")
    if not isinstance(reuse, Mapping) or set(reuse) != {
        "analysis", "model", "scoring", "rank"
    }:
        raise Phase11SearchOrchestrationError(
            "Phase 10 reuse decision is unavailable."
        )
    if any(value not in {"REUSE", "BUILD"} for value in reuse.values()):
        raise Phase11SearchOrchestrationError(
            "Phase 10 reuse decision is invalid."
        )
    return (
        "NEW_INTELLIGENCE_BUILD"
        if any(value == "BUILD" for value in reuse.values())
        else "INTELLIGENCE_REUSE"
    )


def _phase10_state(
    database_path: Path,
    run: Mapping[str, Any],
    *,
    project_root: Path,
    reader: Phase10Reader,
    preparer: Phase10Preparer,
) -> tuple[str, dict[str, Any] | None, dict[str, Any]]:
    response = reader(
        database_path, int(run["targeting_context_id"]), project_root=project_root
    )
    status = str(response.get("status", ""))
    if status == "READY":
        return "READY", _ready_generation(database_path, run, response), response
    if status in {"QUEUED", "RUNNING"}:
        return "WAITING", None, response
    if status in {"BLOCKED", "FAILED"}:
        return status, None, response
    if status not in {"NOT_STARTED", "STALE"}:
        raise Phase11SearchOrchestrationError(
            "Phase 10 preparation state is invalid."
        )
    response = preparer(
        database_path, int(run["targeting_context_id"]), project_root=project_root
    )
    status = str(response.get("status", ""))
    if status == "READY":
        return "READY", _ready_generation(database_path, run, response), response
    if status in {"QUEUED", "RUNNING"}:
        return "WAITING", None, response
    if status in {"BLOCKED", "FAILED"}:
        return status, None, response
    raise Phase11SearchOrchestrationError(
        "Phase 10 preparation did not produce a durable state."
    )


def execute_phase11_search(
    database_path: str | Path,
    search_run_id: int,
    *,
    materializer: SnapshotMaterializer | None,
    project_root: str | Path | None = None,
    phase10_reader: Phase10Reader = get_phase10_preparation,
    phase10_preparer: Phase10Preparer = prepare_phase10_targeting_intelligence,
    membership_source: MembershipSource = iter_selected_members,
) -> SearchOrchestrationOutcome:
    """Advance one durable search through one bounded orchestration pass."""

    path = Path(database_path)
    root = DEFAULT_PROJECT_ROOT if project_root is None else Path(project_root)
    repository = CampaignResultRegistryRepository(path)
    run = repository.fetch_search_run(search_run_id)
    if run is None:
        raise Phase11RegistryStateError("Search was not found.")
    if run["status"] in _TERMINAL_SEARCH_STATES:
        return SearchOrchestrationOutcome(
            search_run_id, str(run["status"]), run.get("result_source"),
            run.get("result_snapshot_id"), run.get("generation_id"),
        )
    validate_persisted_search_identity(run)
    if run["status"] == "QUEUED":
        repository.mark_processing(search_run_id)
        run = repository.fetch_search_run(search_run_id)
        assert run is not None

    state, generation, response = _phase10_state(
        path, run, project_root=root,
        reader=phase10_reader, preparer=phase10_preparer,
    )
    if state == "WAITING":
        return SearchOrchestrationOutcome(
            search_run_id, "PROCESSING", waiting_on="PHASE10_INTELLIGENCE"
        )
    if state in {"BLOCKED", "FAILED"}:
        repository.fail_search_run(search_run_id, blocked=state == "BLOCKED")
        return SearchOrchestrationOutcome(search_run_id, state)
    assert generation is not None

    cache_key = build_result_cache_key(run, generation)
    snapshot = repository.find_snapshot_by_cache_key(cache_key)
    if snapshot is not None and validate_exact_snapshot(
        snapshot, run, generation, cache_key, project_root=root
    ):
        repository.update_snapshot_currentness(
            int(snapshot["result_snapshot_id"]), state="CURRENT"
        )
        repository.complete_search_run(
            search_run_id,
            result_snapshot_id=int(snapshot["result_snapshot_id"]),
            result_source="EXACT_RESULT_REUSE",
        )
        return SearchOrchestrationOutcome(
            search_run_id, "COMPLETED", "EXACT_RESULT_REUSE",
            int(snapshot["result_snapshot_id"]), int(generation["generation_id"]),
        )

    if snapshot is not None:
        repository.update_snapshot_currentness(
            int(snapshot["result_snapshot_id"]), state="STALE"
        )
    if materializer is None:
        return SearchOrchestrationOutcome(
            search_run_id, "PROCESSING", generation_id=int(generation["generation_id"]),
            waiting_on="RESULT_MATERIALIZER",
        )

    members = membership_source(path, run, generation)
    snapshot_id = materializer(
        path, run, generation, cache_key, snapshot, members
    )
    created = repository.fetch_snapshot(snapshot_id)
    if created is None or not validate_exact_snapshot(
        created, run, generation, cache_key, project_root=root
    ):
        raise Phase11SearchOrchestrationError(
            "Materialized result snapshot failed validation."
        )
    source = _result_source(response)
    repository.complete_search_run(
        search_run_id, result_snapshot_id=snapshot_id, result_source=source
    )
    return SearchOrchestrationOutcome(
        search_run_id, "COMPLETED", source, snapshot_id,
        int(generation["generation_id"]),
    )


def execute_phase11_search_safely(
    database_path: str | Path,
    search_run_id: int,
    **kwargs: Any,
) -> SearchOrchestrationOutcome:
    """Fail closed with registry-owned safe messages; never persist exceptions."""

    repository = CampaignResultRegistryRepository(database_path)
    try:
        return execute_phase11_search(database_path, search_run_id, **kwargs)
    except Phase11SearchBlockedError:
        current = repository.fetch_search_run(search_run_id)
        if current is not None and current["status"] in {"QUEUED", "PROCESSING"}:
            repository.fail_search_run(search_run_id, blocked=True)
        return SearchOrchestrationOutcome(search_run_id, "BLOCKED")
    except Exception:
        logger.exception("Phase 11 search orchestration failed | search_run_id=%s", search_run_id)
        current = repository.fetch_search_run(search_run_id)
        if current is not None and current["status"] in {"QUEUED", "PROCESSING"}:
            repository.fail_search_run(search_run_id)
        return SearchOrchestrationOutcome(search_run_id, "FAILED")


def resume_phase11_searches(
    database_path: str | Path,
    *,
    materializer: SnapshotMaterializer | None,
    limit: int = 100,
    **kwargs: Any,
) -> list[SearchOrchestrationOutcome]:
    """Boundedly poll durable queued/processing searches after work or restart."""

    repository = CampaignResultRegistryRepository(database_path)
    runs = repository.list_search_runs(status="PROCESSING", limit=limit)
    if len(runs) < limit:
        runs += repository.list_search_runs(status="QUEUED", limit=limit - len(runs))
    return [
        execute_phase11_search_safely(
            database_path, int(run["search_run_id"]),
            materializer=materializer, **kwargs,
        )
        for run in runs
    ]


__all__ = (
    "RESULT_CACHE_KEY_CONTRACT_VERSION",
    "Phase11SearchBlockedError",
    "Phase11SearchOrchestrationError",
    "SearchOrchestrationOutcome",
    "SnapshotMaterializer",
    "MembershipSource",
    "build_generation_fingerprint",
    "build_result_cache_key",
    "execute_phase11_search",
    "execute_phase11_search_safely",
    "iter_selected_members",
    "resume_phase11_searches",
    "validate_exact_snapshot",
    "validate_persisted_search_identity",
)
