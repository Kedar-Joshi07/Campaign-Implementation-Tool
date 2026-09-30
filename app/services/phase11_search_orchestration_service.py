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
import time
from contextlib import contextmanager
from threading import Event, Lock, Thread
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
from app.database.connection import get_connection
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
    Phase11RegistryStateError,
    canonical_metadata_json,
    result_membership_contract_for_selection,
)
from app.services.phase11_result_snapshot_service import validate_result_snapshot
from app.services.intelligence_attestation_service import has_current_attestation
from app.services.calibrated_selection_contract_service import (
    CALIBRATED_SELECTION_CONTRACT_VERSION,
    build_branch_predicates,
)

logger = logging.getLogger(__name__)

RESULT_CACHE_KEY_CONTRACT_VERSION = "3"
DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REUSABLE_LIFECYCLES = frozenset({"CURRENT", "REUSABLE", "PROTECTED"})
_TERMINAL_SEARCH_STATES = frozenset({"COMPLETED", "BLOCKED", "FAILED"})
_PHASE10_HEAVY_GATE = Lock()
_SEARCH_HEARTBEAT_INTERVAL_SECONDS = 5.0

_PHASE10_STAGE_MAP = {
    "NOT_STARTED": ("CHECKING_CURRENT_INTELLIGENCE", "Checking current intelligence"),
    "QUEUED": ("WAITING_FOR_HEAVY_SLOT", "Waiting for intelligence processing capacity"),
    "CHECKING_COMPATIBILITY": ("CHECKING_CURRENT_INTELLIGENCE", "Checking current intelligence"),
    "RESOLVING_HISTORICAL_CONTEXT": ("PHASE10_ANALYSIS", "Analyzing verified campaign history"),
    "CHECKING_TRAINING_ELIGIBILITY": ("PHASE10_ANALYSIS", "Checking historical training eligibility"),
    "RESOLVING_MODEL": ("PHASE10_MODEL", "Preparing the targeting model"),
    "VALIDATING_MODEL": ("PHASE10_MODEL", "Validating the targeting model"),
    "RESOLVING_SCORING": ("PHASE10_SCORING", "Checking customer scoring coverage"),
    "SCORING_POTENTIAL_CUSTOMERS": ("PHASE10_SCORING", "Scoring potential customers"),
    "PREPARING_TARGET_GROUP": ("PHASE10_RANK_ANALYTICS", "Preparing ranking analytics"),
    "VERIFYING_FINAL_CURRENTNESS": ("PHASE10_RANK_ANALYTICS", "Verifying intelligence currentness"),
    "READY": ("PHASE10_RANK_ANALYTICS", "Targeting intelligence is ready"),
    "EXACT_INTELLIGENCE_REUSE": ("CHECKING_CURRENT_INTELLIGENCE", "Reusing current targeting intelligence"),
}

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


@contextmanager
def _heartbeat_during(
    repository: CampaignResultRegistryRepository,
    search_run_id: int,
    fence: Mapping[str, Any],
):
    """Keep liveness current without rewriting stage facts or event history."""

    stop = Event()

    def heartbeat() -> None:
        while not stop.wait(_SEARCH_HEARTBEAT_INTERVAL_SECONDS):
            try:
                repository.heartbeat_search_attempt(
                    search_run_id,
                    attempt_number=int(fence["attempt_number"]),
                    execution_lease_token=str(fence["execution_lease_token"]),
                )
            except Phase11RegistryStateError:
                return
            except Exception:
                logger.exception(
                    "Search heartbeat failed | search_run_id=%s", search_run_id
                )
                return

    thread = Thread(
        target=heartbeat,
        name=f"phase11-heartbeat-{search_run_id}",
        daemon=True,
    )
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=2.0)


def _phase10_workload(response: Mapping[str, Any]) -> str:
    reuse = response.get("reuse_summary")
    if not isinstance(reuse, Mapping):
        return "PHASE10_REUSE_WITH_VALIDATION"
    return (
        "NEW_INTELLIGENCE_BUILD"
        if any(value == "BUILD" for value in reuse.values())
        else "PHASE10_REUSE_WITH_VALIDATION"
    )


def _phase10_progress(response: Mapping[str, Any]) -> tuple[str, str, int, str]:
    source_stage = str(response.get("stage") or "CHECKING_COMPATIBILITY").upper()
    stage_code, stage_label = _PHASE10_STAGE_MAP.get(
        source_stage,
        ("CHECKING_CURRENT_INTELLIGENCE", "Checking current intelligence"),
    )
    source_progress = response.get("progress_percent", 0)
    if isinstance(source_progress, bool) or not isinstance(source_progress, int):
        source_progress = 0
    # Phase 10 owns 0-90 of the enclosing search. This is a cap, not a
    # wall-clock interpolation: the value remains source-derived.
    progress = min(90, max(2, source_progress))
    message = str(response.get("business_message") or stage_label)[:1000]
    return stage_code, stage_label, progress, message


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
    selection_contract_version = str(run.get("selection_contract_version") or "1")
    membership_contract_version = result_membership_contract_for_selection(
        selection_contract_version
    )
    payload = {
        "result_cache_key_contract_version": (
            RESULT_CACHE_KEY_CONTRACT_VERSION
            if selection_contract_version == "2"
            else "1"
        ),
        "generation_id": generation["generation_id"],
        "generation_fingerprint_sha256": build_generation_fingerprint(generation),
        "targeting_criteria_sha256": run["targeting_criteria_sha256"],
        "filter_branches_sha256": run["filter_branches_sha256"],
        "selection_mode": run["selection_mode"],
        "target_count": run["target_count"],
        "audience_filter_contract_version": AUDIENCE_FILTER_CONTRACT_VERSION,
        "audience_selection_contract_version": AUDIENCE_SELECTION_CONTRACT_VERSION,
        "audience_rank_contract_version": AUDIENCE_RANK_CONTRACT_VERSION,
        "result_membership_contract_version": membership_contract_version,
    }
    if selection_contract_version == "2":
        catalog_version = run.get("catalog_version")
        if not isinstance(catalog_version, str) or len(catalog_version) != 64:
            raise Phase11SearchOrchestrationError(
                "Calibrated result cache identity is incomplete."
            )
        payload.update(
            selection_contract_version=selection_contract_version,
            calibrated_selection_contract_version=(
                CALIBRATED_SELECTION_CONTRACT_VERSION
            ),
            propensity_bucket=run.get("propensity_bucket"),
            calibration_artifact_id=run.get("calibration_artifact_id"),
            catalog_version=catalog_version,
        )
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


def _validated_calibrated_member(row: Mapping[str, Any]) -> dict[str, Any]:
    try:
        person_id = row["person_id"]
        probability = float(row["calibrated_purchase_probability"])
        raw_score = float(row["raw_propensity_score"])
        probability_bucket = row["probability_bucket"]
        percentile = int(row["percentile_bucket"])
        decile = int(row["decile"])
        rank_band = row["rank_band"]
    except (KeyError, TypeError, ValueError) as exc:
        raise Phase11SearchOrchestrationError(
            "Calibrated selection returned invalid membership."
        ) from exc
    if (
        not isinstance(person_id, str) or not person_id
        or not math.isfinite(probability) or not 0.0 <= probability <= 1.0
        or not math.isfinite(raw_score) or not 0.0 <= raw_score <= 1.0
        or probability_bucket not in {"0.90", "0.80", "0.70", "0.60", "0.50"}
        or not 1 <= percentile <= 100 or not 1 <= decile <= 10
        or not isinstance(rank_band, str) or not rank_band
    ):
        raise Phase11SearchOrchestrationError(
            "Calibrated selection returned invalid membership."
        )
    return {
        "person_id": person_id,
        "calibrated_purchase_probability": probability,
        "probability_bucket": probability_bucket,
        "raw_propensity_score": raw_score,
        "percentile_bucket": percentile,
        "decile": decile,
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


def _calibrated_branch_members(
    database_path: Path,
    calibration_artifact_id: int,
    propensity_bucket: str,
    branch: Mapping[str, Any],
):
    """Stream one calibrated branch from a single prepared SQL cursor."""

    predicates, parameters = build_branch_predicates(
        branch,
        calibrated=True,
        calibration_artifact_id=calibration_artifact_id,
        propensity_bucket=propensity_bucket,
    )
    sql = f"""SELECT p.person_id,
                     p.calibrated_probability AS calibrated_purchase_probability,
                     p.propensity_bucket AS probability_bucket,
                     p.raw_score AS raw_propensity_score,
                     p.percentile_bucket,p.decile,p.rank_band
              FROM calibrated_propensity_scores AS p
              JOIN demographics AS d ON d.person_id=p.person_id
              WHERE {' AND '.join(predicates)}
              ORDER BY p.calibrated_probability DESC,p.person_id"""
    with get_connection(database_path) as connection:
        cursor = connection.execute(sql, tuple(parameters))
        while True:
            rows = cursor.fetchmany(5_000)
            if not rows:
                return
            for row in rows:
                yield _validated_calibrated_member(row)


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
    calibrated_selection = run.get("selection_contract_version") == "2"
    if calibrated_selection:
        calibration_id = run.get("calibration_artifact_id")
        propensity_bucket = run.get("propensity_bucket")
        if isinstance(calibration_id, bool) or not isinstance(calibration_id, int):
            raise Phase11SearchBlockedError("A promoted probability calibration is required.")
        if not isinstance(propensity_bucket, str):
            raise Phase11SearchBlockedError("A propensity bucket is required.")
        iterators = [
            iter(_calibrated_branch_members(
                database_path, calibration_id, propensity_bucket, branch
            ))
            for branch in branches
        ]
    else:
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
            heap,
            (
                -row[
                    "calibrated_purchase_probability"
                    if calibrated_selection else "propensity_score"
                ],
                row["person_id"], index, row,
            ),
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
            (
                -following[
                    "calibrated_purchase_probability"
                    if calibrated_selection else "propensity_score"
                ],
                following["person_id"], index, following,
            ),
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


def _direct_reuse_state(
    database_path: Path,
    run: Mapping[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    """Return bounded, currently attested reuse without entering heavy work."""

    candidates = Phase10IntelligenceRepository(database_path).find_generations_by_modeling_context(
        str(run["modeling_context_sha256"]), limit=10,
    )
    direct = next(
        (candidate for candidate in candidates
         if candidate["generation_status"] == "READY"
         and candidate["lifecycle_state"] in _REUSABLE_LIFECYCLES
         and has_current_attestation(database_path, candidate)),
        None,
    )
    if direct is None:
        return None
    with get_connection(database_path) as connection:
        dependency = connection.execute(
            """SELECT orchestration_id FROM phase10_orchestration_runs
               WHERE generation_id=? AND status='READY'
               ORDER BY orchestration_id DESC LIMIT 1""",
            (int(direct["generation_id"]),),
        ).fetchone()
    return "READY", direct, {
        "status": "READY", "progress_percent": 100,
        "stage": "EXACT_INTELLIGENCE_REUSE",
        "business_message": "Reusing compatible targeting intelligence.",
        "reuse_summary": {name: "REUSE" for name in ("analysis", "model", "scoring", "rank")},
        "technical_details": {
            key: direct[key] for key in (
                "generation_id", "modeling_context_sha256", "analysis_run_id",
                "model_run_id", "scoring_run_id",
            )
        } | (
            {"orchestration_id": int(dependency["orchestration_id"])}
            if dependency is not None else {}
        ),
        "is_ready": True,
    }


def _phase10_state(
    database_path: Path,
    run: Mapping[str, Any],
    *,
    project_root: Path,
    reader: Phase10Reader,
    preparer: Phase10Preparer,
) -> tuple[str, dict[str, Any] | None, dict[str, Any]]:
    """Run only the compatibility/preparation path that may perform heavy work."""

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


def _resolve_phase10_state(
    database_path: Path,
    run: Mapping[str, Any],
    *,
    project_root: Path,
    reader: Phase10Reader,
    preparer: Phase10Preparer,
    before_heavy_wait: Callable[[], None] | None = None,
) -> tuple[str, dict[str, Any] | None, dict[str, Any]]:
    """Resolve reuse before the heavy gate, then recheck after waiting for it."""

    direct = _direct_reuse_state(database_path, run)
    if direct is not None:
        return direct
    acquired = _PHASE10_HEAVY_GATE.acquire(blocking=False)
    if not acquired:
        if before_heavy_wait is not None:
            before_heavy_wait()
        _PHASE10_HEAVY_GATE.acquire()
    try:
        # Another worker may have published and attested the exact intelligence
        # while this worker waited. Rechecking is what prevents duplicate builds.
        direct = _direct_reuse_state(database_path, run)
        if direct is not None:
            return direct
        return _phase10_state(
            database_path,
            run,
            project_root=project_root,
            reader=reader,
            preparer=preparer,
        )
    finally:
        _PHASE10_HEAVY_GATE.release()


def execute_phase11_search(
    database_path: str | Path,
    search_run_id: int,
    *,
    attempt_number: int,
    execution_lease_token: str,
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
    fence = {
        "attempt_number": attempt_number,
        "execution_lease_token": execution_lease_token,
    }
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
        repository.mark_processing(search_run_id, **fence)
        run = repository.fetch_search_run(search_run_id)
        assert run is not None

    runtime = repository.fetch_search_runtime(search_run_id)
    if runtime is None or int(runtime["progress_percent"]) <= 3:
        repository.update_search_progress(
            search_run_id,
            **fence,
            stage_code="CHECKING_CURRENT_INTELLIGENCE",
            stage_label="Checking current intelligence",
            progress_percent=3,
            status_message="Checking current and reusable targeting intelligence.",
        )

    def waiting_for_heavy_slot() -> None:
        current = repository.fetch_search_runtime(search_run_id)
        repository.update_search_progress(
            search_run_id,
            **fence,
            stage_code="WAITING_FOR_HEAVY_SLOT",
            stage_label="Waiting for intelligence processing capacity",
            progress_percent=max(3, int(current["progress_percent"]) if current else 3),
            status_message=(
                "This search is active and waiting for the bounded intelligence "
                "processing slot."
            ),
            workload_class="NEW_INTELLIGENCE_BUILD",
        )

    with _heartbeat_during(repository, search_run_id, fence):
        state, generation, response = _resolve_phase10_state(
            path, run, project_root=root,
            reader=phase10_reader, preparer=phase10_preparer,
            before_heavy_wait=waiting_for_heavy_slot,
        )
    details = response.get("technical_details")
    orchestration_id = (
        details.get("orchestration_id")
        if isinstance(details, Mapping)
        else None
    )
    if (
        isinstance(orchestration_id, int)
        and not isinstance(orchestration_id, bool)
        and orchestration_id > 0
    ):
        repository.bind_phase10_dependency(
            search_run_id,
            **fence,
            orchestration_id=orchestration_id,
            dependency_status=(
                str(response.get("status"))
                if str(response.get("status")) in {
                    "NOT_STARTED", "QUEUED", "RUNNING", "READY", "BLOCKED", "FAILED", "STALE",
                }
                else "RUNNING"
            ),
            rejoined=False,
        )
    current_attempt = repository.fetch_current_attempt(search_run_id)
    dependency_rejoined = bool(
        current_attempt and current_attempt.get("phase10_dependency_rejoined")
    )
    stage_code, stage_label, source_progress, status_message = _phase10_progress(
        response
    )
    current_runtime = repository.fetch_search_runtime(search_run_id)
    mapped_progress = max(
        source_progress,
        int(current_runtime["progress_percent"]) if current_runtime else 0,
    )
    workload_class = (
        "DIRECT_INTELLIGENCE_REUSE"
        if str(response.get("stage")) == "EXACT_INTELLIGENCE_REUSE"
        else _phase10_workload(response)
    )
    if dependency_rejoined and state == "WAITING":
        status_message = (
            "Rejoined the existing targeting-intelligence preparation; "
            "waiting for it to finish."
        )
    repository.update_search_progress(
        search_run_id,
        **fence,
        stage_code=stage_code,
        stage_label=stage_label,
        progress_percent=mapped_progress,
        status_message=status_message,
        workload_class=workload_class,
    )
    if state == "WAITING":
        return SearchOrchestrationOutcome(
            search_run_id, "PROCESSING", waiting_on="PHASE10_INTELLIGENCE"
        )
    if state in {"BLOCKED", "FAILED"}:
        blocked = state == "BLOCKED"
        can_retry = bool(response.get("can_retry")) if not blocked else False
        failure_code = (
            "PHASE10_BUSINESS_BLOCKED"
            if blocked
            else (
                "PHASE10_TRANSIENT_FAILED"
                if can_retry
                else "PHASE10_PERMANENT_VALIDATION_FAILED"
            )
        )
        repository.fail_search_run(
            search_run_id,
            **fence,
            blocked=blocked,
            failure_code=failure_code,
            failure_category=(
                "BUSINESS_DATA_INSUFFICIENCY"
                if blocked
                else ("TRANSIENT_DEPENDENCY" if can_retry else "PERMANENT_VALIDATION")
            ),
            failure_summary=str(
                response.get("business_message")
                or (
                    "The saved targeting request does not have enough verified campaign history."
                    if blocked
                    else "Targeting intelligence could not be prepared safely."
                )
            )[:1000],
            resolution_steps=(
                (
                    "Review whether the selected products and historical campaign filters have enough completed history.",
                    "Broaden the historical criteria or load additional verified campaign history, then submit the search again.",
                )
                if blocked
                else (
                    "Wait until the application and source data are available, then submit the saved search again.",
                    "Use the search number when requesting support if the failure continues.",
                )
            ),
            retryable=can_retry,
            technical_reference=(
                f"P10-{orchestration_id}"
                if isinstance(orchestration_id, int) and orchestration_id > 0
                else failure_code
            ),
        )
        return SearchOrchestrationOutcome(search_run_id, state)
    assert generation is not None

    calibration_artifact_id = None
    if run.get("selection_contract_version") == "2":
        with get_connection(path) as connection:
            calibration = connection.execute(
                """SELECT calibration_artifact_id FROM score_calibration_artifacts
                   WHERE scoring_run_id=? AND status='PROMOTED'
                   ORDER BY promoted_at DESC,calibration_artifact_id DESC LIMIT 1""",
                (int(generation["scoring_run_id"]),),
            ).fetchone()
        if calibration is None:
            repository.fail_search_run(
                search_run_id,
                **fence,
                blocked=True,
                failure_code="CALIBRATED_PROPENSITY_NOT_READY",
                failure_category="CALIBRATION",
                failure_summary="Calibrated purchase probabilities are not ready for this targeting intelligence.",
                resolution_steps=(
                    "Prepare and promote a held-out probability calibration for the current scoring generation.",
                    "Retry this saved search after calibration completes.",
                ),
            )
            return SearchOrchestrationOutcome(search_run_id, "BLOCKED")
        calibration_artifact_id = int(calibration["calibration_artifact_id"])
    repository.bind_current_attempt_lineage(
        search_run_id,
        **fence,
        generation_id=int(generation["generation_id"]),
        scoring_run_id=int(generation["scoring_run_id"]),
        calibration_artifact_id=calibration_artifact_id,
    )
    run = repository.fetch_search_run(search_run_id)
    assert run is not None

    repository.update_search_progress(
        search_run_id,
        **fence,
        stage_code="CHECKING_RESULT_CACHE",
        stage_label="Checking for a reusable result",
        progress_percent=91,
        status_message="Checking whether this exact potential-customer result already exists.",
        workload_class=workload_class,
    )

    cache_key = build_result_cache_key(run, generation)
    snapshot = repository.find_snapshot_by_cache_key(cache_key)
    snapshot_is_valid = False
    if snapshot is not None:
        repository.update_search_progress(
            search_run_id,
            **fence,
            stage_code="VERIFYING_RESULT",
            stage_label="Verifying the reusable result",
            progress_percent=91,
            status_message="Verifying the cached result checksum, lineage, and manifest.",
            workload_class="EXACT_RESULT_REUSE",
        )
        with _heartbeat_during(repository, search_run_id, fence):
            snapshot_is_valid = validate_exact_snapshot(
                snapshot, run, generation, cache_key, project_root=root
            )
    if snapshot is not None and snapshot_is_valid:
        repository.update_snapshot_currentness(
            int(snapshot["result_snapshot_id"]), state="CURRENT"
        )
        repository.update_search_progress(
            search_run_id,
            **fence,
            stage_code="VERIFYING_RESULT",
            stage_label="Verifying the reusable result",
            progress_percent=99,
            status_message="Verifying the reused result before making it available.",
            processed_count=int(snapshot["resolved_count"]),
            total_count=int(snapshot["resolved_count"]),
            workload_class="EXACT_RESULT_REUSE",
        )
        repository.complete_search_run(
            search_run_id,
            **fence,
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

    repository.update_search_progress(
        search_run_id,
        **fence,
        stage_code="SELECTING_POTENTIAL_CUSTOMERS",
        stage_label="Selecting potential customers",
        progress_percent=92,
        status_message="Applying the saved targeting criteria to the ranked customer universe.",
        workload_class=(
            "TOP_N_MATERIALIZATION"
            if run.get("selection_mode") == "TOP_N"
            else "NEW_RESULT_MATERIALIZATION"
        ),
    )
    materialization_workload = (
        "TOP_N_MATERIALIZATION"
        if run.get("selection_mode") == "TOP_N"
        else "NEW_RESULT_MATERIALIZATION"
    )
    members = membership_source(path, run, generation)
    expected_total = (
        int(run["target_count"])
        if run.get("selection_mode") == "TOP_N" and run.get("target_count") is not None
        else None
    )

    def tracked_members():
        processed = 0
        last_update = time.monotonic()
        for member in members:
            processed += 1
            current = time.monotonic()
            if processed == 1 or processed % 1000 == 0 or current - last_update >= 1.0:
                progress = 94
                if expected_total:
                    progress = min(97, 92 + int(processed * 5 / expected_total))
                repository.update_search_progress(
                    search_run_id,
                    **fence,
                    stage_code="MATERIALIZING_RESULT",
                    stage_label="Building the result snapshot",
                    progress_percent=progress,
                    status_message=(
                        f"Processed {processed:,} potential customers into the governed result snapshot."
                    ),
                    processed_count=processed,
                    total_count=expected_total,
                    workload_class=materialization_workload,
                )
                last_update = current
            yield member

    with _heartbeat_during(repository, search_run_id, fence):
        snapshot_id = materializer(
            path, run, generation, cache_key, snapshot, tracked_members()
        )
        created = repository.fetch_snapshot(snapshot_id)
        if created is None:
            raise Phase11SearchOrchestrationError(
                "Materialized result snapshot is unavailable."
            )
        repository.update_search_progress(
            search_run_id,
            **fence,
            stage_code="VERIFYING_RESULT",
            stage_label="Verifying the completed result",
            progress_percent=99,
            status_message="Verifying result counts, checksum, lineage, and currentness.",
            processed_count=int(created["resolved_count"]),
            total_count=int(created["resolved_count"]),
            workload_class=materialization_workload,
        )
        if not validate_exact_snapshot(
            created, run, generation, cache_key, project_root=root
        ):
            raise Phase11SearchOrchestrationError(
                "Materialized result snapshot failed validation."
            )
    source = _result_source(response)
    repository.complete_search_run(
        search_run_id, **fence,
        result_snapshot_id=snapshot_id, result_source=source
    )
    return SearchOrchestrationOutcome(
        search_run_id, "COMPLETED", source, snapshot_id,
        int(generation["generation_id"]),
    )


def execute_phase11_search_safely(
    database_path: str | Path,
    search_run_id: int,
    *,
    attempt_number: int,
    execution_lease_token: str,
    **kwargs: Any,
) -> SearchOrchestrationOutcome:
    """Fail closed with registry-owned safe messages; never persist exceptions."""

    repository = CampaignResultRegistryRepository(database_path)
    fence = {
        "attempt_number": attempt_number,
        "execution_lease_token": execution_lease_token,
    }
    try:
        return execute_phase11_search(
            database_path, search_run_id, **fence, **kwargs
        )
    except Phase11SearchBlockedError:
        current = repository.fetch_search_run(search_run_id)
        if current is not None and current["status"] in {"QUEUED", "PROCESSING"}:
            try:
                repository.fail_search_run(
                    search_run_id,
                    **fence,
                    blocked=True,
                    failure_code="SAVED_SEARCH_NO_LONGER_VALID",
                    failure_category="SAVED_TARGETING_CRITERIA",
                    failure_summary="The saved targeting criteria can no longer be applied safely.",
                    resolution_steps=(
                        "Review the saved criteria against the currently available campaign choices.",
                        "Create a new search with current choices after correcting unavailable criteria.",
                    ),
                )
            except Phase11RegistryStateError:
                pass
        return SearchOrchestrationOutcome(search_run_id, "BLOCKED")
    except Exception:
        logger.exception("Phase 11 search orchestration failed | search_run_id=%s", search_run_id)
        current = repository.fetch_search_run(search_run_id)
        if current is not None and current["status"] in {"QUEUED", "PROCESSING"}:
            try:
                repository.fail_search_run(
                    search_run_id,
                    **fence,
                    failure_code="UNEXPECTED_SEARCH_PROCESSING_FAILURE",
                    failure_category="PROCESSING_FAILURE",
                    failure_summary="The search stopped while preparing a governed result.",
                    resolution_steps=(
                        "Wait until the application and source data are available, then submit the saved search again.",
                        "Use the search number when requesting support if the failure continues.",
                    ),
                )
            except Phase11RegistryStateError:
                pass
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
    outcomes: list[SearchOrchestrationOutcome] = []
    for run in runs:
        search_run_id = int(run["search_run_id"])
        fence = repository.claim_search_attempt(
            search_run_id, lease_owner="phase11-resume"
        )
        outcomes.append(
            execute_phase11_search_safely(
                database_path,
                search_run_id,
                **fence.as_kwargs(),
                materializer=materializer,
                **kwargs,
            )
        )
    return outcomes


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
