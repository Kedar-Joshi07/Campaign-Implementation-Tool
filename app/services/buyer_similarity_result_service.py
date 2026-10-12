"""Immutable v3 analytical membership and exact result cache identity."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.database.connection import get_connection
from app.selection_contracts import BUYER_SIMILARITY_SCORE_METHOD_VERSION
from app.services.buyer_similarity_selection_service import (
    SimilarityResolution,
    canonical_digest,
    resolve_similarity_context,
    selected_members_sql,
    selection_sql,
    _current_sources,
)


MEMBERSHIP_COLUMNS = (
    "person_id", "buyer_similarity_score", "similarity_tier",
    "matched_product_id", "score_method_version", "feature_coverage",
    "similarity_generation_id",
)
_TIERS = ("VERY_STRONG", "STRONG", "GOOD", "BROAD", "EXPLORATORY")


class SimilarityResultError(RuntimeError):
    """A v3 result cannot be published or reused safely."""


def result_cache_key(run: Mapping[str, Any], resolution: SimilarityResolution) -> str:
    if not resolution.ready or not resolution.profile_set_sha256:
        raise SimilarityResultError("Current verified buyer similarity is required.")
    return canonical_digest({
        "cache_contract_version": "SIMILARITY_RESULT_V1",
        "selection_contract_version": "3",
        "membership_contract_version": "3",
        "score_semantics": "PRODUCT_BUYER_SIMILARITY",
        "score_method_version": BUYER_SIMILARITY_SCORE_METHOD_VERSION,
        "minimum": run["similarity_minimum"],
        "threshold_predicate": "GREATER_THAN_OR_EQUAL",
        "product_match_policy": "ANY_SELECTED_PRODUCT_MAX_V1",
        "profile_ids": resolution.profile_ids,
        "profile_set_sha256": resolution.profile_set_sha256,
        "generation_ids": resolution.generation_ids,
        "composite_context_sha256": resolution.composite_context_sha256,
        "source_identity": resolution.source_identity,
        "criteria_sha256": run["targeting_criteria_sha256"],
        "filter_branches_sha256": run["filter_branches_sha256"],
        "catalog_version": run["catalog_version"],
        "selection_mode": run["selection_mode"],
        "top_n": run["target_count"],
        "ordering": "SCORE_DESC_PERSON_ID_ASC",
        "publication_cutoff": max(
            str(row["published_at"]) for row in resolution.generation_rows
        ),
    })


def _root(project_root: str | Path) -> Path:
    root = Path(project_root).resolve()
    destination = (root / "artifacts" / "similarity_results").resolve()
    if not destination.is_relative_to(root):
        raise SimilarityResultError("The result artifact root is unsafe.")
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def _valid_member(raw: Mapping[str, Any], minimum: float) -> tuple[Any, ...]:
    if set(raw) != set(MEMBERSHIP_COLUMNS):
        raise SimilarityResultError("Similarity membership schema is invalid.")
    person_id = raw["person_id"]
    product = raw["matched_product_id"]
    method = raw["score_method_version"]
    tier = raw["similarity_tier"]
    try:
        score = float(raw["buyer_similarity_score"])
        coverage = float(raw["feature_coverage"])
        generation_id = int(raw["similarity_generation_id"])
    except (TypeError, ValueError) as exc:
        raise SimilarityResultError("Similarity membership values are invalid.") from exc
    if (
        not isinstance(person_id, str) or not 1 <= len(person_id) <= 128
        or "\x00" in person_id or not isinstance(product, str) or not product
        or method != BUYER_SIMILARITY_SCORE_METHOD_VERSION
        or tier not in _TIERS or not math.isfinite(score)
        or score < minimum or score > 1 or not math.isfinite(coverage)
        or not 0.80 <= coverage <= 1 or generation_id <= 0
        or isinstance(raw["similarity_generation_id"], bool)
    ):
        raise SimilarityResultError("Similarity membership values are invalid.")
    expected_tier = next(
        label for threshold, label in (
            (0.90, "VERY_STRONG"), (0.80, "STRONG"), (0.70, "GOOD"),
            (0.60, "BROAD"), (0.50, "EXPLORATORY"),
        ) if score >= threshold
    )
    if tier != expected_tier:
        raise SimilarityResultError("Similarity tier does not match its full precision score.")
    return (person_id, repr(score), tier, product, method, repr(coverage), generation_id)


def _write_membership(path: Path, rows: Any, minimum: float) -> int:
    count = 0
    previous: tuple[float, str] | None = None
    with path.open("xb") as output:
        with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="", write_through=True) as text:
                writer = csv.writer(text, lineterminator="\n")
                writer.writerow(MEMBERSHIP_COLUMNS)
                for raw in rows:
                    values = _valid_member(dict(raw), minimum)
                    order = (-float(values[1]), values[0])
                    if previous is not None and order <= previous:
                        raise SimilarityResultError("Similarity order or uniqueness changed.")
                    previous = order
                    writer.writerow(values)
                    count += 1
        output.flush()
        os.fsync(output.fileno())
    return count


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inspect_membership(
    path: Path, minimum: float,
    generation_products: Mapping[int, str] | None = None,
) -> tuple[int, str]:
    count = 0
    previous: tuple[float, str] | None = None
    with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if tuple(reader.fieldnames or ()) != MEMBERSHIP_COLUMNS:
            raise SimilarityResultError("Similarity membership columns changed.")
        for raw in reader:
            values = _valid_member(raw, minimum)
            if generation_products is not None and generation_products.get(int(values[6])) != values[3]:
                raise SimilarityResultError("Similarity winning product or generation changed.")
            order = (-float(values[1]), values[0])
            if previous is not None and order <= previous:
                raise SimilarityResultError("Similarity membership order changed.")
            previous = order
            count += 1
    return count, _sha256(path)


def _manifest(
    run: Mapping[str, Any], resolution: SimilarityResolution,
    key: str, count: int, digest: str,
) -> dict[str, Any]:
    return {
        "membership_contract_version": "3",
        "score_semantics": "PRODUCT_BUYER_SIMILARITY",
        "score_method_version": BUYER_SIMILARITY_SCORE_METHOD_VERSION,
        "similarity_minimum": run["similarity_minimum"],
        "threshold_predicate": "GREATER_THAN_OR_EQUAL",
        "product_match_policy": "ANY_SELECTED_PRODUCT_MAX_V1",
        "profile_ids": list(resolution.profile_ids),
        "profile_set_sha256": resolution.profile_set_sha256,
        "generation_ids": list(resolution.generation_ids),
        "composite_context_sha256": resolution.composite_context_sha256,
        "source_identity": {
            name: list(identity) for name, identity in resolution.source_identity.items()
        },
        "criteria_sha256": run["targeting_criteria_sha256"],
        "filter_branches_sha256": run["filter_branches_sha256"],
        "catalog_version": run["catalog_version"],
        "selection_mode": run["selection_mode"],
        "top_n": run["target_count"],
        "cache_key_sha256": key,
        "row_count": count,
        "file_sha256": digest,
        "columns": list(MEMBERSHIP_COLUMNS),
    }


def validate_similarity_result_snapshot(
    snapshot: Mapping[str, Any], run: Mapping[str, Any],
    resolution: SimilarityResolution, *, project_root: str | Path,
) -> bool:
    try:
        if not resolution.ready:
            return False
        key = result_cache_key(run, resolution)
        if any((
            snapshot.get("result_cache_key_sha256") != key,
            snapshot.get("currentness_state") != "CURRENT",
            snapshot.get("result_membership_contract_version") != "3",
            snapshot.get("profile_set_sha256") != resolution.profile_set_sha256,
            snapshot.get("composite_context_sha256") != resolution.composite_context_sha256,
            snapshot.get("similarity_generation_id") != resolution.generation_ids[0],
            snapshot.get("targeting_criteria_sha256") != run["targeting_criteria_sha256"],
            snapshot.get("filter_branches_sha256") != run["filter_branches_sha256"],
            snapshot.get("selection_mode") != run["selection_mode"],
            snapshot.get("target_count") != run["target_count"],
        )):
            return False
        root = Path(project_root).resolve()
        directory = _root(root) / f"snapshot_{int(snapshot['similarity_result_snapshot_id']):06d}"
        expected_uri = (directory / "members.csv.gz").relative_to(root).as_posix()
        if snapshot.get("storage_uri") != expected_uri or directory.is_symlink():
            return False
        path = directory / "members.csv.gz"
        manifest_path = directory / "manifest.json"
        if (path.is_symlink() or manifest_path.is_symlink()
            or not path.is_file() or not manifest_path.is_file()
            or manifest_path.stat().st_size > 65536):
            return False
        generation_products = {
            int(row["similarity_generation_id"]): str(row["product_id"])
            for row in resolution.generation_rows
        }
        count, digest = _inspect_membership(
            path, float(run["similarity_minimum"]), generation_products,
        )
        if count != snapshot.get("resolved_count") or digest != snapshot.get("snapshot_sha256"):
            return False
        return json.loads(manifest_path.read_text(encoding="utf-8")) == _manifest(
            run, resolution, key, count, digest
        )
    except (OSError, ValueError, TypeError, KeyError, SimilarityResultError):
        return False


def find_similarity_result_snapshot(
    database_path: str | Path, run: Mapping[str, Any],
    resolution: SimilarityResolution, *, project_root: str | Path,
) -> dict[str, Any] | None:
    key = result_cache_key(run, resolution)
    with get_connection(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM buyer_similarity_result_snapshots WHERE result_cache_key_sha256=?",
            (key,),
        ).fetchone()
    candidate = dict(row) if row is not None else None
    if candidate is None:
        return None
    if not validate_similarity_result_snapshot(candidate, run, resolution, project_root=project_root):
        raise SimilarityResultError("A matching immutable similarity snapshot is invalid.")
    return candidate


def materialize_similarity_result(
    database_path: str | Path, run: Mapping[str, Any],
    context: Mapping[str, Any], resolution: SimilarityResolution,
    *, project_root: str | Path,
    attempt_number: int,
    execution_lease_token: str,
    product_catalog_path: str | Path | None = None,
) -> dict[str, Any]:
    """Stream the shared selection query into one checksum verified snapshot."""

    if not resolution.ready:
        raise SimilarityResultError("Current verified buyer similarity is required.")
    def assert_active(connection: Any) -> None:
        active = connection.execute(
            """SELECT 1 FROM campaign_search_runs r
               JOIN campaign_search_attempts a ON a.search_run_id=r.search_run_id
                 AND a.attempt_number=r.current_attempt_number
               WHERE r.search_run_id=? AND r.current_attempt_number=?
                 AND r.status='PROCESSING' AND r.selection_contract_version='3'
                 AND a.status='PROCESSING' AND a.execution_lease_token=?""",
            (int(run["search_run_id"]), attempt_number, execution_lease_token),
        ).fetchone()
        if active is None:
            raise SimilarityResultError("The similarity result publication lease is no longer active.")

    with get_connection(database_path) as connection:
        assert_active(connection)
    key = result_cache_key(run, resolution)
    existing = find_similarity_result_snapshot(
        database_path, run, resolution, project_root=project_root,
    )
    if existing is not None:
        return existing
    root = Path(project_root).resolve()
    results_root = _root(root)
    branches = json.loads(str(run["filter_branches_json"]))
    cte, parameters = selection_sql(
        branches, resolution.generation_ids, float(run["similarity_minimum"]),
        selection_mode=str(run["selection_mode"]), top_n=run["target_count"],
    )
    query = selected_members_sql(cte, selection_mode=str(run["selection_mode"]))
    if run["selection_mode"] == "TOP_N":
        parameters = (*parameters, int(run["target_count"]))
    with tempfile.TemporaryDirectory(prefix=".pending_similarity_", dir=results_root) as temporary:
        staged = Path(temporary)
        membership = staged / "members.csv.gz"
        with get_connection(database_path) as connection:
            connection.execute("BEGIN")
            cursor = connection.execute(query, parameters)
            count = _write_membership(membership, cursor, float(run["similarity_minimum"]))
        inspected_count, digest = _inspect_membership(
            membership, float(run["similarity_minimum"]), {
                int(row["similarity_generation_id"]): str(row["product_id"])
                for row in resolution.generation_rows
            },
        )
        if count != inspected_count:
            raise SimilarityResultError("Membership count changed after publication staging.")
        after = resolve_similarity_context(
            database_path, context, project_root=root,
            product_catalog_path=product_catalog_path,
        )
        if not after.ready or after.composite_context_sha256 != resolution.composite_context_sha256:
            raise SimilarityResultError("Source data changed during result materialization.")
        with get_connection(database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            assert_active(connection)
            if _current_sources(connection) != resolution.source_identity:
                raise SimilarityResultError("Authoritative sources changed before result publication.")
            raced = connection.execute(
                "SELECT * FROM buyer_similarity_result_snapshots WHERE result_cache_key_sha256=?",
                (key,),
            ).fetchone()
            if raced is not None:
                candidate = dict(raced)
                if validate_similarity_result_snapshot(
                    candidate, run, resolution, project_root=root,
                ):
                    return candidate
                raise SimilarityResultError("A matching snapshot was published concurrently but is invalid.")
            next_id = int(connection.execute(
                "SELECT COALESCE(MAX(similarity_result_snapshot_id),0)+1 FROM buyer_similarity_result_snapshots"
            ).fetchone()[0])
            destination = results_root / f"snapshot_{next_id:06d}"
            if destination.exists() or destination.is_symlink():
                raise SimilarityResultError("The result artifact destination is occupied.")
            manifest = _manifest(run, resolution, key, count, digest)
            manifest_path = staged / "manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            with manifest_path.open("rb+") as stream:
                os.fsync(stream.fileno())
            os.replace(staged, destination)
            try:
                moment = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
                uri = (destination / "members.csv.gz").relative_to(root).as_posix()
                connection.execute(
                    """INSERT INTO buyer_similarity_result_snapshots (
                        similarity_result_snapshot_id,result_membership_contract_version,
                        similarity_generation_id,selection_contract_version,
                        score_semantics,score_method_version,similarity_minimum,
                        threshold_predicate,product_match_policy,profile_set_sha256,
                        composite_context_sha256,targeting_criteria_sha256,
                        filter_branches_sha256,selection_mode,target_count,
                        result_cache_key_sha256,resolved_count,storage_format,
                        storage_uri,snapshot_sha256,publication_cutoff,
                        currentness_state,created_at,last_verified_at,last_used_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (next_id, "3", resolution.generation_ids[0], "3",
                     "PRODUCT_BUYER_SIMILARITY", BUYER_SIMILARITY_SCORE_METHOD_VERSION,
                     run["similarity_minimum"], "GREATER_THAN_OR_EQUAL",
                     "ANY_SELECTED_PRODUCT_MAX_V1", resolution.profile_set_sha256,
                     resolution.composite_context_sha256,
                     run["targeting_criteria_sha256"], run["filter_branches_sha256"],
                     run["selection_mode"], run["target_count"], key, count,
                     "CSV_GZIP", uri, digest,
                     max(str(row["published_at"]) for row in resolution.generation_rows),
                     "CURRENT", moment, moment, moment),
                )
            except Exception:
                # Only the uniquely allocated, unregistered directory is removed.
                for child in destination.iterdir():
                    child.unlink()
                destination.rmdir()
                raise
    with get_connection(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM buyer_similarity_result_snapshots WHERE result_cache_key_sha256=?",
            (key,),
        ).fetchone()
    if row is None or not validate_similarity_result_snapshot(
        dict(row), run, resolution, project_root=root,
    ):
        raise SimilarityResultError("Published similarity result did not pass reopen validation.")
    return dict(row)


def reconcile_similarity_result_publications(
    database_path: str | Path, *, project_root: str | Path,
    minimum_age_seconds: int = 86400, limit: int = 100,
) -> int:
    """Remove only old unregistered publication debris; never touch registered history."""

    if minimum_age_seconds < 3600 or not 1 <= limit <= 1000:
        raise ValueError("Similarity publication recovery bounds are invalid.")
    root = _root(project_root)
    with get_connection(database_path) as connection:
        registered = {
            int(row[0]) for row in connection.execute(
                "SELECT similarity_result_snapshot_id FROM buyer_similarity_result_snapshots"
            )
        }
    removed = 0
    cutoff = time.time() - minimum_age_seconds
    for directory in sorted(root.iterdir()):
        if removed >= limit:
            break
        if directory.is_symlink() or not directory.is_dir() or not directory.name.startswith("snapshot_"):
            continue
        suffix = directory.name.removeprefix("snapshot_")
        if len(suffix) < 6 or not suffix.isdigit() or int(suffix) in registered:
            continue
        if directory.stat().st_mtime > cutoff:
            continue
        children = list(directory.iterdir())
        if any(child.is_symlink() or not child.is_file()
               or child.name not in {"members.csv.gz", "manifest.json"} for child in children):
            continue
        for child in children:
            child.unlink()
        directory.rmdir()
        removed += 1
    return removed


__all__ = (
    "MEMBERSHIP_COLUMNS", "SimilarityResultError", "find_similarity_result_snapshot",
    "materialize_similarity_result", "result_cache_key", "validate_similarity_result_snapshot",
    "reconcile_similarity_result_publications",
)
