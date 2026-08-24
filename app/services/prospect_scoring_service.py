"""Direct chunked prospect scoring engine for Phase 5 Step 3."""

from __future__ import annotations

import math
import traceback
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

import numpy as np

from app.database.schema import initialize_database
from app.ml.feature_contract import validate_and_normalize_feature_frame
from app.ml.pu_estimators import positive_class_scores
from app.repositories.prospect_scoring_repository import (
    MAX_SCORING_CHUNK_LIMIT,
    ProspectPopulationSnapshot,
    ProspectScoringRepository,
)
from app.repositories.scoring_repository import (
    ScoringRepository,
    ScoringStateTransitionError,
    ScoringValidationError,
)
from app.services.model_scoring_compatibility import (
    ModelScoreabilityValidationError,
    transform_and_score_prospect_chunk,
    validate_scoreable_model,
)


SCORING_STAGE_VALIDATING_MODEL = "VALIDATING_MODEL"
SCORING_STAGE_PREPARING_SCORING_RUN = "PREPARING_SCORING_RUN"
SCORING_STAGE_SCORING_PROSPECTS = "SCORING_PROSPECTS"
SCORING_STAGE_FINALIZING_SCORES = "FINALIZING_SCORES"
SCORING_STAGE_VERIFYING_COMPLETENESS = "VERIFYING_COMPLETENESS"
SCORING_STAGE_COMPLETED = "COMPLETED"

DEFAULT_SCORING_CHUNK_SIZE = 25_000
MINIMUM_SCORING_CHUNK_SIZE = 1_000
SCORING_PROGRESS_MIN = 10
SCORING_PROGRESS_MAX = 90
MAXIMUM_INTERNAL_ERROR_LENGTH = 4_096
SCORE_COMPARISON_RELATIVE_TOLERANCE = 1e-12
SCORE_COMPARISON_ABSOLUTE_TOLERANCE = 1e-12

AGE_SEMANTICS_NOTE = (
    "For this synthetic POC, demographic age is treated as compatible prospect "
    "snapshot age and validated under the frozen 18-100 feature contract."
)

ProgressCallback = Callable[[str, int, str | None, int | None], None]


class ProspectScoringServiceError(RuntimeError):
    """Base class for direct scoring service failures."""


class ProspectScoringExecutionError(ProspectScoringServiceError):
    """Raised when chunked scoring fails after scoring run creation."""


class ProspectScoringVerificationError(ProspectScoringServiceError):
    """Raised when deterministic score verification fails."""


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _bounded_error(exc: Exception) -> str:
    diagnostic = traceback.format_exc()[-MAXIMUM_INTERNAL_ERROR_LENGTH:]
    if diagnostic.strip():
        return diagnostic
    return f"{type(exc).__name__}: {exc}"[:MAXIMUM_INTERNAL_ERROR_LENGTH]


def _validate_chunk_size(chunk_size: int) -> int:
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int):
        raise ModelScoreabilityValidationError("chunk_size must be an integer.")
    if not MINIMUM_SCORING_CHUNK_SIZE <= chunk_size <= MAX_SCORING_CHUNK_LIMIT:
        raise ModelScoreabilityValidationError(
            f"chunk_size must be between {MINIMUM_SCORING_CHUNK_SIZE} and "
            f"{MAX_SCORING_CHUNK_LIMIT}."
        )
    return chunk_size


def _matrix_storage_bytes(matrix: Any) -> int:
    if all(hasattr(matrix, attribute) for attribute in ("data", "indices", "indptr")):
        return int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes)
    return int(np.asarray(matrix).nbytes)


def _dynamic_progress(scored_count: int, total_count: int) -> int:
    if total_count <= 0:
        return SCORING_PROGRESS_MIN
    ratio = min(max(scored_count / total_count, 0.0), 1.0)
    progress_range = SCORING_PROGRESS_MAX - SCORING_PROGRESS_MIN
    return int(SCORING_PROGRESS_MIN + math.floor(ratio * progress_range))


def _emit_progress(
    callback: ProgressCallback | None,
    *,
    stage: str,
    progress_percent: int,
    message: str | None,
    scoring_run_id: int | None,
    state: dict[str, Any],
) -> None:
    if callback is None:
        return
    if state.get("stage") == stage and state.get("progress") == progress_percent:
        return
    callback(stage, progress_percent, message, scoring_run_id)
    state["stage"] = stage
    state["progress"] = progress_percent


def _validate_score_vector(scores: np.ndarray, *, expected_count: int) -> None:
    if scores.ndim != 1:
        raise ProspectScoringExecutionError("Scoring produced a non-vector score output.")
    if scores.shape[0] != expected_count:
        raise ProspectScoringExecutionError("Scoring produced an unexpected score length.")
    if not np.isfinite(scores).all():
        raise ProspectScoringExecutionError("Scoring produced non-finite values.")
    if (scores < 0).any() or (scores > 1).any():
        raise ProspectScoringExecutionError("Scoring produced values outside [0, 1].")


def _build_summary_payload(
    *,
    score_count: int,
    score_min: float,
    score_max: float,
    score_mean: float,
    total_seconds: float,
    chunk_size: int,
    chunk_count: int,
    largest_chunk_rows: int,
    largest_matrix_bytes: int,
    model_run_id: int,
    selected_candidate: str,
    model_role_policy_version: str,
    feature_contract_version: str,
    feature_contract_sha256: str,
    artifact_sha256: str,
) -> dict[str, Any]:
    safe_total_seconds = max(float(total_seconds), 0.0)
    rows_per_second = 0.0 if score_count == 0 or safe_total_seconds == 0 else score_count / safe_total_seconds
    return {
        "score_count": int(score_count),
        "score_min": float(score_min),
        "score_max": float(score_max),
        "score_mean": float(score_mean),
        "total_seconds": safe_total_seconds,
        "rows_per_second": float(rows_per_second),
        "chunk_size": int(chunk_size),
        "chunk_count": int(chunk_count),
        "largest_chunk_rows": int(largest_chunk_rows),
        "largest_transformed_matrix_bytes": int(largest_matrix_bytes),
        "model_run_id": int(model_run_id),
        "selected_candidate": selected_candidate,
        "model_role_policy_version": model_role_policy_version,
        "feature_contract_version": feature_contract_version,
        "feature_contract_sha256": feature_contract_sha256,
        "artifact_sha256": artifact_sha256,
        "score_semantics": "LOOK_ALIKE_PROPENSITY_SCORE",
        "age_semantics_note": AGE_SEMANTICS_NOTE,
    }


def _reconcile_completion(
    *,
    expected_snapshot: ProspectPopulationSnapshot,
    actual_snapshot: ProspectPopulationSnapshot,
    aggregates: dict[str, Any],
    last_person_id: str | None,
) -> None:
    if actual_snapshot.demographic_snapshot_count != expected_snapshot.demographic_snapshot_count:
        raise ProspectScoringExecutionError("Demographic snapshot count changed during scoring.")
    if actual_snapshot.demographic_min_person_id != expected_snapshot.demographic_min_person_id:
        raise ProspectScoringExecutionError("Demographic snapshot minimum person_id changed during scoring.")
    if actual_snapshot.demographic_max_person_id != expected_snapshot.demographic_max_person_id:
        raise ProspectScoringExecutionError("Demographic snapshot maximum person_id changed during scoring.")

    score_count = int(aggregates["score_count"])
    distinct_count = int(aggregates["distinct_person_count"])
    if score_count != expected_snapshot.demographic_snapshot_count:
        raise ProspectScoringExecutionError("Persisted score count does not match demographic snapshot count.")
    if distinct_count != expected_snapshot.demographic_snapshot_count:
        raise ProspectScoringExecutionError("Distinct scored person count does not match demographic snapshot count.")
    if last_person_id != expected_snapshot.demographic_max_person_id:
        raise ProspectScoringExecutionError("Final keyset cursor does not match demographic snapshot maximum person_id.")

    score_min = aggregates.get("score_min")
    score_max = aggregates.get("score_max")
    score_mean = aggregates.get("score_mean")
    if score_min is None or score_max is None or score_mean is None:
        raise ProspectScoringExecutionError("Score aggregates are incomplete.")
    if not (math.isfinite(score_min) and math.isfinite(score_max) and math.isfinite(score_mean)):
        raise ProspectScoringExecutionError("Score aggregates are not finite.")
    if not (0.0 <= score_min <= score_mean <= score_max <= 1.0):
        raise ProspectScoringExecutionError("Score aggregates violate [0, 1] ordering constraints.")


def run_chunked_prospect_scoring(
    database_path: str | Path,
    *,
    model_run_id: int,
    job_id: int,
    chunk_size: int = DEFAULT_SCORING_CHUNK_SIZE,
    project_root: str | Path | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Run bounded keyset scoring and persist propensity scores chunk-by-chunk."""
    normalized_chunk_size = _validate_chunk_size(chunk_size)
    initialized_path = initialize_database(database_path)

    progress_state: dict[str, Any] = {"stage": None, "progress": None}
    scoring_run_id: int | None = None
    scored_count = 0
    chunk_count = 0
    largest_chunk_rows = 0
    largest_matrix_bytes = 0
    running_score_min: float | None = None
    running_score_max: float | None = None
    running_score_sum = 0.0
    last_person_id: str | None = None
    started = perf_counter()

    scoring_repository = ScoringRepository(initialized_path)
    prospect_repository = ProspectScoringRepository(initialized_path)

    try:
        _emit_progress(
            progress_callback,
            stage=SCORING_STAGE_VALIDATING_MODEL,
            progress_percent=5,
            message="Validating scoreable model governance and artifact.",
            scoring_run_id=None,
            state=progress_state,
        )
        compatibility = validate_scoreable_model(
            initialized_path,
            model_run_id,
            project_root=project_root,
        )

        _emit_progress(
            progress_callback,
            stage=SCORING_STAGE_PREPARING_SCORING_RUN,
            progress_percent=10,
            message="Capturing prospect snapshot and creating scoring run.",
            scoring_run_id=None,
            state=progress_state,
        )
        snapshot = prospect_repository.fetch_prospect_snapshot()
        if snapshot.demographic_snapshot_count <= 0:
            raise ModelScoreabilityValidationError("Prospect scoring requires at least one demographic row.")

        scoring_run_id = scoring_repository.create_scoring_run(
            job_id=job_id,
            model_run_id=compatibility.model_run_id,
            created_at=_utc_timestamp(),
            demographic_snapshot_count=snapshot.demographic_snapshot_count,
            demographic_min_person_id=snapshot.demographic_min_person_id,
            demographic_max_person_id=snapshot.demographic_max_person_id,
            chunk_size=normalized_chunk_size,
            selected_candidate=compatibility.selected_candidate,
            model_role_policy_version=compatibility.model_role_policy_version,
            feature_contract_version=compatibility.feature_contract_version,
            feature_contract_sha256=compatibility.feature_contract_sha256,
            artifact_sha256=compatibility.artifact_sha256,
        )

        after_person_id: str | None = None
        while True:
            person_ids, raw_features = prospect_repository.fetch_scoring_chunk(
                after_person_id=after_person_id,
                limit=normalized_chunk_size,
            )
            if not person_ids:
                break

            normalized = validate_and_normalize_feature_frame(raw_features)
            matrix = compatibility.artifact_payload["preprocessor"].transform(normalized)
            scores = positive_class_scores(
                compatibility.artifact_payload["estimator"],
                matrix,
                require_unit_interval=True,
            )
            _validate_score_vector(scores, expected_count=len(person_ids))

            inserted = scoring_repository.insert_scores_chunk(
                scoring_run_id=scoring_run_id,
                model_run_id=compatibility.model_run_id,
                person_ids=person_ids,
                propensity_scores=scores.tolist(),
            )
            if inserted != len(person_ids):
                raise ProspectScoringExecutionError("Chunk insert count did not match input row count.")

            scored_count += inserted
            chunk_count += 1
            largest_chunk_rows = max(largest_chunk_rows, inserted)
            largest_matrix_bytes = max(largest_matrix_bytes, _matrix_storage_bytes(matrix))
            after_person_id = person_ids[-1]
            last_person_id = after_person_id

            chunk_min = float(np.min(scores))
            chunk_max = float(np.max(scores))
            chunk_sum = float(np.sum(scores, dtype=np.float64))
            running_score_min = chunk_min if running_score_min is None else min(running_score_min, chunk_min)
            running_score_max = chunk_max if running_score_max is None else max(running_score_max, chunk_max)
            running_score_sum += chunk_sum
            running_score_mean = running_score_sum / scored_count

            scoring_repository.update_counters(
                scoring_run_id=scoring_run_id,
                scored_person_count=scored_count,
                last_person_id=last_person_id,
                score_min=running_score_min,
                score_max=running_score_max,
                score_mean=running_score_mean,
            )

            _emit_progress(
                progress_callback,
                stage=SCORING_STAGE_SCORING_PROSPECTS,
                progress_percent=_dynamic_progress(scored_count, snapshot.demographic_snapshot_count),
                message=(
                    f"Scored {scored_count} of {snapshot.demographic_snapshot_count} prospects."
                ),
                scoring_run_id=scoring_run_id,
                state=progress_state,
            )

            del raw_features
            del normalized
            del matrix
            del scores

        _emit_progress(
            progress_callback,
            stage=SCORING_STAGE_FINALIZING_SCORES,
            progress_percent=94,
            message="Finalizing score aggregates.",
            scoring_run_id=scoring_run_id,
            state=progress_state,
        )
        aggregates = scoring_repository.fetch_score_aggregates(scoring_run_id)

        _emit_progress(
            progress_callback,
            stage=SCORING_STAGE_VERIFYING_COMPLETENESS,
            progress_percent=98,
            message="Verifying scored population completeness.",
            scoring_run_id=scoring_run_id,
            state=progress_state,
        )
        snapshot_after = prospect_repository.fetch_prospect_snapshot()
        _reconcile_completion(
            expected_snapshot=snapshot,
            actual_snapshot=snapshot_after,
            aggregates=aggregates,
            last_person_id=last_person_id,
        )

        total_seconds = perf_counter() - started
        summary_payload = _build_summary_payload(
            score_count=int(aggregates["score_count"]),
            score_min=float(aggregates["score_min"]),
            score_max=float(aggregates["score_max"]),
            score_mean=float(aggregates["score_mean"]),
            total_seconds=total_seconds,
            chunk_size=normalized_chunk_size,
            chunk_count=chunk_count,
            largest_chunk_rows=largest_chunk_rows,
            largest_matrix_bytes=largest_matrix_bytes,
            model_run_id=compatibility.model_run_id,
            selected_candidate=compatibility.selected_candidate,
            model_role_policy_version=compatibility.model_role_policy_version,
            feature_contract_version=compatibility.feature_contract_version,
            feature_contract_sha256=compatibility.feature_contract_sha256,
            artifact_sha256=compatibility.artifact_sha256,
        )
        scoring_repository.mark_completed(
            scoring_run_id=scoring_run_id,
            completed_at=_utc_timestamp(),
            scored_person_count=int(aggregates["score_count"]),
            score_min=float(aggregates["score_min"]),
            score_max=float(aggregates["score_max"]),
            score_mean=float(aggregates["score_mean"]),
            summary_payload=summary_payload,
        )

        _emit_progress(
            progress_callback,
            stage=SCORING_STAGE_COMPLETED,
            progress_percent=100,
            message="Prospect scoring completed.",
            scoring_run_id=scoring_run_id,
            state=progress_state,
        )
        return {
            "scoring_run_id": scoring_run_id,
            "scored_person_count": int(aggregates["score_count"]),
            "score_min": float(aggregates["score_min"]),
            "score_max": float(aggregates["score_max"]),
            "score_mean": float(aggregates["score_mean"]),
            "summary": summary_payload,
        }
    except ModelScoreabilityValidationError:
        raise
    except Exception as exc:
        if scoring_run_id is not None:
            try:
                scoring_repository.mark_failed(
                    scoring_run_id=scoring_run_id,
                    completed_at=_utc_timestamp(),
                    error_message=_bounded_error(exc),
                    summary_payload={
                        "partial_scored_person_count": scored_count,
                        "chunk_size": normalized_chunk_size,
                        "chunk_count": chunk_count,
                        "age_semantics_note": AGE_SEMANTICS_NOTE,
                    },
                )
            except (ScoringValidationError, ScoringStateTransitionError):
                pass
        raise ProspectScoringExecutionError("Prospect scoring failed.") from exc


def verify_scoring_run_sample(
    database_path: str | Path,
    *,
    scoring_run_id: int,
    sample_size: int = 128,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Deterministically re-score a bounded ordered sample and compare persisted scores."""
    if isinstance(sample_size, bool) or not isinstance(sample_size, int) or not 1 <= sample_size <= 1000:
        raise ModelScoreabilityValidationError("sample_size must be an integer between 1 and 1000.")

    initialized_path = initialize_database(database_path)
    scoring_repository = ScoringRepository(initialized_path)
    prospect_repository = ProspectScoringRepository(initialized_path)

    scoring_run = scoring_repository.fetch_scoring_run(scoring_run_id)
    if scoring_run is None:
        raise ProspectScoringVerificationError("Scoring run was not found.")
    if scoring_run["status"] != "COMPLETED":
        raise ProspectScoringVerificationError("Only a completed scoring run can be verified.")

    score_rows = scoring_repository.fetch_score_sample(
        scoring_run_id=scoring_run_id,
        limit=sample_size,
    )
    if not score_rows:
        raise ProspectScoringVerificationError("No persisted score rows are available for verification.")

    expected_person_ids = [str(row["person_id"]) for row in score_rows]
    expected_scores = np.asarray([float(row["propensity_score"]) for row in score_rows], dtype=np.float64)

    resolved_person_ids, raw_features = prospect_repository.fetch_features_for_person_ids(
        person_ids=expected_person_ids,
    )
    if resolved_person_ids != expected_person_ids:
        raise ProspectScoringVerificationError(
            "Verification sample demographics no longer match persisted score identities."
        )

    compatibility = validate_scoreable_model(
        initialized_path,
        int(scoring_run["model_run_id"]),
        project_root=project_root,
    )
    rescored = transform_and_score_prospect_chunk(
        artifact_payload=compatibility.artifact_payload,
        raw_features=raw_features,
    )

    if rescored.shape != expected_scores.shape:
        raise ProspectScoringVerificationError("Verification sample produced unexpected score length.")
    if not np.allclose(
        rescored,
        expected_scores,
        rtol=SCORE_COMPARISON_RELATIVE_TOLERANCE,
        atol=SCORE_COMPARISON_ABSOLUTE_TOLERANCE,
    ):
        max_abs_diff = float(np.max(np.abs(rescored - expected_scores)))
        raise ProspectScoringVerificationError(
            f"Deterministic sample re-score mismatch detected (max_abs_diff={max_abs_diff})."
        )

    return {
        "scoring_run_id": int(scoring_run_id),
        "sample_size": int(rescored.shape[0]),
        "max_abs_diff": float(np.max(np.abs(rescored - expected_scores))),
        "verified": True,
    }


__all__ = (
    "DEFAULT_SCORING_CHUNK_SIZE",
    "ProspectScoringExecutionError",
    "ProspectScoringServiceError",
    "ProspectScoringVerificationError",
    "run_chunked_prospect_scoring",
    "verify_scoring_run_sample",
)
