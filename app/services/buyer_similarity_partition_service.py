"""Immutable, bounded partition-manifest publication before v3 profile fitting."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from app.database.connection import get_connection
from app.services.buyer_similarity_cohort_service import BuyerCohortBuild
from app.services.buyer_similarity_split_service import SUPPORT_AWARE_SPLIT_VERSION


PARTITION_ROOT = Path("artifacts/buyer_similarity_partitions")
_SHA = re.compile(r"[0-9a-f]{64}")
MAX_PARTITION_BYTES = 512_000


class BuyerPartitionError(RuntimeError):
    """No incomplete or mismatched partition may be used for model fitting."""


def _encoded(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def _path(root: Path, context_sha: str, partition_sha: str) -> Path:
    if _SHA.fullmatch(context_sha) is None or _SHA.fullmatch(partition_sha) is None:
        raise BuyerPartitionError("The partition identity is invalid.")
    destination = (root / PARTITION_ROOT / f"partition_{partition_sha}.json").resolve()
    if not destination.is_relative_to(root) or destination.is_symlink():
        raise BuyerPartitionError("The partition artifact path is unsafe.")
    return destination


def load_partition_manifest(
    *, project_root: str | Path, context_sha256: str, partition_sha256: str,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    path = _path(root, context_sha256, partition_sha256)
    if not path.is_file() or path.stat().st_size > MAX_PARTITION_BYTES:
        raise BuyerPartitionError("The frozen partition manifest is missing or oversized.")
    data = path.read_bytes()
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuyerPartitionError("The frozen partition manifest is invalid.") from exc
    if (not isinstance(payload, dict)
        or _encoded(payload) != data
        or hashlib.sha256(_encoded(payload).rstrip(b"\n")).hexdigest() != partition_sha256
        or payload.get("context_identity_sha256") != context_sha256
        or payload.get("split_strategy_version") != SUPPORT_AWARE_SPLIT_VERSION
        or payload.get("split_status") != "FEASIBLE"):
        raise BuyerPartitionError("The frozen partition manifest does not match its lineage.")
    return payload


def _assert_current_sources(database_path: Path, payload: dict[str, Any]) -> None:
    source = payload["source_identity"]
    with get_connection(database_path) as connection:
        for dataset, id_field, checksum_field in (
            ("customers", "customer_import_id", "customer_source_checksum"),
            ("campaign_sales", "campaign_sales_import_id", "campaign_sales_source_checksum"),
        ):
            row = connection.execute(
                "SELECT import_id,source_checksum FROM data_import_runs "
                "WHERE dataset_name=? AND status='COMPLETED' ORDER BY import_id DESC LIMIT 1",
                (dataset,),
            ).fetchone()
            if (row is None or int(row["import_id"]) != source[id_field]
                or str(row["source_checksum"]).lower() != source[checksum_field]):
                raise BuyerPartitionError("The buyer source changed before partition publication.")


def freeze_partition_manifest(
    cohort: BuyerCohortBuild, *, project_root: str | Path,
    database_path: str | Path,
) -> dict[str, Any]:
    """Atomically create-if-absent; a crash leaves only a full file or no file."""

    manifest = cohort.manifest
    if (manifest.split_strategy_version != SUPPORT_AWARE_SPLIT_VERSION
        or manifest.split_status != "FEASIBLE" or not manifest.eligible
        or manifest.partition_manifest_sha256 is None):
        raise BuyerPartitionError("Only a fully feasible partition can be frozen.")
    payload = manifest.partition_payload()
    data = _encoded(payload)
    if len(data) > MAX_PARTITION_BYTES:
        raise BuyerPartitionError("The partition manifest exceeds its size limit.")
    root = Path(project_root).resolve()
    destination = _path(root, manifest.context_identity_sha256,
                        manifest.partition_manifest_sha256)
    _assert_current_sources(Path(database_path), payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        existing = load_partition_manifest(
            project_root=root, context_sha256=manifest.context_identity_sha256,
            partition_sha256=manifest.partition_manifest_sha256,
        )
        if existing != payload:
            raise BuyerPartitionError("An immutable partition identity has different content.")
        return existing
    temporary = destination.parent / f".{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            pass  # A competing builder may publish only the same exact identity.
    finally:
        if temporary.exists():
            temporary.unlink()
    existing = load_partition_manifest(
        project_root=root, context_sha256=manifest.context_identity_sha256,
        partition_sha256=manifest.partition_manifest_sha256,
    )
    if existing != payload:
        raise BuyerPartitionError("A competing partition publication differs.")
    _assert_current_sources(Path(database_path), payload)
    return existing


__all__ = ["BuyerPartitionError", "PARTITION_ROOT", "freeze_partition_manifest",
           "load_partition_manifest"]
