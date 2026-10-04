"""Exact, non-mutating calibrated audience preflight counts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories.phase10_intelligence_repository import Phase10IntelligenceRepository
from app.selection_contracts import DEMO_QUALIFICATION_MINIMUM
from app.services.intelligence_attestation_service import has_current_attestation
from app.services.phase10_context_identity_service import derive_modeling_context_from_campaign_context
from app.services.potential_customer_search_submission_service import normalize_search_definition
from app.services.source_currentness_service import (
    generation_sources_match,
    latest_source_identity,
    public_calibration_currentness,
    resolve_governed_calibration_eligibility,
)
from app.services.calibrated_selection_contract_service import (
    CALIBRATED_SELECTION_CONTRACT_VERSION,
    build_branch_predicates,
    propensity_bucket_bounds,
)


PREFLIGHT_CACHE_CONTRACT_VERSION = "2"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_preflight_cache_key(
    *,
    criteria_sha256: str,
    filter_branches_sha256: str,
    catalog_version: str,
    source_identity: Mapping[str, Any],
    generation_id: int,
    scoring_run_id: int,
    calibration_artifact_id: int,
    propensity_bucket: str,
    selection_mode: str,
    target_count: int | None,
) -> str:
    """Hash every lineage and selection component that can change a count."""

    payload = {
        "preflight_cache_contract_version": PREFLIGHT_CACHE_CONTRACT_VERSION,
        "calibrated_selection_contract_version": CALIBRATED_SELECTION_CONTRACT_VERSION,
        "selection_contract_version": CALIBRATED_SELECTION_CONTRACT_VERSION,
        "criteria_sha256": criteria_sha256,
        "filter_branches_sha256": filter_branches_sha256,
        "catalog_version": catalog_version,
        "source_identity": dict(source_identity),
        "generation_id": generation_id,
        "scoring_run_id": scoring_run_id,
        "calibration_artifact_id": calibration_artifact_id,
        "propensity_bucket": propensity_bucket,
        "propensity_bucket_bounds": propensity_bucket_bounds(propensity_bucket),
        "selection_mode": selection_mode,
        "target_count": target_count,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _union_count(
    path: Path,
    branches: list[Mapping[str, Any]],
    *,
    calibration_id: int | None,
    propensity_bucket: str | None = None,
) -> int:
    selects: list[str] = []
    parameters: list[Any] = []
    calibrated = calibration_id is not None
    for branch in branches:
        predicates, values = build_branch_predicates(
            branch,
            calibrated=calibrated,
            calibration_artifact_id=calibration_id,
            propensity_bucket=propensity_bucket,
        )
        if calibrated:
            source = "calibrated_propensity_scores AS p JOIN demographics AS d ON d.person_id=p.person_id"
            identity = "p.person_id"
        else:
            source = "demographics AS d"
            identity = "d.person_id"
        selects.append(
            f"SELECT {identity} AS person_id FROM {source}"
            + (" WHERE " + " AND ".join(predicates) if predicates else "")
        )
        parameters.extend(values)
    with get_connection(path) as connection:
        return int(connection.execute(
            "SELECT COUNT(*) FROM (" + " UNION ".join(selects) + ")",
            tuple(parameters),
        ).fetchone()[0])


def count_calibrated_members(
    database_path: str | Path,
    branches: list[Mapping[str, Any]],
    *,
    calibration_artifact_id: int,
    propensity_bucket: str,
) -> int:
    """Count the exact de-duplicated membership emitted by the v2 iterator."""

    return _union_count(
        Path(database_path),
        branches,
        calibration_id=calibration_artifact_id,
        propensity_bucket=propensity_bucket,
    )


def _demographic_counts_many(
    path: Path,
    branches_by_request: list[list[Mapping[str, Any]]],
) -> list[int]:
    """Count several exact demographic definitions in one source-table pass."""

    if not branches_by_request:
        return []
    expressions: list[str] = []
    parameters: list[Any] = []
    for index, branches in enumerate(branches_by_request):
        branch_expressions: list[str] = []
        for branch in branches:
            predicates, values = build_branch_predicates(branch, calibrated=False)
            branch_expressions.append(
                "(" + (" AND ".join(predicates) if predicates else "1") + ")"
            )
            parameters.extend(values)
        condition = " OR ".join(branch_expressions) if branch_expressions else "0"
        expressions.append(
            f"SUM(CASE WHEN ({condition}) THEN 1 ELSE 0 END) AS count_{index}"
        )
    with get_connection(path) as connection:
        row = connection.execute(
            "SELECT " + ",".join(expressions) + " FROM demographics AS d",
            tuple(parameters),
        ).fetchone()
    return [int(row[f"count_{index}"] or 0) for index in range(len(expressions))]


def exact_preflight_many(
    database_path: str | Path,
    requests: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve several exact preflights with one demographic-table pass."""

    if not requests:
        return []
    path = initialize_database(database_path)
    repository = Phase10IntelligenceRepository(path)
    current_sources = latest_source_identity(path)
    source_identity_payload = {
        name: {"import_id": identity[0], "source_checksum": identity[1]}
        for name, identity in sorted(current_sources.items())
    }
    source_identity_sha256 = hashlib.sha256(
        json.dumps(
            source_identity_payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    prepared: list[dict[str, Any]] = []
    for request in requests:
        bucket = str(request["propensity_bucket"])
        normalized_context, normalized_criteria, catalog = normalize_search_definition(
            path,
            raw_context=dict(request["context"]),
            raw_criteria=dict(request["criteria"]),
            propensity_bucket=bucket,
            catalog_version=request.get("catalog_version"),
            require_current_catalog=False,
        )
        identity = derive_modeling_context_from_campaign_context(normalized_context)
        generations = repository.find_generations_by_modeling_context(
            identity.modeling_context_sha256,
            limit=20,
        )
        reusable = [
            item for item in generations
            if item["generation_status"] == "READY"
            and item["lifecycle_state"] in {"CURRENT", "REUSABLE", "PROTECTED"}
        ]
        generation = next(
            (item for item in reusable if has_current_attestation(path, item)),
            reusable[0] if reusable else None,
        )
        source_current = generation_sources_match(path, generation)
        attestation_current = bool(
            generation is not None and has_current_attestation(path, generation)
        )
        if not catalog.get("is_current", True):
            lineage_state = "STALE"
        elif attestation_current:
            lineage_state = "CURRENT"
        elif generation is not None and not source_current:
            lineage_state = "STALE"
        elif generation is not None:
            lineage_state = "UNVERIFIED"
        else:
            lineage_state = "NOT_AVAILABLE"
        calibration_id: int | None = None
        calibration_status: str | None = None
        calibration_eligibility = resolve_governed_calibration_eligibility(
            path, generation
        )
        if generation is not None:
            calibration_id = calibration_eligibility.calibration_artifact_id
            calibration_status = calibration_eligibility.status
        branches = [dict(item) for item in normalized_criteria.audience_filter_branches]
        branches_sha256 = hashlib.sha256(
            json.dumps(branches, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        selection_mode = str(normalized_criteria.audience_selection["mode"])
        target_count = normalized_criteria.audience_selection.get("target_count")
        prepared.append(
            {
                "bucket": bucket,
                "criteria": normalized_criteria,
                "branches": branches,
                "generation": generation,
                "calibration_id": calibration_id,
                "calibration_status": calibration_status,
                "calibration_eligibility": calibration_eligibility,
                "lineage_state": lineage_state,
                "catalog_version": str(catalog["catalog_version"]),
                "branches_sha256": branches_sha256,
                "selection_mode": selection_mode,
                "target_count": target_count,
            }
        )

    demographic_counts = [0] * len(prepared)
    uncached_indices: list[int] = []
    for index, item in enumerate(prepared):
        generation = item["generation"]
        calibration_id = item["calibration_id"]
        item["cache_key"] = None
        item["cached"] = None
        if (
            generation is not None
            and calibration_id is not None
            and item["lineage_state"] == "CURRENT"
            and item["calibration_eligibility"].eligible
        ):
            cache_key = build_preflight_cache_key(
                criteria_sha256=item["criteria"].sha256,
                filter_branches_sha256=item["branches_sha256"],
                catalog_version=item["catalog_version"],
                source_identity=source_identity_payload,
                generation_id=int(generation["generation_id"]),
                scoring_run_id=int(generation["scoring_run_id"]),
                calibration_artifact_id=calibration_id,
                propensity_bucket=item["bucket"],
                selection_mode=item["selection_mode"],
                target_count=item["target_count"],
            )
            with get_connection(path) as connection:
                cached = connection.execute(
                    """SELECT * FROM search_preflight_cache
                       WHERE cache_key_sha256=? AND currentness_state='CURRENT'""",
                    (cache_key,),
                ).fetchone()
            item["cache_key"] = cache_key
            item["cached"] = cached
            if cached is not None:
                demographic_counts[index] = int(cached["demographic_count"])
                continue
        uncached_indices.append(index)
    uncached_counts = _demographic_counts_many(
        path,
        [prepared[index]["branches"] for index in uncached_indices],
    )
    for index, count in zip(uncached_indices, uncached_counts, strict=True):
        demographic_counts[index] = count
    results: list[dict[str, Any]] = []
    for item, demographic_count in zip(prepared, demographic_counts, strict=True):
        generation = item["generation"]
        calibration_id = item["calibration_id"]
        calibration_status = item["calibration_status"]
        calibration_eligibility = item["calibration_eligibility"]
        lineage_state = item["lineage_state"]
        criteria = item["criteria"]
        bucket = item["bucket"]
        response_identity = {
            "catalog_version": item["catalog_version"],
            "source_identity_sha256": source_identity_sha256,
            "filter_branches_sha256": item["branches_sha256"],
            "selection_contract_version": CALIBRATED_SELECTION_CONTRACT_VERSION,
            "selection_mode": item["selection_mode"],
            "target_count": item["target_count"],
        }
        if generation is None:
            results.append(
                {
                    "demographic_count": demographic_count,
                    "bucket_count": 0,
                    "intersection_count": 0,
                    "qualifying_count": 0,
                    "selected_count": 0,
                    "demo_ready": False,
                    "generation_id": None,
                    "scoring_run_id": None,
                    "calibration_artifact_id": calibration_id,
                    "calibration_currentness": "NOT_AVAILABLE",
                    "calibration_eligibility": "NOT_ELIGIBLE",
                    "calibration_reason_code": (
                        calibration_eligibility.reason_code
                    ),
                    "safe_message": "Compatible targeting intelligence has not been prepared yet.",
                    "criteria_sha256": criteria.sha256,
                    **response_identity,
                }
            )
            continue
        if lineage_state != "CURRENT":
            results.append(
                {
                    "demographic_count": demographic_count,
                    "bucket_count": 0,
                    "intersection_count": 0,
                    "qualifying_count": 0,
                    "selected_count": 0,
                    "demo_ready": False,
                    "generation_id": int(generation["generation_id"]),
                    "scoring_run_id": int(generation["scoring_run_id"]),
                    "calibration_artifact_id": calibration_id,
                    "calibration_currentness": lineage_state,
                    "calibration_eligibility": "NOT_ELIGIBLE",
                    "calibration_reason_code": (
                        "AUTHORITATIVE_SOURCES_STALE"
                        if lineage_state == "STALE"
                        else "CURRENT_ATTESTATION_REQUIRED"
                    ),
                    "safe_message": (
                        "Targeting intelligence is stale because an authoritative source changed. Prepare current intelligence before using this count."
                        if lineage_state == "STALE"
                        else "Targeting intelligence has not passed current deep verification. Verify it before using calibrated counts."
                    ),
                    "criteria_sha256": criteria.sha256,
                    **response_identity,
                }
            )
            continue
        if not calibration_eligibility.eligible:
            results.append(
                {
                    "demographic_count": demographic_count,
                    "bucket_count": 0,
                    "intersection_count": 0,
                    "qualifying_count": 0,
                    "selected_count": 0,
                    "demo_ready": False,
                    "generation_id": int(generation["generation_id"]),
                    "scoring_run_id": int(generation["scoring_run_id"]),
                    "calibration_artifact_id": calibration_id,
                    "calibration_currentness": public_calibration_currentness(
                        calibration_eligibility
                    ),
                    "calibration_eligibility": "NOT_ELIGIBLE",
                    "calibration_reason_code": calibration_eligibility.reason_code,
                    "safe_message": calibration_eligibility.safe_message,
                    "criteria_sha256": criteria.sha256,
                    **response_identity,
                }
            )
            continue
        cache_key = str(item["cache_key"])
        cached = item["cached"]
        if cached is not None:
            demographic_count = int(cached["demographic_count"])
            bucket_count = int(cached["bucket_count"])
            intersection_count = int(cached["intersection_count"])
        else:
            with get_connection(path) as connection:
                bucket_count = int(
                    connection.execute(
                        """SELECT COUNT(*) FROM calibrated_propensity_scores
                           WHERE calibration_artifact_id=? AND propensity_bucket=?""",
                        (calibration_id, bucket),
                    ).fetchone()[0]
                )
            intersection_count = (
                count_calibrated_members(
                    path,
                    item["branches"],
                    calibration_artifact_id=calibration_id,
                    propensity_bucket=bucket,
                )
                if bucket_count
                else 0
            )
            now = _now()
            with get_connection(path, write=True) as connection:
                connection.execute(
                    """INSERT OR REPLACE INTO search_preflight_cache (
                           cache_key_sha256,criteria_sha256,generation_id,
                           calibration_artifact_id,demographic_count,bucket_count,
                           intersection_count,currentness_state,created_at,last_used_at
                       ) VALUES (?,?,?,?,?,?,?,'CURRENT',?,?)""",
                    (
                        cache_key,
                        criteria.sha256,
                        int(generation["generation_id"]),
                        calibration_id,
                        demographic_count,
                        bucket_count,
                        intersection_count,
                        now,
                        now,
                    ),
                )
        selected_count = (
            min(intersection_count, int(item["target_count"]))
            if item["selection_mode"] == "TOP_N" and item["target_count"] is not None
            else intersection_count
        )
        results.append(
            {
                "demographic_count": demographic_count,
                "bucket_count": bucket_count,
                "intersection_count": intersection_count,
                "qualifying_count": intersection_count,
                "selected_count": selected_count,
                "demo_ready": selected_count >= DEMO_QUALIFICATION_MINIMUM,
                "generation_id": int(generation["generation_id"]),
                "scoring_run_id": int(generation["scoring_run_id"]),
                "calibration_artifact_id": calibration_id,
                "calibration_currentness": "CURRENT",
                "calibration_eligibility": "ELIGIBLE",
                "calibration_reason_code": "ELIGIBLE",
                "safe_message": (
                    "This exact selection is demo-ready."
                    if selected_count >= DEMO_QUALIFICATION_MINIMUM
                    else (
                        f"{intersection_count:,} potential customers qualify and the saved TOP_N selection would return {selected_count:,}; filters were not widened."
                        if item["selection_mode"] == "TOP_N"
                        else (
                            "This exact selection contains fewer than "
                            f"{DEMO_QUALIFICATION_MINIMUM:,} potential customers; "
                            "filters were not widened."
                        )
                    )
                ),
                "criteria_sha256": criteria.sha256,
                **response_identity,
            }
        )
    return results


def exact_preflight(
    database_path: str | Path,
    *,
    context: dict[str, Any],
    criteria: dict[str, Any],
    propensity_bucket: str,
    catalog_version: str | None,
) -> dict[str, Any]:
    return exact_preflight_many(
        database_path,
        [
            {
                "context": context,
                "criteria": criteria,
                "propensity_bucket": propensity_bucket,
                "catalog_version": catalog_version,
            }
        ],
    )[0]


__all__ = (
    "PREFLIGHT_CACHE_CONTRACT_VERSION", "build_preflight_cache_key",
    "count_calibrated_members",
    "exact_preflight", "exact_preflight_many",
)
