"""Deterministic audience rank preparation orchestration and helpers for Phase 6 Step 3."""

from __future__ import annotations

import math
import json
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories.audience_rank_repository import AudienceRankRepository
from app.repositories.job_repository import (
    ActiveComputeJobConflictError,
    JobRepository,
    JobValidationError,
)
from app.repositories.scoring_repository import (
    MAXIMUM_SCORE_SCAN_CHUNK_SIZE,
    MINIMUM_SCORE_SCAN_CHUNK_SIZE,
    ScoringRepository,
)
from app.services.prospect_scoring_service import (
    find_current_canonical_run_for_model,
    validate_completed_scoring_run_provenance,
)


DEFAULT_RANK_CONTRACT_VERSION = "1"
SUPPORTED_RANK_CONTRACT_VERSIONS = {DEFAULT_RANK_CONTRACT_VERSION}
DEFAULT_PREPARATION_SCAN_CHUNK_SIZE = 100_000
MAXIMUM_INTERNAL_ERROR_LENGTH = 4_096
MAXIMUM_CURRENTNESS_ISSUES = 5
MAXIMUM_CURRENTNESS_ISSUE_LENGTH = 160

SCORING_RUN_NOT_FOUND_MESSAGE = "The requested scoring run was not found."
SCORING_RUN_NOT_COMPLETED_MESSAGE = "The requested scoring run is not completed."
SCORING_RUN_NOT_CANONICAL_MESSAGE = (
    "The requested scoring run is not current for its model and source provenance."
)
SCORING_COUNT_MISMATCH_MESSAGE = "Scoring row count does not match completed scoring metadata."
EXISTING_AUDIENCE_PREPARATION_CONFLICT_MESSAGE = (
    "Audience rank boundaries already exist for this scoring run and contract."
)
ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE = "A compute job is already active."
AUDIENCE_PREPARATION_SUBMISSION_FAILURE_MESSAGE = "Audience preparation could not be completed."


class AudiencePreparationServiceError(RuntimeError):
    """Base class for audience preparation service failures."""


class AudiencePreparationValidationError(AudiencePreparationServiceError):
    """Raised when audience preparation request arguments are invalid."""


class AudiencePreparationConflictError(AudiencePreparationServiceError):
    """Raised when audience preparation conflicts with current persisted state."""


class AudiencePreparationSubmissionError(AudiencePreparationServiceError):
    """Raised when queue persistence succeeds but worker submission fails."""


@dataclass(frozen=True)
class RankBoundary:
    percentile_bucket: int
    boundary_rank: int
    boundary_score: float
    boundary_person_id: str
    total_population: int

    def to_row(self) -> dict[str, Any]:
        return {
            "percentile_bucket": self.percentile_bucket,
            "boundary_rank": self.boundary_rank,
            "boundary_score": self.boundary_score,
            "boundary_person_id": self.boundary_person_id,
            "total_population": self.total_population,
        }


@dataclass(frozen=True)
class PreparationMetrics:
    scanned_rows: int
    chunk_size: int
    chunk_count: int
    largest_chunk_rows: int
    runtime_seconds: float
    rows_per_second: float

    def to_payload(self) -> dict[str, Any]:
        return {
            "scanned_rows": int(self.scanned_rows),
            "chunk_size": int(self.chunk_size),
            "chunk_count": int(self.chunk_count),
            "largest_chunk_rows": int(self.largest_chunk_rows),
            "runtime_seconds": round(float(self.runtime_seconds), 6),
            "rows_per_second": round(float(self.rows_per_second), 6),
        }


WorkerSubmitter = Callable[[str | Path, int], Any]


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _bounded_internal_error(exc: Exception) -> str:
    diagnostic = traceback.format_exc()[-MAXIMUM_INTERNAL_ERROR_LENGTH:]
    if diagnostic.strip():
        return diagnostic
    return f"{type(exc).__name__}: {exc}"[:MAXIMUM_INTERNAL_ERROR_LENGTH]


def _public_job_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": int(row["job_id"]),
        "job_type": str(row["job_type"]),
        "status": str(row["status"]),
        "progress_percent": int(row["progress_percent"]),
        "stage": str(row["stage"]),
        "message": row.get("message"),
        "analysis_run_id": row.get("analysis_run_id"),
        "model_run_id": row.get("model_run_id"),
        "created_at": row["created_at"],
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
    }


def _compact_currentness_issue(issue: Any) -> str | None:
    if not isinstance(issue, str):
        return None
    normalized = issue.strip()
    if not normalized:
        return None
    if len(normalized) <= MAXIMUM_CURRENTNESS_ISSUE_LENGTH:
        return normalized
    return normalized[: MAXIMUM_CURRENTNESS_ISSUE_LENGTH - 3].rstrip() + "..."


def _bounded_currentness_issues(issues: list[Any]) -> list[str]:
    bounded: list[str] = []
    seen: set[str] = set()
    for issue in issues:
        compact = _compact_currentness_issue(issue)
        if compact is None or compact in seen:
            continue
        seen.add(compact)
        bounded.append(compact)
        if len(bounded) >= MAXIMUM_CURRENTNESS_ISSUES:
            break
    return bounded


def _resolve_run_currentness(
    database_path: str | Path,
    *,
    scoring_run_id: int,
    model_run_id: int,
) -> dict[str, Any]:
    issues: list[Any] = []
    source_verified = False
    is_canonical = False

    try:
        provenance = validate_completed_scoring_run_provenance(
            database_path,
            scoring_run_id=scoring_run_id,
            verify_current_source_match=True,
        )
    except Exception:
        provenance = None
        issues.append("Scoring provenance could not be validated.")

    if provenance is not None:
        is_canonical = bool(provenance.get("is_canonical"))
        historical_verified = bool(provenance.get("historical_source_verified"))
        demographic_verified = bool(provenance.get("demographic_source_verified"))
        source_verified = historical_verified and demographic_verified
        if not historical_verified:
            issues.append("Historical source provenance is stale for this scoring run.")
        if not demographic_verified:
            issues.append("Demographic source provenance is stale for this scoring run.")
        if not is_canonical:
            issues.extend(list(provenance.get("issues") or []))

    try:
        canonical_row = find_current_canonical_run_for_model(
            database_path,
            model_run_id=model_run_id,
        )
    except Exception:
        canonical_row = None
        issues.append("Current canonical scoring run could not be resolved.")

    if canonical_row is None or int(canonical_row["scoring_run_id"]) != scoring_run_id:
        is_canonical = False
        issues.append("Scoring run is not the current canonical run for this model.")

    return {
        "is_canonical": is_canonical,
        "source_verified": source_verified,
        "currentness_issues": _bounded_currentness_issues(issues),
    }


def _require_positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AudiencePreparationValidationError(f"{field_name} must be a positive integer.")
    return value


def _normalize_rank_contract_version(value: Any) -> str:
    if value is None:
        return DEFAULT_RANK_CONTRACT_VERSION
    if not isinstance(value, str):
        raise AudiencePreparationValidationError("rank_contract_version must be text.")
    normalized = value.strip()
    if not normalized:
        raise AudiencePreparationValidationError("rank_contract_version must not be blank.")
    if len(normalized) > 24:
        raise AudiencePreparationValidationError(
            "rank_contract_version must not exceed 24 characters."
        )
    if normalized not in SUPPORTED_RANK_CONTRACT_VERSIONS:
        raise AudiencePreparationValidationError(
            "rank_contract_version is not supported."
        )
    return normalized


def _normalize_scan_chunk_size(chunk_size: int) -> int:
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int):
        raise AudiencePreparationValidationError("scan_chunk_size must be an integer.")
    if not MINIMUM_SCORE_SCAN_CHUNK_SIZE <= chunk_size <= MAXIMUM_SCORE_SCAN_CHUNK_SIZE:
        raise AudiencePreparationValidationError(
            "scan_chunk_size must be between "
            f"{MINIMUM_SCORE_SCAN_CHUNK_SIZE} and {MAXIMUM_SCORE_SCAN_CHUNK_SIZE}."
        )
    return chunk_size


def _target_rank(total_population: int, bucket: int) -> int:
    base = math.ceil((total_population * bucket) / 100)
    return max(1, base)


def classify_percentile_bucket(
    score: float,
    person_id: str,
    boundaries: list[dict[str, Any]],
) -> int:
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise AudiencePreparationValidationError("score must be numeric.")
    normalized_score = float(score)
    if not math.isfinite(normalized_score) or not 0 <= normalized_score <= 1:
        raise AudiencePreparationValidationError("score must be finite and between 0 and 1.")
    if not isinstance(person_id, str) or not person_id.strip():
        raise AudiencePreparationValidationError("person_id must be a non-empty string.")
    normalized_person_id = person_id.strip()

    if len(boundaries) != 100:
        raise AudiencePreparationValidationError("boundaries must contain exactly 100 rows.")

    for row in boundaries:
        bucket = row.get("percentile_bucket")
        boundary_score = row.get("boundary_score")
        boundary_person_id = row.get("boundary_person_id")
        if isinstance(bucket, bool) or not isinstance(bucket, int) or not 1 <= bucket <= 100:
            raise AudiencePreparationValidationError("boundary percentile_bucket is invalid.")
        if isinstance(boundary_score, bool) or not isinstance(boundary_score, (int, float)):
            raise AudiencePreparationValidationError("boundary_score is invalid.")
        boundary_score = float(boundary_score)
        if not math.isfinite(boundary_score):
            raise AudiencePreparationValidationError("boundary_score must be finite.")
        if not isinstance(boundary_person_id, str) or not boundary_person_id.strip():
            raise AudiencePreparationValidationError("boundary_person_id is invalid.")

        # Sorted by score desc then person_id asc: first boundary at or below row is the row bucket.
        if normalized_score > boundary_score:
            return int(bucket)
        if normalized_score == boundary_score and normalized_person_id <= boundary_person_id:
            return int(bucket)

    return 100


def classify_decile(bucket: int) -> int:
    if isinstance(bucket, bool) or not isinstance(bucket, int) or not 1 <= bucket <= 100:
        raise AudiencePreparationValidationError("bucket must be an integer between 1 and 100.")
    return ((bucket - 1) // 10) + 1


def classify_rank_band(bucket: int) -> str:
    if isinstance(bucket, bool) or not isinstance(bucket, int) or not 1 <= bucket <= 100:
        raise AudiencePreparationValidationError("bucket must be an integer between 1 and 100.")
    if bucket == 1:
        return "ELITE"
    if bucket <= 5:
        return "VERY_HIGH"
    if bucket <= 10:
        return "HIGH"
    if bucket <= 25:
        return "MEDIUM"
    if bucket <= 50:
        return "LOW"
    return "VERY_LOW"


def _compute_boundaries_for_run(
    database_path: str | Path,
    *,
    scoring_run_id: int,
    chunk_size: int,
) -> tuple[list[RankBoundary], PreparationMetrics]:
    repository = ScoringRepository(database_path)
    scoring_run = repository.fetch_scoring_run(scoring_run_id)
    if scoring_run is None:
        raise AudiencePreparationValidationError(SCORING_RUN_NOT_FOUND_MESSAGE)

    total_population = int(scoring_run["scored_person_count"])
    if total_population <= 0:
        raise AudiencePreparationValidationError(SCORING_COUNT_MISMATCH_MESSAGE)

    targets = [_target_rank(total_population, bucket) for bucket in range(1, 101)]

    boundaries: list[RankBoundary] = []
    current_bucket_index = 0
    current_rank = 0
    cursor_score: float | None = None
    cursor_person_id: str | None = None
    scanned_rows = 0
    chunk_count = 0
    largest_chunk_rows = 0
    started = perf_counter()

    while current_bucket_index < 100:
        rows = repository.fetch_rank_scan_chunk(
            scoring_run_id=scoring_run_id,
            limit=chunk_size,
            after_score=cursor_score,
            after_person_id=cursor_person_id,
        )
        if not rows:
            break
        chunk_count += 1
        scanned_rows += len(rows)
        if len(rows) > largest_chunk_rows:
            largest_chunk_rows = len(rows)

        for row in rows:
            current_rank += 1
            row_score = float(row["propensity_score"])
            row_person_id = str(row["person_id"])

            while current_bucket_index < 100 and current_rank >= targets[current_bucket_index]:
                boundaries.append(
                    RankBoundary(
                        percentile_bucket=current_bucket_index + 1,
                        boundary_rank=current_rank,
                        boundary_score=row_score,
                        boundary_person_id=row_person_id,
                        total_population=total_population,
                    )
                )
                current_bucket_index += 1

            cursor_score = row_score
            cursor_person_id = row_person_id

    if current_bucket_index != 100:
        raise AudiencePreparationValidationError(SCORING_COUNT_MISMATCH_MESSAGE)
    if boundaries[-1].boundary_rank != total_population:
        raise AudiencePreparationValidationError(
            "The 100th percentile boundary rank must equal scored population."
        )

    runtime_seconds = max(0.0, perf_counter() - started)
    rows_per_second = (scanned_rows / runtime_seconds) if runtime_seconds > 0 else 0.0
    metrics = PreparationMetrics(
        scanned_rows=scanned_rows,
        chunk_size=chunk_size,
        chunk_count=chunk_count,
        largest_chunk_rows=largest_chunk_rows,
        runtime_seconds=runtime_seconds,
        rows_per_second=rows_per_second,
    )
    return boundaries, metrics


def _validate_preparation_inputs(
    database_path: str | Path,
    *,
    scoring_run_id: int,
    rank_contract_version: str,
) -> dict[str, Any]:
    scoring_repository = ScoringRepository(database_path)
    scoring_run = scoring_repository.fetch_scoring_run(scoring_run_id)
    if scoring_run is None:
        raise AudiencePreparationValidationError(SCORING_RUN_NOT_FOUND_MESSAGE)
    if scoring_run["status"] != "COMPLETED":
        raise AudiencePreparationConflictError(SCORING_RUN_NOT_COMPLETED_MESSAGE)

    aggregates = scoring_repository.fetch_score_aggregates(scoring_run_id)
    score_count = int(aggregates["score_count"])
    if score_count != int(scoring_run["scored_person_count"]):
        raise AudiencePreparationConflictError(SCORING_COUNT_MISMATCH_MESSAGE)

    provenance = validate_completed_scoring_run_provenance(
        database_path,
        scoring_run_id=scoring_run_id,
        verify_current_source_match=True,
    )
    if not provenance["is_canonical"]:
        raise AudiencePreparationConflictError(SCORING_RUN_NOT_CANONICAL_MESSAGE)

    canonical = find_current_canonical_run_for_model(
        database_path,
        model_run_id=int(scoring_run["model_run_id"]),
    )
    if canonical is None or int(canonical["scoring_run_id"]) != scoring_run_id:
        raise AudiencePreparationConflictError(SCORING_RUN_NOT_CANONICAL_MESSAGE)

    existing = AudienceRankRepository(database_path).fetch_boundaries(scoring_run_id)
    if (
        len(existing) == 100
        and all(str(row["rank_contract_version"]) == rank_contract_version for row in existing)
    ):
        raise AudiencePreparationConflictError(EXISTING_AUDIENCE_PREPARATION_CONFLICT_MESSAGE)

    return {
        "scoring_run_id": scoring_run_id,
        "model_run_id": int(scoring_run["model_run_id"]),
        "score_count": score_count,
    }


def submit_audience_preparation_job_request(
    database_path: str | Path | None,
    request_payload: dict[str, Any],
    *,
    submitter: WorkerSubmitter | None = None,
) -> dict[str, Any]:
    path = initialize_database(database_path)
    if not isinstance(request_payload, dict):
        raise AudiencePreparationValidationError("Audience preparation request must be a JSON object.")

    scoring_run_id = _require_positive_int(
        request_payload.get("scoring_run_id"),
        field_name="scoring_run_id",
    )
    rank_contract_version = _normalize_rank_contract_version(
        request_payload.get("rank_contract_version", DEFAULT_RANK_CONTRACT_VERSION)
    )

    _validate_preparation_inputs(
        path,
        scoring_run_id=scoring_run_id,
        rank_contract_version=rank_contract_version,
    )

    repository = JobRepository(path)
    if repository.find_active_compute_job() is not None:
        raise AudiencePreparationConflictError(ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE)

    try:
        job_id = repository.create_audience_preparation_job(
            created_at=_utc_timestamp(),
            request_payload={
                "scoring_run_id": scoring_run_id,
                "rank_contract_version": rank_contract_version,
            },
        )
    except ActiveComputeJobConflictError as exc:
        raise AudiencePreparationConflictError(ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE) from exc
    except JobValidationError as exc:
        raise AudiencePreparationValidationError(str(exc)) from exc

    worker_submitter = submit_audience_preparation_job if submitter is None else submitter
    try:
        if submitter is None:
            from app.jobs.executor import submit_audience_preparation_job

            worker_submitter = submit_audience_preparation_job
        else:
            worker_submitter = submitter
        worker_submitter(path, job_id)
    except Exception as exc:
        repository.mark_failed(
            job_id=job_id,
            finished_at=_utc_timestamp(),
            error_message=_bounded_internal_error(exc),
            model_run_id=None,
            message=AUDIENCE_PREPARATION_SUBMISSION_FAILURE_MESSAGE,
        )
        raise AudiencePreparationSubmissionError(AUDIENCE_PREPARATION_SUBMISSION_FAILURE_MESSAGE) from exc

    row = repository.fetch_job(job_id)
    if row is None:
        raise AudiencePreparationServiceError("Queued audience preparation job could not be reloaded.")
    return _public_job_summary(row)


def get_audience_preparation_status(
    database_path: str | Path,
    *,
    scoring_run_id: int,
    rank_contract_version: str = DEFAULT_RANK_CONTRACT_VERSION,
) -> dict[str, Any]:
    path = initialize_database(database_path)
    normalized_scoring_run_id = _require_positive_int(scoring_run_id, field_name="scoring_run_id")
    normalized_rank_contract_version = _normalize_rank_contract_version(rank_contract_version)

    scoring_row = ScoringRepository(path).fetch_scoring_run(normalized_scoring_run_id)
    if scoring_row is None:
        raise AudiencePreparationValidationError(SCORING_RUN_NOT_FOUND_MESSAGE)

    boundaries = AudienceRankRepository(path).fetch_boundaries(normalized_scoring_run_id)
    ready = (
        len(boundaries) == 100
        and all(
            str(row["rank_contract_version"]) == normalized_rank_contract_version
            for row in boundaries
        )
    )
    currentness = _resolve_run_currentness(
        path,
        scoring_run_id=normalized_scoring_run_id,
        model_run_id=int(scoring_row["model_run_id"]),
    )
    ready_for_current_actions = (
        ready
        and bool(currentness["is_canonical"])
        and bool(currentness["source_verified"])
    )

    active_job = JobRepository(path).find_active_compute_job()
    active_for_run: dict[str, Any] | None = None
    if active_job is not None and active_job.get("job_type") == "AUDIENCE_PREPARATION":
        request_json = active_job.get("request_json")
        if isinstance(request_json, str):
            try:
                request_payload = json.loads(request_json)
            except (TypeError, ValueError):
                request_payload = None
            if (
                isinstance(request_payload, dict)
                and request_payload.get("scoring_run_id") == normalized_scoring_run_id
            ):
                active_for_run = _public_job_summary(active_job)

    return {
        "scoring_run_id": normalized_scoring_run_id,
        "model_run_id": int(scoring_row["model_run_id"]),
        "status": str(scoring_row["status"]),
        "rank_contract_version": normalized_rank_contract_version,
        "prepared": ready,
        "is_canonical": bool(currentness["is_canonical"]),
        "source_verified": bool(currentness["source_verified"]),
        "ready_for_current_audience_actions": ready_for_current_actions,
        "currentness_issues": currentness["currentness_issues"],
        "boundary_count": len(boundaries),
        "total_population": (
            int(boundaries[0]["total_population"]) if boundaries else int(scoring_row["scored_person_count"])
        ),
        "active_job": active_for_run,
    }


def list_audience_preparation_runs(
    database_path: str | Path,
    *,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    path = initialize_database(database_path)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise AudiencePreparationValidationError("limit must be an integer between 1 and 100.")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise AudiencePreparationValidationError("offset must be a non-negative integer.")

    with get_connection(path) as connection:
        rows = connection.execute(
            """
            SELECT
                s.scoring_run_id,
                s.model_run_id,
                s.completed_at,
                s.scored_person_count,
                COUNT(b.percentile_bucket) AS boundary_count,
                MIN(b.rank_contract_version) AS rank_contract_version
            FROM scoring_runs s
            LEFT JOIN audience_rank_boundaries b
                ON b.scoring_run_id = s.scoring_run_id
            WHERE s.status = 'COMPLETED'
            GROUP BY
                s.scoring_run_id,
                s.model_run_id,
                s.completed_at,
                s.scored_person_count
            ORDER BY s.completed_at DESC, s.scoring_run_id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

    summaries: list[dict[str, Any]] = []
    for row in rows:
        boundary_count = int(row["boundary_count"])
        currentness = _resolve_run_currentness(
            path,
            scoring_run_id=int(row["scoring_run_id"]),
            model_run_id=int(row["model_run_id"]),
        )
        prepared = boundary_count == 100 and str(row["rank_contract_version"] or "") == DEFAULT_RANK_CONTRACT_VERSION
        summaries.append(
            {
                "scoring_run_id": int(row["scoring_run_id"]),
                "model_run_id": int(row["model_run_id"]),
                "completed_at": row["completed_at"],
                "scored_person_count": int(row["scored_person_count"]),
                "prepared": prepared,
                "is_canonical": bool(currentness["is_canonical"]),
                "source_verified": bool(currentness["source_verified"]),
                "ready_for_current_audience_actions": (
                    prepared
                    and bool(currentness["is_canonical"])
                    and bool(currentness["source_verified"])
                ),
                "currentness_issues": currentness["currentness_issues"],
                "rank_contract_version": row["rank_contract_version"] if prepared else None,
                "boundary_count": boundary_count,
            }
        )
    return summaries


def run_audience_rank_preparation(
    database_path: str | Path,
    *,
    scoring_run_id: int,
    rank_contract_version: str = DEFAULT_RANK_CONTRACT_VERSION,
    chunk_size: int = DEFAULT_PREPARATION_SCAN_CHUNK_SIZE,
) -> dict[str, Any]:
    path = initialize_database(database_path)
    normalized_scoring_run_id = _require_positive_int(scoring_run_id, field_name="scoring_run_id")
    normalized_rank_contract_version = _normalize_rank_contract_version(rank_contract_version)
    normalized_chunk_size = _normalize_scan_chunk_size(chunk_size)

    envelope = _validate_preparation_inputs(
        path,
        scoring_run_id=normalized_scoring_run_id,
        rank_contract_version=normalized_rank_contract_version,
    )

    boundaries, metrics = _compute_boundaries_for_run(
        path,
        scoring_run_id=normalized_scoring_run_id,
        chunk_size=normalized_chunk_size,
    )

    # Revalidate canonical provenance and score count before publishing boundaries.
    _validate_preparation_inputs(
        path,
        scoring_run_id=normalized_scoring_run_id,
        rank_contract_version=normalized_rank_contract_version,
    )

    boundary_rows = [row.to_row() for row in boundaries]
    created_at = _utc_timestamp()
    rank_repository = AudienceRankRepository(path)
    rank_repository.replace_boundaries(
        scoring_run_id=normalized_scoring_run_id,
        rank_contract_version=normalized_rank_contract_version,
        created_at=created_at,
        boundaries=boundary_rows,
    )

    persisted = rank_repository.fetch_boundaries(normalized_scoring_run_id)
    if len(persisted) != 100:
        raise AudiencePreparationValidationError("Persisted audience boundaries are incomplete.")

    return {
        "scoring_run_id": normalized_scoring_run_id,
        "model_run_id": int(envelope["model_run_id"]),
        "rank_contract_version": normalized_rank_contract_version,
        "boundary_count": len(persisted),
        "total_population": int(boundary_rows[-1]["total_population"]),
        **metrics.to_payload(),
    }


__all__ = (
    "ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE",
    "DEFAULT_PREPARATION_SCAN_CHUNK_SIZE",
    "DEFAULT_RANK_CONTRACT_VERSION",
    "EXISTING_AUDIENCE_PREPARATION_CONFLICT_MESSAGE",
    "SCORING_COUNT_MISMATCH_MESSAGE",
    "SCORING_RUN_NOT_CANONICAL_MESSAGE",
    "SCORING_RUN_NOT_COMPLETED_MESSAGE",
    "SCORING_RUN_NOT_FOUND_MESSAGE",
    "AudiencePreparationConflictError",
    "AudiencePreparationServiceError",
    "AudiencePreparationSubmissionError",
    "AudiencePreparationValidationError",
    "classify_decile",
    "classify_percentile_bucket",
    "classify_rank_band",
    "get_audience_preparation_status",
    "list_audience_preparation_runs",
    "run_audience_rank_preparation",
    "submit_audience_preparation_job_request",
)
