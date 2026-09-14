"""Exact Phase 10 scoring, rank/analytics reuse, and READY generation bridge."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from string import hexdigits
from typing import Any, Literal

from app.jobs.prospect_scoring_worker import run_prospect_scoring_job
from app.ml.feature_contract import FEATURE_CONTRACT_SHA256, FEATURE_CONTRACT_VERSION
from app.ml.model_roles import MODEL_ROLE_POLICY_VERSION, PRIMARY_MODEL_NAME
from app.repositories.audience_rank_repository import AudienceRankRepository
from app.repositories.job_repository import JobRepository
from app.repositories.model_run_repository import ModelRunRepository
from app.repositories.phase10_intelligence_repository import (
    Phase10IntelligenceRepository,
    Phase10RepositoryStateError,
)
from app.repositories.prospect_scoring_repository import (
    DemographicImportProvenance,
    ProspectScoringRepository,
    ProspectScoringValidationError,
)
from app.repositories.scoring_repository import ScoringRepository
from app.schemas.phase10_intelligence import (
    PHASE10_AUTOMATED_TRAINING_POLICY_VERSION,
    PHASE10_COMPATIBILITY_CONTRACT_VERSION,
    PHASE10_HISTORICAL_WINDOW_POLICY_VERSION,
    PHASE10_INTELLIGENCE_GENERATION_CONTRACT_VERSION,
    PHASE10_LIFECYCLE_POLICY_VERSION,
    PHASE10_MULTI_PRODUCT_POSITIVE_POLICY_VERSION,
    PHASE10_TRAINING_ELIGIBILITY_POLICY_VERSION,
    ScoreSemanticsContract,
)
from app.services.audience_preparation_service import (
    AUDIENCE_ANALYTICS_CONTRACT_VERSION,
    DEFAULT_PREPARATION_SCAN_CHUNK_SIZE,
    DEFAULT_RANK_CONTRACT_VERSION,
    get_audience_preparation_status,
    run_audience_rank_preparation,
)
from app.services.historical_source_provenance_service import (
    resolve_current_historical_source_provenance,
)
from app.services.model_scoring_compatibility import (
    ModelScoreabilityValidationError,
    validate_scoreable_model,
)
from app.services.phase10_context_identity_service import (
    CompatibilityFingerprint,
    ModelingContextIdentity,
    build_scoring_compatibility_fingerprint,
    normalize_modeling_context,
)
from app.services.phase10_historical_resolution_service import (
    HistoricalAnalysisResolution,
)
from app.services.phase10_model_resolution_service import Phase10ModelResolution
from app.services.prospect_scoring_service import (
    DEFAULT_SCORING_CHUNK_SIZE,
    ProspectScoringVerificationError,
    resolve_current_scoring_context_lightweight,
    validate_completed_scoring_run_integrity_deep,
)


ScoringResolutionStatus = Literal["READY", "BLOCKED"]
SCORING_SCORE_SEMANTICS_NAME = "LOOK_ALIKE_PROPENSITY_SCORE"


class Phase10ScoringResolutionError(RuntimeError):
    """Raised when scoring/rank compatibility cannot be resolved safely."""


class Phase10ScoringValidationError(Phase10ScoringResolutionError):
    """Raised when a persisted scoring candidate is not exactly reusable."""

    def __init__(self, reason_codes: tuple[str, ...]) -> None:
        super().__init__(
            "The scoring run is not compatible with the current Phase 10 contract: "
            + ", ".join(reason_codes)
        )
        self.reason_codes = reason_codes


@dataclass(frozen=True)
class ScoringCandidateRecord:
    scoring_run_id: int


@dataclass(frozen=True)
class ScoringCandidateRejection(ScoringCandidateRecord):
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class RankAnalyticsReadiness:
    ready: bool
    boundary_count: int
    total_population: int
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class Phase10ScoringRankResolution:
    status: ScoringResolutionStatus
    analysis_run_id: int | None
    model_run_id: int | None
    scoring_run_id: int | None
    scoring_job_id: int | None
    scoring_reused: bool
    scoring_built: bool
    rank_reused: bool
    rank_rebuilt: bool
    scoring_compatibility: CompatibilityFingerprint | None
    compatible_candidates: tuple[ScoringCandidateRecord, ...]
    rejected_candidates: tuple[ScoringCandidateRejection, ...]
    readiness: RankAnalyticsReadiness | None
    business_message: str


SynchronousScoringWorker = Callable[..., None]
ScoringProgressObserver = Callable[[str, int, str | None], None]


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


def _sha256_json(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _decode_json_object(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _append_reason(reasons: list[str], code: str) -> None:
    if code not in reasons:
        reasons.append(code)


def _current_demographic_provenance(
    database_path: str | Path,
) -> DemographicImportProvenance:
    try:
        return ProspectScoringRepository(
            database_path
        ).fetch_completed_demographic_import_provenance()
    except ProspectScoringValidationError as exc:
        raise Phase10ScoringResolutionError(
            "Current demographic provenance is unavailable for Phase 10 scoring."
        ) from exc


def _scoring_reason_codes(
    database_path: str | Path,
    row: Mapping[str, Any],
    *,
    model_run_id: int,
    artifact_sha256: str,
    demographic: DemographicImportProvenance,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if row.get("status") != "COMPLETED":
        _append_reason(reasons, "STATUS_NOT_COMPLETED")
    if row.get("model_run_id") != model_run_id:
        _append_reason(reasons, "MODEL_LINK_MISMATCH")
    if row.get("artifact_sha256") != artifact_sha256:
        _append_reason(reasons, "ARTIFACT_MISMATCH")
    if (
        row.get("feature_contract_version") != FEATURE_CONTRACT_VERSION
        or row.get("feature_contract_sha256") != FEATURE_CONTRACT_SHA256
    ):
        _append_reason(reasons, "FEATURE_CONTRACT_MISMATCH")
    if (
        row.get("selected_candidate") != PRIMARY_MODEL_NAME
        or row.get("model_role_policy_version") != MODEL_ROLE_POLICY_VERSION
    ):
        _append_reason(reasons, "MODEL_GOVERNANCE_MISMATCH")

    summary = _decode_json_object(row.get("score_summary_json"))
    if summary is None or summary.get("score_semantics") != (
        SCORING_SCORE_SEMANTICS_NAME
    ):
        _append_reason(reasons, "SCORE_SEMANTICS_MISMATCH")
    if summary is None or (
        summary.get("demographic_import_id") != demographic.demographic_import_id
        or summary.get("demographic_source_checksum")
        != demographic.demographic_source_checksum
        or summary.get("demographic_snapshot_count")
        != demographic.demographic_snapshot_count
        or summary.get("demographic_min_person_id")
        != demographic.demographic_min_person_id
        or summary.get("demographic_max_person_id")
        != demographic.demographic_max_person_id
    ):
        _append_reason(reasons, "DEMOGRAPHIC_PROVENANCE_MISMATCH")

    scoring_run_id = int(row["scoring_run_id"])
    if row.get("status") == "COMPLETED":
        try:
            integrity = ScoringRepository(
                database_path
            ).fetch_phase10_score_integrity(scoring_run_id)
        except Exception:
            _append_reason(reasons, "SCORE_INTEGRITY_UNAVAILABLE")
        else:
            universe = demographic.demographic_snapshot_count
            if (
                integrity["score_count"] != universe
                or integrity["distinct_person_count"] != universe
                or integrity["missing_person_count"] != 0
                or integrity["extra_person_count"] != 0
                or row.get("scored_person_count") != universe
                or row.get("demographic_snapshot_count") != universe
            ):
                _append_reason(reasons, "INCOMPLETE_FULL_UNIVERSE")
            if integrity["duplicate_person_count"] != 0:
                _append_reason(reasons, "DUPLICATE_PERSON_SCORES")
            if integrity["invalid_score_count"] != 0:
                _append_reason(reasons, "INVALID_SCORE_VALUES")
        try:
            deep = validate_completed_scoring_run_integrity_deep(
                database_path,
                scoring_run_id=scoring_run_id,
                verify_current_source_match=True,
            )
        except Exception:
            _append_reason(reasons, "SCORING_DEEP_INTEGRITY_FAILED")
        else:
            if not deep.get("is_canonical") or deep.get("issues"):
                _append_reason(reasons, "SCORING_DEEP_INTEGRITY_FAILED")
        try:
            currentness = resolve_current_scoring_context_lightweight(
                database_path,
                scoring_run_id=scoring_run_id,
                verify_current_source_match=True,
            )
        except (ProspectScoringVerificationError, ValueError, TypeError):
            _append_reason(reasons, "CANONICAL_CURRENTNESS_FAILED")
        else:
            if not currentness.get("is_canonical"):
                _append_reason(reasons, "CANONICAL_CURRENTNESS_FAILED")
    else:
        _append_reason(reasons, "SCORE_INTEGRITY_UNAVAILABLE")
    return tuple(reasons)


def _rank_analytics_readiness(
    database_path: str | Path,
    *,
    scoring_run_id: int,
    population_count: int,
) -> RankAnalyticsReadiness:
    boundaries = AudienceRankRepository(database_path).fetch_boundaries(scoring_run_id)
    reasons: list[str] = []
    if len(boundaries) != 100:
        _append_reason(reasons, "RANK_BOUNDARY_COUNT_MISMATCH")
    else:
        for bucket, row in enumerate(boundaries, start=1):
            expected_rank = max(1, math.ceil((population_count * bucket) / 100))
            score = row.get("boundary_score")
            if (
                row.get("percentile_bucket") != bucket
                or row.get("boundary_rank") != expected_rank
                or row.get("total_population") != population_count
                or row.get("rank_contract_version") != DEFAULT_RANK_CONTRACT_VERSION
                or isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not math.isfinite(float(score))
                or not 0 <= float(score) <= 1
                or not isinstance(row.get("boundary_person_id"), str)
                or not row["boundary_person_id"].strip()
            ):
                _append_reason(reasons, "RANK_BOUNDARY_CONTRACT_MISMATCH")
                break
    try:
        status = get_audience_preparation_status(
            database_path,
            scoring_run_id=scoring_run_id,
            rank_contract_version=DEFAULT_RANK_CONTRACT_VERSION,
        )
    except Exception:
        _append_reason(reasons, "ANALYTICS_CURRENTNESS_FAILED")
    else:
        if not status.get("analytics_prepared"):
            _append_reason(reasons, "ANALYTICS_SNAPSHOT_MISSING_OR_STALE")
        if not status.get("is_canonical") or not status.get("source_verified"):
            _append_reason(reasons, "RANK_ANALYTICS_PROVENANCE_DRIFT")
        if not status.get("ready_for_current_audience_actions"):
            _append_reason(reasons, "AUDIENCE_ACTIONS_NOT_READY")
    return RankAnalyticsReadiness(
        ready=not reasons,
        boundary_count=len(boundaries),
        total_population=population_count,
        reason_codes=tuple(reasons),
    )


def get_phase10_rank_analytics_readiness(
    database_path: str | Path,
    scoring_run_id: int,
) -> RankAnalyticsReadiness:
    """Read and verify rank/analytics state for one current scoring run."""

    demographic = _current_demographic_provenance(database_path)
    return _rank_analytics_readiness(
        database_path,
        scoring_run_id=scoring_run_id,
        population_count=demographic.demographic_snapshot_count,
    )


def _run_synchronous_scoring(
    database_path: str | Path,
    *,
    model_run_id: int,
    project_root: str | Path | None,
    chunk_size: int,
    scoring_worker: SynchronousScoringWorker,
    progress_observer: ScoringProgressObserver | None,
) -> tuple[int, int]:
    repository = JobRepository(database_path)
    job_id = repository.create_scoring_job(
        created_at=_utc_timestamp(),
        request_payload={"model_run_id": model_run_id},
        message="Phase 10 governed prospect scoring queued.",
    )
    # Direct in-process invocation prevents parent-worker self-deadlock while
    # preserving the existing durable child-job and scoring-run lifecycles.
    scoring_worker(
        database_path,
        job_id,
        project_root=project_root,
        chunk_size=chunk_size,
        progress_observer=progress_observer,
    )
    job = repository.fetch_job(job_id)
    scoring = ScoringRepository(database_path).fetch_by_job_id(job_id)
    if (
        job is None
        or job.get("status") != "COMPLETED"
        or scoring is None
        or scoring.get("status") != "COMPLETED"
    ):
        raise Phase10ScoringResolutionError(
            "Governed Phase 10 prospect scoring did not complete successfully."
        )
    return job_id, int(scoring["scoring_run_id"])


def _validated_current_model(
    database_path: str | Path,
    model_resolution: Phase10ModelResolution,
    *,
    project_root: str | Path | None,
):
    if (
        model_resolution.status != "READY"
        or model_resolution.model_run_id is None
        or model_resolution.model_compatibility is None
    ):
        raise Phase10ScoringResolutionError(
            "Phase 10 scoring requires a READY compatible model."
        )
    try:
        model = validate_scoreable_model(
            database_path,
            model_resolution.model_run_id,
            project_root=project_root,
        )
    except ModelScoreabilityValidationError as exc:
        raise Phase10ScoringResolutionError(
            "The Phase 10 model failed mandatory validation before scoring."
        ) from exc
    model_row = ModelRunRepository(database_path).fetch_run(
        model_resolution.model_run_id
    )
    if (
        model_row is None
        or model_row.get("artifact_sha256") != model.artifact_sha256
    ):
        raise Phase10ScoringResolutionError(
            "The model artifact identity is inconsistent."
        )
    return model


def validate_phase10_scoring_candidate(
    database_path: str | Path,
    scoring_run_id: int,
    model_resolution: Phase10ModelResolution,
    *,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Apply the complete Phase 10 reuse gate to one persisted scoring run."""

    if (
        isinstance(scoring_run_id, bool)
        or not isinstance(scoring_run_id, int)
        or scoring_run_id <= 0
    ):
        raise Phase10ScoringValidationError(("SCORING_RUN_NOT_FOUND",))
    model = _validated_current_model(
        database_path,
        model_resolution,
        project_root=project_root,
    )
    assert model_resolution.model_run_id is not None
    row = ScoringRepository(database_path).fetch_scoring_run(scoring_run_id)
    if row is None:
        raise Phase10ScoringValidationError(("SCORING_RUN_NOT_FOUND",))
    reasons = _scoring_reason_codes(
        database_path,
        row,
        model_run_id=model_resolution.model_run_id,
        artifact_sha256=model.artifact_sha256,
        demographic=_current_demographic_provenance(database_path),
    )
    if reasons:
        raise Phase10ScoringValidationError(reasons)
    return row


def resolve_or_build_phase10_scoring_rank(
    database_path: str | Path,
    model_resolution: Phase10ModelResolution,
    *,
    project_root: str | Path | None = None,
    scoring_chunk_size: int = DEFAULT_SCORING_CHUNK_SIZE,
    rank_chunk_size: int = DEFAULT_PREPARATION_SCAN_CHUNK_SIZE,
    scoring_worker: SynchronousScoringWorker = run_prospect_scoring_job,
    scoring_progress_observer: ScoringProgressObserver | None = None,
) -> Phase10ScoringRankResolution:
    """Reuse or build exact scoring, then reuse or rebuild rank/analytics only."""

    if (
        model_resolution.status != "READY"
        or model_resolution.analysis_run_id is None
        or model_resolution.model_run_id is None
        or model_resolution.model_compatibility is None
    ):
        return Phase10ScoringRankResolution(
            status="BLOCKED",
            analysis_run_id=model_resolution.analysis_run_id,
            model_run_id=model_resolution.model_run_id,
            scoring_run_id=None,
            scoring_job_id=None,
            scoring_reused=False,
            scoring_built=False,
            rank_reused=False,
            rank_rebuilt=False,
            scoring_compatibility=None,
            compatible_candidates=(),
            rejected_candidates=(),
            readiness=None,
            business_message=model_resolution.business_message,
        )
    model_run_id = model_resolution.model_run_id
    model = _validated_current_model(
        database_path,
        model_resolution,
        project_root=project_root,
    )

    demographic = _current_demographic_provenance(database_path)
    score_semantics = ScoreSemanticsContract()
    scoring_fingerprint = build_scoring_compatibility_fingerprint(
        model_fingerprint=model_resolution.model_compatibility,
        model_run_id=model_run_id,
        artifact_sha256=model.artifact_sha256,
        demographic_source_checksum=demographic.demographic_source_checksum,
        demographic_count=demographic.demographic_snapshot_count,
        score_semantics=score_semantics,
    )
    scoring_repository = ScoringRepository(database_path)
    compatible: list[ScoringCandidateRecord] = []
    rejected: list[ScoringCandidateRejection] = []
    for row in scoring_repository.list_model_candidates(model_run_id):
        scoring_run_id = int(row["scoring_run_id"])
        reasons = _scoring_reason_codes(
            database_path,
            row,
            model_run_id=model_run_id,
            artifact_sha256=model.artifact_sha256,
            demographic=demographic,
        )
        if reasons:
            rejected.append(
                ScoringCandidateRejection(
                    scoring_run_id=scoring_run_id,
                    reason_codes=reasons,
                )
            )
        else:
            compatible.append(ScoringCandidateRecord(scoring_run_id=scoring_run_id))

    scoring_job_id: int | None = None
    scoring_built = False
    if compatible:
        scoring_run_id = compatible[0].scoring_run_id
        scoring_reused = True
    else:
        scoring_job_id, scoring_run_id = _run_synchronous_scoring(
            database_path,
            model_run_id=model_run_id,
            project_root=project_root,
            chunk_size=scoring_chunk_size,
            scoring_worker=scoring_worker,
            progress_observer=scoring_progress_observer,
        )
        scoring_reused = False
        scoring_built = True
        fresh_row = scoring_repository.fetch_scoring_run(scoring_run_id)
        assert fresh_row is not None
        reasons = _scoring_reason_codes(
            database_path,
            fresh_row,
            model_run_id=model_run_id,
            artifact_sha256=model.artifact_sha256,
            demographic=demographic,
        )
        if reasons:
            raise Phase10ScoringResolutionError(
                "Fresh Phase 10 scoring failed compatibility validation: "
                + ", ".join(reasons)
            )

    readiness = _rank_analytics_readiness(
        database_path,
        scoring_run_id=scoring_run_id,
        population_count=demographic.demographic_snapshot_count,
    )
    rank_rebuilt = False
    if not readiness.ready:
        run_audience_rank_preparation(
            database_path,
            scoring_run_id=scoring_run_id,
            rank_contract_version=DEFAULT_RANK_CONTRACT_VERSION,
            chunk_size=rank_chunk_size,
        )
        rank_rebuilt = True
        readiness = _rank_analytics_readiness(
            database_path,
            scoring_run_id=scoring_run_id,
            population_count=demographic.demographic_snapshot_count,
        )
        if not readiness.ready:
            raise Phase10ScoringResolutionError(
                "Phase 10 rank and analytics preparation did not become current."
            )

    return Phase10ScoringRankResolution(
        status="READY",
        analysis_run_id=model_resolution.analysis_run_id,
        model_run_id=model_run_id,
        scoring_run_id=scoring_run_id,
        scoring_job_id=scoring_job_id,
        scoring_reused=scoring_reused,
        scoring_built=scoring_built,
        rank_reused=not rank_rebuilt,
        rank_rebuilt=rank_rebuilt,
        scoring_compatibility=scoring_fingerprint,
        compatible_candidates=tuple(compatible),
        rejected_candidates=tuple(rejected),
        readiness=readiness,
        business_message=(
            "Existing verified targeting intelligence matches this campaign and is ready."
            if scoring_reused and not rank_rebuilt
            else "Targeting intelligence is ready."
        ),
    )


def build_phase10_intelligence_key(
    scoring_compatibility: CompatibilityFingerprint,
) -> str:
    if scoring_compatibility.kind != "SCORING_COMPATIBILITY":
        raise Phase10ScoringResolutionError(
            "Intelligence identity requires scoring compatibility."
        )
    return _sha256_json(
        {
            "intelligence_generation_contract_version": (
                PHASE10_INTELLIGENCE_GENERATION_CONTRACT_VERSION
            ),
            "scoring_compatibility_sha256": (
                scoring_compatibility.fingerprint_sha256
            ),
            "rank_contract_version": DEFAULT_RANK_CONTRACT_VERSION,
            "analytics_contract_version": AUDIENCE_ANALYTICS_CONTRACT_VERSION,
        }
    )


def register_or_reuse_phase10_generation(
    database_path: str | Path,
    modeling_context: ModelingContextIdentity | Mapping[str, Any],
    historical_resolution: HistoricalAnalysisResolution,
    model_resolution: Phase10ModelResolution,
    scoring_resolution: Phase10ScoringRankResolution,
    *,
    intelligence_key_sha256: str | None = None,
) -> tuple[int, bool]:
    """Register a complete READY generation, or reuse its exact verified record."""

    identity = (
        modeling_context
        if isinstance(modeling_context, ModelingContextIdentity)
        else normalize_modeling_context(modeling_context)
    )
    if (
        scoring_resolution.status != "READY"
        or scoring_resolution.readiness is None
        or not scoring_resolution.readiness.ready
        or scoring_resolution.scoring_run_id is None
        or scoring_resolution.scoring_compatibility is None
        or model_resolution.model_run_id is None
        or model_resolution.analysis_run_id is None
    ):
        raise Phase10ScoringResolutionError(
            "Only fully current scoring, rank, and analytics can register a generation."
        )
    historical_source = resolve_current_historical_source_provenance(database_path)
    demographic = _current_demographic_provenance(database_path)
    scoring_row = ScoringRepository(database_path).fetch_scoring_run(
        scoring_resolution.scoring_run_id
    )
    if scoring_row is None:
        raise Phase10ScoringResolutionError("READY scoring run was not found.")
    model_row = ModelRunRepository(database_path).fetch_run(model_resolution.model_run_id)
    if model_row is None:
        raise Phase10ScoringResolutionError("READY model run was not found.")

    score_semantics = ScoreSemanticsContract()
    score_semantics_payload = score_semantics.model_dump(mode="json")
    historical_filters_payload = historical_resolution.resolved_filters.model_dump(
        mode="json"
    )
    if intelligence_key_sha256 is None:
        intelligence_key = build_phase10_intelligence_key(
            scoring_resolution.scoring_compatibility
        )
    else:
        intelligence_key = intelligence_key_sha256.strip().lower()
        if len(intelligence_key) != 64 or any(
            character not in hexdigits for character in intelligence_key
        ):
            raise Phase10ScoringResolutionError(
                "The requested intelligence identity is invalid."
            )
    timestamp = _utc_timestamp()
    values: dict[str, Any] = {
        "intelligence_generation_contract_version": (
            PHASE10_INTELLIGENCE_GENERATION_CONTRACT_VERSION
        ),
        "compatibility_contract_version": PHASE10_COMPATIBILITY_CONTRACT_VERSION,
        "intelligence_key_sha256": intelligence_key,
        "modeling_context_json": identity.canonical_json,
        "modeling_context_sha256": identity.modeling_context_sha256,
        "historical_filters_json": _canonical_json(historical_filters_payload),
        "historical_filters_sha256": _sha256_json(historical_filters_payload),
        "historical_window_policy_version": PHASE10_HISTORICAL_WINDOW_POLICY_VERSION,
        "multi_product_positive_policy_version": (
            PHASE10_MULTI_PRODUCT_POSITIVE_POLICY_VERSION
        ),
        "training_eligibility_policy_version": (
            PHASE10_TRAINING_ELIGIBILITY_POLICY_VERSION
        ),
        "customer_import_id": historical_source.customer_import_id,
        "customer_source_checksum": historical_source.customer_source_checksum,
        "campaign_sales_import_id": historical_source.campaign_sales_import_id,
        "campaign_sales_source_checksum": (
            historical_source.campaign_sales_source_checksum
        ),
        "demographic_import_id": demographic.demographic_import_id,
        "demographic_source_checksum": demographic.demographic_source_checksum,
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "feature_contract_sha256": FEATURE_CONTRACT_SHA256,
        "model_role_policy_version": MODEL_ROLE_POLICY_VERSION,
        "evaluation_contract_version": model_resolution.model_compatibility.payload[
            "evaluation_contract_version"
        ],
        "automated_training_policy_version": (
            PHASE10_AUTOMATED_TRAINING_POLICY_VERSION
        ),
        "analysis_run_id": model_resolution.analysis_run_id,
        "model_run_id": model_resolution.model_run_id,
        "scoring_run_id": scoring_resolution.scoring_run_id,
        "artifact_sha256": model_row["artifact_sha256"],
        "score_semantics_json": _canonical_json(score_semantics_payload),
        "score_semantics_sha256": _sha256_json(score_semantics_payload),
        "rank_contract_version": DEFAULT_RANK_CONTRACT_VERSION,
        "analytics_contract_version": AUDIENCE_ANALYTICS_CONTRACT_VERSION,
        "lifecycle_policy_version": PHASE10_LIFECYCLE_POLICY_VERSION,
        "generation_status": "READY",
        "lifecycle_state": "CURRENT",
        "created_at": timestamp,
        "last_verified_at": timestamp,
        "last_used_at": timestamp,
    }
    repository = Phase10IntelligenceRepository(database_path)
    existing = repository.find_generation_by_intelligence_key(intelligence_key)
    immutable_fields = set(values) - {
        "lifecycle_state",
        "created_at",
        "last_verified_at",
        "last_used_at",
    }
    if (
        existing is not None
        and existing.get("lifecycle_state") in {"CURRENT", "REUSABLE", "PROTECTED"}
        and all(existing.get(field) == values[field] for field in immutable_fields)
    ):
        repository.verify_generation_record(int(existing["generation_id"]))
        repository.record_generation_verification(
            int(existing["generation_id"]),
            verified_at=timestamp,
        )
        repository.touch_generation_usage(
            int(existing["generation_id"]),
            used_at=timestamp,
        )
        return int(existing["generation_id"]), True
    return repository.insert_ready_generation(values), False


def finalize_phase10_ready_context(
    database_path: str | Path,
    *,
    targeting_context_id: int,
    orchestration_id: int,
    modeling_context: ModelingContextIdentity | Mapping[str, Any],
    historical_resolution: HistoricalAnalysisResolution,
    model_resolution: Phase10ModelResolution,
    scoring_resolution: Phase10ScoringRankResolution,
    intelligence_key_sha256: str | None = None,
    business_message: str | None = None,
) -> tuple[int, bool]:
    """Register/reuse generation and atomically publish both READY bindings."""

    identity = (
        modeling_context
        if isinstance(modeling_context, ModelingContextIdentity)
        else normalize_modeling_context(modeling_context)
    )
    generation_id, reused = register_or_reuse_phase10_generation(
        database_path,
        identity,
        historical_resolution,
        model_resolution,
        scoring_resolution,
        intelligence_key_sha256=intelligence_key_sha256,
    )
    assert scoring_resolution.scoring_run_id is not None
    assert model_resolution.analysis_run_id is not None
    assert model_resolution.model_run_id is not None
    try:
        Phase10IntelligenceRepository(database_path).finalize_ready_context(
            targeting_context_id=targeting_context_id,
            modeling_context_sha256=identity.modeling_context_sha256,
            orchestration_id=orchestration_id,
            generation_id=generation_id,
            analysis_run_id=model_resolution.analysis_run_id,
            model_run_id=model_resolution.model_run_id,
            scoring_run_id=scoring_resolution.scoring_run_id,
            business_message=(
                scoring_resolution.business_message
                if business_message is None
                else business_message
            ),
            timestamp=_utc_timestamp(),
        )
    except Phase10RepositoryStateError as exc:
        raise Phase10ScoringResolutionError(
            "The verified generation could not be bound to the campaign context."
        ) from exc
    return generation_id, reused


__all__ = (
    "Phase10ScoringRankResolution",
    "Phase10ScoringResolutionError",
    "Phase10ScoringValidationError",
    "RankAnalyticsReadiness",
    "ScoringCandidateRecord",
    "ScoringCandidateRejection",
    "build_phase10_intelligence_key",
    "finalize_phase10_ready_context",
    "get_phase10_rank_analytics_readiness",
    "register_or_reuse_phase10_generation",
    "resolve_or_build_phase10_scoring_rank",
    "validate_phase10_scoring_candidate",
)
