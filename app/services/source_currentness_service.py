"""Fail-closed derived currentness after authoritative source replacement.

Historical generations, attestations, calibrations, caches, snapshots, and
export audits remain present.  Only their explicitly mutable currentness/status
fields are changed, so reconciliation is safe to repeat after startup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from app.database.connection import get_connection
from app.services.intelligence_attestation_service import has_current_attestation
from app.services.targeting_option_catalog_service import get_or_build_targeting_catalog


_SOURCE_FIELDS = (
    ("customers", "customer_import_id", "customer_source_checksum"),
    ("campaign_sales", "campaign_sales_import_id", "campaign_sales_source_checksum"),
    ("demographics", "demographic_import_id", "demographic_source_checksum"),
)


def latest_source_identity(database_path: str | Path) -> dict[str, tuple[int, str]]:
    """Return the latest completed identity for every authoritative dataset."""

    with get_connection(database_path) as connection:
        rows = connection.execute(
            """SELECT dataset_name,import_id,source_checksum
               FROM data_import_runs AS run
               WHERE status='COMPLETED'
                 AND dataset_name IN ('customers','campaign_sales','demographics')
                 AND import_id=(
                     SELECT MAX(candidate.import_id) FROM data_import_runs AS candidate
                     WHERE candidate.status='COMPLETED'
                       AND candidate.dataset_name=run.dataset_name
                 )"""
        ).fetchall()
    return {
        str(row["dataset_name"]): (int(row["import_id"]), str(row["source_checksum"]))
        for row in rows
    }


def generation_sources_match(
    database_path: str | Path, generation: Mapping[str, Any] | None,
) -> bool:
    if generation is None:
        return False
    current = latest_source_identity(database_path)
    if set(current) != {name for name, _id, _checksum in _SOURCE_FIELDS}:
        return False
    return all(
        generation.get(import_field) == current[name][0]
        and generation.get(checksum_field) == current[name][1]
        for name, import_field, checksum_field in _SOURCE_FIELDS
    )


def calibration_is_current(
    database_path: str | Path,
    generation: Mapping[str, Any] | None,
    calibration_artifact_id: int | None = None,
) -> bool:
    """Check exact promoted calibration ownership without scanning score rows."""

    if generation is None or not generation_sources_match(database_path, generation):
        return False
    if not has_current_attestation(database_path, generation):
        return False
    parameters: list[Any] = [int(generation["scoring_run_id"])]
    predicate = ""
    if calibration_artifact_id is not None:
        predicate = " AND calibration_artifact_id=?"
        parameters.append(int(calibration_artifact_id))
    with get_connection(database_path) as connection:
        row = connection.execute(
            """SELECT calibration_artifact_id FROM score_calibration_artifacts
               WHERE scoring_run_id=? AND status='PROMOTED'"""
            + predicate
            + " ORDER BY promoted_at DESC,calibration_artifact_id DESC LIMIT 1",
            tuple(parameters),
        ).fetchone()
    return row is not None


def result_lineage_is_current(
    database_path: str | Path,
    generation: Mapping[str, Any] | None,
    *,
    selection_contract_version: str = "1",
    calibration_artifact_id: int | None = None,
) -> bool:
    if generation is None or not generation_sources_match(database_path, generation):
        return False
    # Legacy v1 snapshots predate deep-attestation persistence.  Their immutable
    # generation and exact authoritative source identity remain the compatibility
    # contract.  New calibrated v2 snapshots additionally require the promoted
    # calibration, which itself requires a current attestation.
    return selection_contract_version != "2" or calibration_is_current(
        database_path, generation, calibration_artifact_id
    )


def reconcile_source_currentness(database_path: str | Path) -> dict[str, Any]:
    """Build the exact catalog and stale incompatible derived artifacts.

    The authoritative import is already committed before this function runs.
    Every operation is idempotent, so startup can repair an interrupted or
    failed post-import maintenance pass deterministically.
    """

    path = Path(database_path)
    catalog = get_or_build_targeting_catalog(path)
    current = latest_source_identity(path)
    if set(current) != {name for name, _id, _checksum in _SOURCE_FIELDS}:
        return {
            "catalog_version": catalog["catalog_version"],
            "stale_attestations": 0,
            "stale_calibrations": 0,
            "stale_preflight_entries": 0,
            "stale_snapshots": 0,
        }

    mismatch = " OR ".join(
        f"g.{import_field}<>? OR g.{checksum_field}<>?"
        for _name, import_field, checksum_field in _SOURCE_FIELDS
    )
    parameters: list[Any] = []
    for name, _import_field, _checksum_field in _SOURCE_FIELDS:
        parameters.extend(current[name])
    with get_connection(path, write=True) as connection:
        connection.execute("BEGIN IMMEDIATE")
        stale_attestations = connection.execute(
            f"""UPDATE intelligence_verification_attestations AS a
                SET verification_status='STALE'
                WHERE verification_status='VERIFIED' AND EXISTS (
                    SELECT 1 FROM phase10_intelligence_generations AS g
                    WHERE g.generation_id=a.generation_id AND ({mismatch})
                )""",
            tuple(parameters),
        ).rowcount
        stale_calibrations = connection.execute(
            f"""UPDATE score_calibration_artifacts AS c SET status='STALE'
                WHERE status='PROMOTED' AND EXISTS (
                    SELECT 1 FROM phase10_intelligence_generations AS g
                    WHERE g.scoring_run_id=c.scoring_run_id AND ({mismatch})
                )""",
            tuple(parameters),
        ).rowcount
        stale_preflight = connection.execute(
            f"""UPDATE search_preflight_cache AS cache SET currentness_state='STALE'
                WHERE currentness_state='CURRENT' AND (
                    NOT EXISTS (
                        SELECT 1 FROM score_calibration_artifacts AS c
                        WHERE c.calibration_artifact_id=cache.calibration_artifact_id
                          AND c.status='PROMOTED'
                    ) OR EXISTS (
                        SELECT 1 FROM phase10_intelligence_generations AS g
                        WHERE g.generation_id=cache.generation_id AND ({mismatch})
                    )
                )""",
            tuple(parameters),
        ).rowcount
        stale_snapshots = connection.execute(
            f"""UPDATE campaign_result_snapshots AS snapshot
                SET currentness_state='STALE'
                WHERE currentness_state='CURRENT' AND EXISTS (
                    SELECT 1 FROM phase10_intelligence_generations AS g
                    WHERE g.generation_id=snapshot.generation_id AND ({mismatch})
                )""",
            tuple(parameters),
        ).rowcount
    return {
        "catalog_version": catalog["catalog_version"],
        "stale_attestations": stale_attestations,
        "stale_calibrations": stale_calibrations,
        "stale_preflight_entries": stale_preflight,
        "stale_snapshots": stale_snapshots,
    }


__all__ = (
    "calibration_is_current",
    "generation_sources_match",
    "latest_source_identity",
    "reconcile_source_currentness",
    "result_lineage_is_current",
)
