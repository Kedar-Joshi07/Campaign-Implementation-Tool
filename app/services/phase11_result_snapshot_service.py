"""Deterministic, no-contact-PII Phase 11 result snapshot publication.

CSV-GZIP is the frozen POC format.  It is streamable and uses only the Python
standard library; the locked runtime does not carry pyarrow.  Membership files
contain only the five version-1 analytical identity fields.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
import os
import re
import shutil
import tempfile
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.database.connection import get_connection
from app.repositories.campaign_result_registry_repository import (
    CampaignResultRegistryRepository,
)
from app.services.audience_preparation_service import (
    classify_decile,
    classify_rank_band,
)
from app.services.phase11_result_contracts import (
    RESULT_MEMBERSHIP_COLUMNS,
    RESULT_MEMBERSHIP_CONTRACT_VERSION,
    Phase11RegistryStateError,
)


RESULT_SNAPSHOT_STORAGE_FORMAT = "CSV_GZIP"
RESULT_SNAPSHOT_FILE_NAME = "members.csv.gz"
RESULT_SNAPSHOT_MANIFEST_NAME = "manifest.json"
RESULT_MEMBERSHIP_SCHEMA = (
    {"name": "person_id", "type": "string"},
    {"name": "propensity_score", "type": "float64"},
    {"name": "percentile_bucket", "type": "int32"},
    {"name": "decile", "type": "int32"},
    {"name": "rank_band", "type": "string"},
)
DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_READY_LIFECYCLES = frozenset({"CURRENT", "REUSABLE", "PROTECTED"})
_SNAPSHOT_DIRECTORY = re.compile(r"result_snapshot_[0-9]+")


class ResultSnapshotError(RuntimeError):
    """Base class for safe snapshot publication/validation failures."""


class ResultSnapshotValidationError(ResultSnapshotError):
    """Membership or manifest content violates contract version 1."""


class ResultSnapshotPublicationError(ResultSnapshotError):
    """A validated artifact could not be safely published."""


@dataclass(frozen=True)
class ResultSnapshotValidation:
    is_valid: bool
    error_code: str | None = None
    row_count: int | None = None
    file_sha256: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_results_root(project_root: str | Path) -> tuple[Path, Path]:
    root = Path(project_root).resolve()
    results = (root / "artifacts" / "results").resolve()
    if not results.is_relative_to(root):
        raise ResultSnapshotPublicationError("Result artifact root is unsafe.")
    results.mkdir(parents=True, exist_ok=True)
    return root, results


def _validated_member(raw: Mapping[str, Any]) -> tuple[str, float, int, int, str]:
    if set(raw) != set(RESULT_MEMBERSHIP_COLUMNS):
        raise ResultSnapshotValidationError("Membership schema is invalid.")
    person_id = raw.get("person_id")
    rank_band = raw.get("rank_band")
    try:
        score = float(raw.get("propensity_score"))
        percentile_bucket = int(raw.get("percentile_bucket"))
        decile = int(raw.get("decile"))
    except (TypeError, ValueError) as exc:
        raise ResultSnapshotValidationError("Membership values are invalid.") from exc
    if (
        not isinstance(person_id, str)
        or not 1 <= len(person_id) <= 200
        or "\x00" in person_id
        or not math.isfinite(score)
        or not 0.0 <= score <= 1.0
        or isinstance(raw.get("percentile_bucket"), bool)
        or not 1 <= percentile_bucket <= 100
        or isinstance(raw.get("decile"), bool)
        or decile != classify_decile(percentile_bucket)
        or not isinstance(rank_band, str)
        or rank_band != classify_rank_band(percentile_bucket)
    ):
        raise ResultSnapshotValidationError("Membership values are invalid.")
    return person_id, score, percentile_bucket, decile, rank_band


def _write_membership(path: Path, members: Iterable[Mapping[str, Any]]) -> int:
    count = 0
    previous_order: tuple[float, str] | None = None
    with path.open("xb") as raw:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=raw, compresslevel=6, mtime=0
        ) as compressed:
            with io.TextIOWrapper(
                compressed, encoding="utf-8", newline="", write_through=True
            ) as text:
                writer = csv.writer(text, lineterminator="\n")
                writer.writerow(RESULT_MEMBERSHIP_COLUMNS)
                for member in members:
                    if not isinstance(member, Mapping):
                        raise ResultSnapshotValidationError(
                            "Membership rows must be objects."
                        )
                    person_id, score, percentile, decile, rank_band = _validated_member(
                        member
                    )
                    order = (-score, person_id)
                    if previous_order is not None and order <= previous_order:
                        raise ResultSnapshotValidationError(
                            "Membership order or uniqueness is invalid."
                        )
                    previous_order = order
                    writer.writerow(
                        (person_id, repr(score), percentile, decile, rank_band)
                    )
                    count += 1
        raw.flush()
        os.fsync(raw.fileno())
    return count


def _inspect_membership(path: Path) -> tuple[int, str]:
    digest = _sha256(path)
    count = 0
    previous_order: tuple[float, str] | None = None
    with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if tuple(reader.fieldnames or ()) != RESULT_MEMBERSHIP_COLUMNS:
            raise ResultSnapshotValidationError("Membership schema is invalid.")
        for raw in reader:
            if None in raw or set(raw) != set(RESULT_MEMBERSHIP_COLUMNS):
                raise ResultSnapshotValidationError("Membership schema is invalid.")
            person_id, score, _percentile, _decile, _rank_band = _validated_member(raw)
            order = (-score, person_id)
            if previous_order is not None and order <= previous_order:
                raise ResultSnapshotValidationError(
                    "Membership order or uniqueness is invalid."
                )
            previous_order = order
            count += 1
    return count, digest


def _manifest(
    *, snapshot_id: int, row_count: int, file_sha256: str,
    run: Mapping[str, Any], generation: Mapping[str, Any], cache_key: str,
    created_at: str,
) -> dict[str, Any]:
    return {
        "result_snapshot_manifest_contract_version": "1",
        "snapshot_id": snapshot_id,
        "result_membership_contract_version": RESULT_MEMBERSHIP_CONTRACT_VERSION,
        "row_count": row_count,
        "file_sha256": file_sha256,
        "generation_id": generation["generation_id"],
        "scoring_run_id": generation["scoring_run_id"],
        "model_run_id": generation["model_run_id"],
        "analysis_run_id": generation["analysis_run_id"],
        "targeting_criteria_sha256": run["targeting_criteria_sha256"],
        "filter_branches_sha256": run["filter_branches_sha256"],
        "result_cache_key_sha256": cache_key,
        "selection_mode": run["selection_mode"],
        "target_count": run["target_count"],
        "created_at": created_at,
        "storage_format": RESULT_SNAPSHOT_STORAGE_FORMAT,
        "storage_schema": list(RESULT_MEMBERSHIP_SCHEMA),
    }


def _write_manifest(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(
        dict(payload), ensure_ascii=True, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    with path.open("xb") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())


def _load_manifest(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 64 * 1024:
        raise ResultSnapshotValidationError("Snapshot manifest is invalid.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ResultSnapshotValidationError("Snapshot manifest is invalid.")
    return payload


def _artifact_path(project_root: Path, storage_uri: Any) -> Path:
    if not isinstance(storage_uri, str):
        raise ResultSnapshotValidationError("Snapshot artifact path is invalid.")
    path = (project_root / storage_uri).resolve()
    if not path.is_relative_to(project_root) or not path.is_file():
        raise ResultSnapshotValidationError("Snapshot artifact is unavailable.")
    if path.name != RESULT_SNAPSHOT_FILE_NAME or not _SNAPSHOT_DIRECTORY.fullmatch(
        path.parent.name
    ):
        raise ResultSnapshotValidationError("Snapshot artifact path is invalid.")
    return path


def validate_result_snapshot(
    snapshot: Mapping[str, Any], run: Mapping[str, Any],
    generation: Mapping[str, Any], cache_key: str, *,
    project_root: str | Path | None = None,
) -> ResultSnapshotValidation:
    """Verify identity, manifest, exact schema, row values, count and checksum."""

    try:
        expected_metadata = {
            "result_membership_contract_version": RESULT_MEMBERSHIP_CONTRACT_VERSION,
            "generation_id": generation.get("generation_id"),
            "targeting_criteria_sha256": run.get("targeting_criteria_sha256"),
            "filter_branches_sha256": run.get("filter_branches_sha256"),
            "selection_mode": run.get("selection_mode"),
            "target_count": run.get("target_count"),
            "result_cache_key_sha256": cache_key,
            "storage_format": RESULT_SNAPSHOT_STORAGE_FORMAT,
            "currentness_state": "CURRENT",
        }
        if any(snapshot.get(key) != value for key, value in expected_metadata.items()):
            return ResultSnapshotValidation(False, "METADATA_MISMATCH")
        if (
            generation.get("generation_status") != "READY"
            or generation.get("lifecycle_state") not in _READY_LIFECYCLES
            or generation.get("modeling_context_sha256")
            != run.get("modeling_context_sha256")
        ):
            return ResultSnapshotValidation(False, "GENERATION_NOT_CURRENT")
        root = (
            DEFAULT_PROJECT_ROOT if project_root is None else Path(project_root)
        ).resolve()
        members_path = _artifact_path(root, snapshot.get("storage_uri"))
        expected_uri = (
            f"artifacts/results/result_snapshot_{int(snapshot['result_snapshot_id']):06d}/"
            f"{RESULT_SNAPSHOT_FILE_NAME}"
        )
        if snapshot.get("storage_uri") != expected_uri:
            return ResultSnapshotValidation(False, "ARTIFACT_IDENTITY_MISMATCH")
        manifest_path = members_path.parent / RESULT_SNAPSHOT_MANIFEST_NAME
        if not manifest_path.is_file():
            return ResultSnapshotValidation(False, "MANIFEST_MISSING")
        row_count, digest = _inspect_membership(members_path)
        if digest != snapshot.get("snapshot_sha256"):
            return ResultSnapshotValidation(False, "CHECKSUM_MISMATCH", row_count, digest)
        if row_count != snapshot.get("resolved_count"):
            return ResultSnapshotValidation(False, "ROW_COUNT_MISMATCH", row_count, digest)
        expected_manifest = _manifest(
            snapshot_id=int(snapshot["result_snapshot_id"]),
            row_count=row_count,
            file_sha256=digest,
            run=run,
            generation=generation,
            cache_key=cache_key,
            created_at=str(snapshot["created_at"]),
        )
        if _load_manifest(manifest_path) != expected_manifest:
            return ResultSnapshotValidation(False, "MANIFEST_MISMATCH", row_count, digest)
        return ResultSnapshotValidation(True, row_count=row_count, file_sha256=digest)
    except (
        KeyError, OSError, UnicodeError, ValueError, TypeError,
        json.JSONDecodeError, gzip.BadGzipFile, ResultSnapshotValidationError,
    ):
        return ResultSnapshotValidation(False, "ARTIFACT_INVALID")


def _next_snapshot_id(connection: Any) -> int:
    sequence = connection.execute(
        "SELECT seq FROM sqlite_sequence WHERE name='campaign_result_snapshots'"
    ).fetchone()
    maximum = connection.execute(
        "SELECT COALESCE(MAX(result_snapshot_id), 0) FROM campaign_result_snapshots"
    ).fetchone()[0]
    return max(int(sequence["seq"]) if sequence is not None else 0, int(maximum)) + 1


def _safe_remove_directory(path: Path, results_root: Path) -> None:
    if path.is_symlink():
        raise ResultSnapshotPublicationError("Refusing unsafe artifact cleanup.")
    resolved = path.resolve()
    if (
        resolved.parent != results_root
        or not (
            _SNAPSHOT_DIRECTORY.fullmatch(resolved.name)
            or resolved.name.startswith(".pending_result_")
        )
    ):
        raise ResultSnapshotPublicationError("Refusing unsafe artifact cleanup.")
    if resolved.exists():
        allowed = {RESULT_SNAPSHOT_FILE_NAME, RESULT_SNAPSHOT_MANIFEST_NAME}
        if any(
            child.is_symlink() or not child.is_file() or child.name not in allowed
            for child in resolved.iterdir()
        ):
            raise ResultSnapshotPublicationError(
                "Refusing cleanup of an unrecognized artifact directory."
            )
        shutil.rmtree(resolved)


def recover_orphan_result_artifacts(
    database_path: str | Path, *, project_root: str | Path | None = None,
    minimum_age_seconds: float = 3600.0, limit: int = 100,
) -> int:
    """Boundedly remove only recognizable, unregistered stale result directories."""

    if (
        isinstance(minimum_age_seconds, bool)
        or not isinstance(minimum_age_seconds, (int, float))
        or not math.isfinite(float(minimum_age_seconds))
        or minimum_age_seconds < 0
        or isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= 1000
    ):
        raise ResultSnapshotValidationError("Invalid orphan recovery bounds.")
    _root, results_root = _safe_results_root(
        DEFAULT_PROJECT_ROOT if project_root is None else project_root
    )
    with get_connection(database_path) as connection:
        registered = {
            Path(row["storage_uri"]).parent.name
            for row in connection.execute(
                "SELECT storage_uri FROM campaign_result_snapshots"
            )
        }
    cutoff = time.time() - float(minimum_age_seconds)
    removed = 0
    inspected = 0
    for candidate in sorted(results_root.iterdir(), key=lambda item: item.name):
        if inspected >= limit:
            break
        inspected += 1
        if not candidate.is_dir() or candidate.is_symlink():
            continue
        recognized = candidate.name.startswith(
            ".pending_result_"
        ) or _SNAPSHOT_DIRECTORY.fullmatch(candidate.name)
        if not recognized or candidate.name in registered:
            continue
        try:
            if candidate.stat().st_mtime > cutoff:
                continue
            _safe_remove_directory(candidate, results_root)
        except FileNotFoundError:
            continue
        removed += 1
    return removed


def _publish_existing(
    *, temp_directory: Path, existing: Mapping[str, Any], run: Mapping[str, Any],
    generation: Mapping[str, Any], cache_key: str, row_count: int,
    file_sha256: str, results_root: Path,
    repository: CampaignResultRegistryRepository,
) -> int:
    snapshot_id = int(existing["result_snapshot_id"])
    live = repository.fetch_snapshot(snapshot_id)
    if live is None or live.get("currentness_state") != "STALE":
        raise ResultSnapshotPublicationError(
            "Only a stale registered snapshot may be deterministically repaired."
        )
    existing = live
    if (
        existing.get("result_cache_key_sha256") != cache_key
        or existing.get("generation_id") != generation.get("generation_id")
        or existing.get("targeting_criteria_sha256") != run.get("targeting_criteria_sha256")
        or existing.get("filter_branches_sha256") != run.get("filter_branches_sha256")
        or existing.get("selection_mode") != run.get("selection_mode")
        or existing.get("target_count") != run.get("target_count")
        or existing.get("resolved_count") != row_count
        or existing.get("snapshot_sha256") != file_sha256
        or existing.get("storage_format") != RESULT_SNAPSHOT_STORAGE_FORMAT
    ):
        raise ResultSnapshotPublicationError(
            "An immutable snapshot cannot be replaced with different membership."
        )
    expected_uri = (
        f"artifacts/results/result_snapshot_{snapshot_id:06d}/"
        f"{RESULT_SNAPSHOT_FILE_NAME}"
    )
    if existing.get("storage_uri") != expected_uri:
        raise ResultSnapshotPublicationError("Snapshot artifact identity is invalid.")
    _write_manifest(
        temp_directory / RESULT_SNAPSHOT_MANIFEST_NAME,
        _manifest(
            snapshot_id=snapshot_id, row_count=row_count,
            file_sha256=file_sha256, run=run, generation=generation,
            cache_key=cache_key, created_at=str(existing["created_at"]),
        ),
    )
    final_directory = results_root / f"result_snapshot_{snapshot_id:06d}"
    if final_directory.is_symlink() or (
        final_directory.exists() and final_directory.resolve().parent != results_root
    ):
        raise ResultSnapshotPublicationError("Snapshot artifact path is unsafe.")
    final_directory.mkdir(parents=False, exist_ok=True)
    os.replace(
        temp_directory / RESULT_SNAPSHOT_MANIFEST_NAME,
        final_directory / RESULT_SNAPSHOT_MANIFEST_NAME,
    )
    os.replace(
        temp_directory / RESULT_SNAPSHOT_FILE_NAME,
        final_directory / RESULT_SNAPSHOT_FILE_NAME,
    )
    repository.update_snapshot_currentness(snapshot_id, state="CURRENT")
    return snapshot_id


def materialize_result_snapshot(
    database_path: str | Path, run: Mapping[str, Any],
    generation: Mapping[str, Any], cache_key: str,
    existing: Mapping[str, Any] | None,
    members: Iterable[Mapping[str, Any]], *,
    project_root: str | Path | None = None,
) -> int:
    """Stream, validate, atomically publish, then register one exact snapshot."""

    root, results_root = _safe_results_root(
        DEFAULT_PROJECT_ROOT if project_root is None else project_root
    )
    recover_orphan_result_artifacts(
        database_path, project_root=root, minimum_age_seconds=3600.0, limit=100
    )
    repository = CampaignResultRegistryRepository(database_path)
    temp_directory = Path(
        tempfile.mkdtemp(prefix=".pending_result_", dir=results_root)
    ).resolve()
    published_directory: Path | None = None
    try:
        members_path = temp_directory / RESULT_SNAPSHOT_FILE_NAME
        written_count = _write_membership(members_path, members)
        verified_count, file_sha256 = _inspect_membership(members_path)
        if verified_count != written_count:
            raise ResultSnapshotValidationError("Membership count changed after write.")

        if existing is not None:
            return _publish_existing(
                temp_directory=temp_directory, existing=existing,
                run=run, generation=generation, cache_key=cache_key,
                row_count=verified_count, file_sha256=file_sha256,
                results_root=results_root, repository=repository,
            )

        created_at = _now()
        with get_connection(database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            raced = connection.execute(
                "SELECT * FROM campaign_result_snapshots WHERE result_cache_key_sha256=?",
                (cache_key,),
            ).fetchone()
            if raced is not None:
                raced_snapshot = dict(raced)
                if validate_result_snapshot(
                    raced_snapshot, run, generation, cache_key, project_root=root
                ).is_valid:
                    return int(raced_snapshot["result_snapshot_id"])
                raise Phase11RegistryStateError(
                    "An exact snapshot was published concurrently; retry for reuse."
                )
            snapshot_id = _next_snapshot_id(connection)
            final_directory = results_root / f"result_snapshot_{snapshot_id:06d}"
            if final_directory.exists():
                registered = connection.execute(
                    "SELECT 1 FROM campaign_result_snapshots WHERE storage_uri LIKE ?",
                    (f"artifacts/results/{final_directory.name}/%",),
                ).fetchone()
                if registered is not None:
                    raise ResultSnapshotPublicationError(
                        "Snapshot artifact path is already registered."
                    )
                _safe_remove_directory(final_directory, results_root)
            _write_manifest(
                temp_directory / RESULT_SNAPSHOT_MANIFEST_NAME,
                _manifest(
                    snapshot_id=snapshot_id, row_count=verified_count,
                    file_sha256=file_sha256, run=run, generation=generation,
                    cache_key=cache_key, created_at=created_at,
                ),
            )
            os.replace(temp_directory, final_directory)
            published_directory = final_directory
            storage_uri = (
                f"artifacts/results/{final_directory.name}/"
                f"{RESULT_SNAPSHOT_FILE_NAME}"
            )
            candidate = {
                "result_snapshot_id": snapshot_id,
                "result_membership_contract_version": RESULT_MEMBERSHIP_CONTRACT_VERSION,
                "generation_id": generation["generation_id"],
                "targeting_criteria_sha256": run["targeting_criteria_sha256"],
                "filter_branches_sha256": run["filter_branches_sha256"],
                "selection_mode": run["selection_mode"],
                "target_count": run["target_count"],
                "result_cache_key_sha256": cache_key,
                "resolved_count": verified_count,
                "storage_format": RESULT_SNAPSHOT_STORAGE_FORMAT,
                "storage_uri": storage_uri,
                "snapshot_sha256": file_sha256,
                "created_at": created_at,
                "currentness_state": "CURRENT",
            }
            validation = validate_result_snapshot(
                candidate, run, generation, cache_key, project_root=root
            )
            if not validation.is_valid:
                raise ResultSnapshotPublicationError(
                    "Published snapshot failed validation before registration."
                )
            registered_id = repository.register_snapshot_in_transaction(
                connection,
                generation_id=int(generation["generation_id"]),
                targeting_criteria_sha256=str(run["targeting_criteria_sha256"]),
                filter_branches_sha256=str(run["filter_branches_sha256"]),
                result_cache_key_sha256=cache_key,
                resolved_count=verified_count,
                storage_format=RESULT_SNAPSHOT_STORAGE_FORMAT,
                storage_uri=storage_uri,
                snapshot_sha256=file_sha256,
                selection_mode=str(run["selection_mode"]),
                target_count=run.get("target_count"),
                timestamp=created_at,
                expected_snapshot_id=snapshot_id,
            )
        return registered_id
    except Exception:
        if published_directory is not None and published_directory.exists():
            _safe_remove_directory(published_directory, results_root)
        raise
    finally:
        if temp_directory.exists():
            _safe_remove_directory(temp_directory, results_root)


class ResultSnapshotMaterializer:
    """Callable composition adapter for the Phase 11 search orchestrator."""

    def __init__(self, project_root: str | Path | None = None) -> None:
        self.project_root = (
            DEFAULT_PROJECT_ROOT if project_root is None else Path(project_root)
        )

    def __call__(
        self, database_path: Path, run: dict[str, Any],
        generation: dict[str, Any], cache_key: str,
        existing: dict[str, Any] | None,
        members: Iterable[Mapping[str, Any]],
    ) -> int:
        return materialize_result_snapshot(
            database_path, run, generation, cache_key, existing, members,
            project_root=self.project_root,
        )


__all__ = (
    "RESULT_MEMBERSHIP_SCHEMA",
    "RESULT_SNAPSHOT_FILE_NAME",
    "RESULT_SNAPSHOT_MANIFEST_NAME",
    "RESULT_SNAPSHOT_STORAGE_FORMAT",
    "ResultSnapshotError",
    "ResultSnapshotMaterializer",
    "ResultSnapshotPublicationError",
    "ResultSnapshotValidation",
    "ResultSnapshotValidationError",
    "materialize_result_snapshot",
    "recover_orphan_result_artifacts",
    "validate_result_snapshot",
)
