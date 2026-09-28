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
from app.services.phase10_context_identity_service import derive_modeling_context_from_campaign_context
from app.services.potential_customer_search_submission_service import normalize_search_definition


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _predicates(branch: Mapping[str, Any], *, calibrated: bool) -> tuple[list[str], list[Any]]:
    predicates: list[str] = []
    parameters: list[Any] = []
    numeric = {
        "age_min": "d.age >= ?", "age_max": "d.age <= ?",
        "individual_yearly_income_min": "d.individual_yearly_income >= ?",
        "individual_yearly_income_max": "d.individual_yearly_income <= ?",
        "family_member_count_min": "d.family_member_count >= ?",
        "family_member_count_max": "d.family_member_count <= ?",
    }
    if calibrated:
        numeric.update({
            "score_min": "p.calibrated_probability >= ?",
            "score_max": "p.calibrated_probability <= ?",
            "top_percentile_max": "p.percentile_bucket <= ?",
        })
    for key, predicate in numeric.items():
        if branch.get(key) is not None:
            predicates.append(predicate)
            parameters.append(branch[key])
    if calibrated and branch.get("deciles"):
        marks = ",".join("?" for _ in branch["deciles"])
        predicates.append(f"p.decile IN ({marks})")
        parameters.extend(branch["deciles"])
    if calibrated and branch.get("rank_bands"):
        marks = ",".join("?" for _ in branch["rank_bands"])
        predicates.append(f"p.rank_band IN ({marks})")
        parameters.extend(branch["rank_bands"])
    for field in (
        "gender", "state", "marital_status", "education", "employment_status",
        "resident_status", "resident_type", "type_of_employment",
    ):
        values = branch.get(field) or []
        if values:
            marks = ",".join("?" for _ in values)
            predicates.append(
                f"COALESCE(NULLIF(TRIM(CAST(d.{field} AS TEXT)),''),'Unknown/Other') IN ({marks})"
            )
            parameters.extend(values)
    return predicates, parameters


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
        predicates, values = _predicates(branch, calibrated=calibrated)
        if calibrated:
            predicates.insert(0, "p.calibration_artifact_id=?")
            values.insert(0, calibration_id)
            if propensity_bucket is not None:
                predicates.insert(1, "p.propensity_bucket=?")
                values.insert(1, propensity_bucket)
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
            predicates, values = _predicates(branch, calibrated=False)
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
    prepared: list[dict[str, Any]] = []
    for request in requests:
        bucket = str(request["propensity_bucket"])
        normalized_context, normalized_criteria, _catalog = normalize_search_definition(
            path,
            raw_context=dict(request["context"]),
            raw_criteria=dict(request["criteria"]),
            propensity_bucket=bucket,
            catalog_version=request.get("catalog_version"),
        )
        identity = derive_modeling_context_from_campaign_context(normalized_context)
        generations = repository.find_generations_by_modeling_context(
            identity.modeling_context_sha256,
            limit=20,
        )
        generation = next(
            (
                item
                for item in generations
                if item["generation_status"] == "READY"
                and item["lifecycle_state"] in {"CURRENT", "REUSABLE", "PROTECTED"}
            ),
            None,
        )
        calibration_id: int | None = None
        if generation is not None:
            with get_connection(path) as connection:
                calibration = connection.execute(
                    """SELECT calibration_artifact_id FROM score_calibration_artifacts
                       WHERE scoring_run_id=? AND status='PROMOTED'
                       ORDER BY promoted_at DESC,calibration_artifact_id DESC LIMIT 1""",
                    (int(generation["scoring_run_id"]),),
                ).fetchone()
            if calibration is not None:
                calibration_id = int(calibration["calibration_artifact_id"])
        branches = [dict(item) for item in normalized_criteria.audience_filter_branches]
        prepared.append(
            {
                "bucket": bucket,
                "criteria": normalized_criteria,
                "branches": branches,
                "generation": generation,
                "calibration_id": calibration_id,
            }
        )

    demographic_counts = [0] * len(prepared)
    uncached_indices: list[int] = []
    for index, item in enumerate(prepared):
        generation = item["generation"]
        calibration_id = item["calibration_id"]
        item["cache_key"] = None
        item["cached"] = None
        if generation is not None and calibration_id is not None:
            cache_payload = {
                "criteria_sha256": item["criteria"].sha256,
                "generation_id": int(generation["generation_id"]),
                "calibration_artifact_id": calibration_id,
            }
            cache_key = hashlib.sha256(
                json.dumps(
                    cache_payload,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
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
        criteria = item["criteria"]
        bucket = item["bucket"]
        if generation is None:
            results.append(
                {
                    "demographic_count": demographic_count,
                    "bucket_count": 0,
                    "intersection_count": 0,
                    "demo_ready": False,
                    "generation_id": None,
                    "scoring_run_id": None,
                    "calibration_artifact_id": None,
                    "calibration_currentness": "NOT_AVAILABLE",
                    "safe_message": "Compatible targeting intelligence has not been prepared yet.",
                    "criteria_sha256": criteria.sha256,
                }
            )
            continue
        if calibration_id is None:
            results.append(
                {
                    "demographic_count": demographic_count,
                    "bucket_count": 0,
                    "intersection_count": 0,
                    "demo_ready": False,
                    "generation_id": int(generation["generation_id"]),
                    "scoring_run_id": int(generation["scoring_run_id"]),
                    "calibration_artifact_id": None,
                    "calibration_currentness": "NOT_AVAILABLE",
                    "safe_message": "Compatible intelligence exists, but calibrated probabilities are not ready.",
                    "criteria_sha256": criteria.sha256,
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
                _union_count(
                    path,
                    item["branches"],
                    calibration_id=calibration_id,
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
        results.append(
            {
                "demographic_count": demographic_count,
                "bucket_count": bucket_count,
                "intersection_count": intersection_count,
                "demo_ready": intersection_count >= 10_000,
                "generation_id": int(generation["generation_id"]),
                "scoring_run_id": int(generation["scoring_run_id"]),
                "calibration_artifact_id": calibration_id,
                "calibration_currentness": "CURRENT",
                "safe_message": (
                    "This exact selection is demo-ready."
                    if intersection_count >= 10_000
                    else "This exact selection contains fewer than 10,000 potential customers; filters were not widened."
                ),
                "criteria_sha256": criteria.sha256,
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


__all__ = ("exact_preflight", "exact_preflight_many")
