"""Durable deep-verification attestations for reusable intelligence generations."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.database.connection import get_connection
from app.database.schema import SCHEMA_VERSION


def _key(generation: Mapping[str, Any]) -> tuple[str, str]:
    sources = {
        name: generation[name] for name in (
            "customer_source_checksum", "campaign_sales_source_checksum",
            "demographic_source_checksum",
        )
    }
    source_json = json.dumps(sources, sort_keys=True, separators=(",", ":"))
    payload = {
        "generation_id": generation["generation_id"],
        "scoring_run_id": generation["scoring_run_id"],
        "artifact_sha256": generation["artifact_sha256"],
        "source_checksums": sources,
        "schema_version": SCHEMA_VERSION,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest(), source_json


def has_current_attestation(database_path: str | Path, generation: Mapping[str, Any]) -> bool:
    key, _sources = _key(generation)
    with get_connection(database_path) as connection:
        row = connection.execute(
            """SELECT verification_status FROM intelligence_verification_attestations
               WHERE attestation_key_sha256=? AND verification_status='VERIFIED'
                 AND (expires_at IS NULL OR expires_at > ?)""",
            (key, datetime.now(timezone.utc).isoformat()),
        ).fetchone()
    return row is not None


def record_deep_verification_attestation(
    database_path: str | Path, generation: Mapping[str, Any],
) -> dict[str, Any]:
    """Perform the population count once, then persist its immutable lineage key."""

    key, source_json = _key(generation)
    with get_connection(database_path) as connection:
        scoring = connection.execute(
            "SELECT scored_person_count,status FROM scoring_runs WHERE scoring_run_id=?",
            (int(generation["scoring_run_id"]),),
        ).fetchone()
        actual = int(connection.execute(
            "SELECT COUNT(*) FROM propensity_scores WHERE scoring_run_id=?",
            (int(generation["scoring_run_id"]),),
        ).fetchone()[0])
    expected = int(scoring["scored_person_count"]) if scoring is not None else -1
    status = "VERIFIED" if scoring is not None and scoring["status"] == "COMPLETED" and actual == expected else "FAILED"
    verified_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """INSERT OR REPLACE INTO intelligence_verification_attestations (
                   attestation_key_sha256,generation_id,scoring_run_id,
                   source_checksums_json,artifact_sha256,schema_version,
                   verified_at,verification_status,verified_row_count
               ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (key, int(generation["generation_id"]), int(generation["scoring_run_id"]),
             source_json, str(generation["artifact_sha256"]), SCHEMA_VERSION,
             verified_at, status, actual),
        )
    return {"attestation_key_sha256": key, "status": status, "verified_row_count": actual}


__all__ = ("has_current_attestation", "record_deep_verification_attestation")
