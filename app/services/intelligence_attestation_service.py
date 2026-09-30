"""Versioned deep-verification attestations for reusable intelligence."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.database.connection import get_connection
from app.database.schema import SCHEMA_VERSION
from app.ml.feature_contract import FEATURE_CONTRACT_SHA256, FEATURE_CONTRACT_VERSION
from app.repositories.model_run_repository import ModelRunRepository
from app.repositories.phase10_intelligence_repository import Phase10IntelligenceRepository
from app.repositories.prospect_scoring_repository import (
    ProspectScoringRepository,
    ProspectScoringValidationError,
)
from app.repositories.scoring_repository import ScoringRepository
from app.services.audience_preparation_service import (
    AUDIENCE_ANALYTICS_CONTRACT_VERSION,
    DEFAULT_RANK_CONTRACT_VERSION,
)
from app.services.historical_source_provenance_service import (
    HistoricalSourceProvenanceError,
    resolve_current_historical_source_provenance,
)
from app.services.phase10_scoring_resolution_service import (
    get_phase10_rank_analytics_readiness,
)
from app.services.prospect_scoring_service import (
    validate_completed_scoring_run_integrity_deep,
)


ATTESTATION_VERIFICATION_CONTRACT_VERSION = "2"
ATTESTATION_INTEGRITY_CONTRACT_VERSION = "2"
_SHA256_FIELDS = (
    "artifact_sha256",
    "feature_contract_sha256",
    "score_semantics_sha256",
    "customer_source_checksum",
    "campaign_sales_source_checksum",
    "demographic_source_checksum",
)
_POSITIVE_ID_FIELDS = (
    "generation_id",
    "analysis_run_id",
    "model_run_id",
    "scoring_run_id",
    "customer_import_id",
    "campaign_sales_import_id",
    "demographic_import_id",
)
_POLICY_FIELDS = (
    "intelligence_generation_contract_version",
    "compatibility_contract_version",
    "historical_window_policy_version",
    "multi_product_positive_policy_version",
    "training_eligibility_policy_version",
    "model_role_policy_version",
    "evaluation_contract_version",
    "automated_training_policy_version",
    "rank_contract_version",
    "analytics_contract_version",
    "lifecycle_policy_version",
)


def _canonical(value: Mapping[str, Any] | list[Any]) -> str:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _authoritative_generation(
    database_path: str | Path, generation: Mapping[str, Any]
) -> dict[str, Any] | None:
    identifier = generation.get("generation_id")
    if isinstance(identifier, bool) or not isinstance(identifier, int) or identifier <= 0:
        return None
    return Phase10IntelligenceRepository(database_path).fetch_generation(identifier)


def _current_sources(database_path: str | Path) -> dict[str, Any] | None:
    try:
        historical = resolve_current_historical_source_provenance(database_path)
        demographic = ProspectScoringRepository(
            database_path
        ).fetch_completed_demographic_import_provenance()
    except (HistoricalSourceProvenanceError, ProspectScoringValidationError):
        return None
    return {
        "customer_import_id": historical.customer_import_id,
        "customer_source_checksum": historical.customer_source_checksum,
        "campaign_sales_import_id": historical.campaign_sales_import_id,
        "campaign_sales_source_checksum": historical.campaign_sales_source_checksum,
        "demographic_import_id": demographic.demographic_import_id,
        "demographic_source_checksum": demographic.demographic_source_checksum,
        "expected_population_count": demographic.demographic_snapshot_count,
    }


def _identity(
    database_path: str | Path, generation: Mapping[str, Any]
) -> tuple[dict[str, Any] | None, list[str]]:
    """Build current immutable identity without scanning propensity scores."""

    reasons: list[str] = []
    current = _authoritative_generation(database_path, generation)
    if current is None:
        return None, ["GENERATION_IDENTITY_MISSING"]
    if current.get("generation_status") != "READY" or current.get(
        "lifecycle_state"
    ) not in {"CURRENT", "REUSABLE", "PROTECTED"}:
        reasons.append("GENERATION_NOT_REUSABLE")
    for field in _POSITIVE_ID_FIELDS:
        value = current.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            reasons.append(f"MISSING_{field.upper()}")
    for field in _SHA256_FIELDS:
        if not _is_sha256(current.get(field)):
            reasons.append(f"INVALID_{field.upper()}")
    if current.get("feature_contract_version") != FEATURE_CONTRACT_VERSION:
        reasons.append("FEATURE_CONTRACT_VERSION_MISMATCH")
    if current.get("feature_contract_sha256") != FEATURE_CONTRACT_SHA256:
        reasons.append("FEATURE_CONTRACT_SHA256_MISMATCH")
    if current.get("rank_contract_version") != DEFAULT_RANK_CONTRACT_VERSION:
        reasons.append("RANK_CONTRACT_VERSION_MISMATCH")
    if current.get("analytics_contract_version") != AUDIENCE_ANALYTICS_CONTRACT_VERSION:
        reasons.append("ANALYTICS_CONTRACT_VERSION_MISMATCH")
    raw_semantics = current.get("score_semantics_json")
    if not isinstance(raw_semantics, str) or _sha256(raw_semantics) != current.get(
        "score_semantics_sha256"
    ):
        reasons.append("SCORE_SEMANTICS_IDENTITY_MISMATCH")

    scoring = None
    model = None
    scoring_id = current.get("scoring_run_id")
    model_id = current.get("model_run_id")
    if isinstance(scoring_id, int) and not isinstance(scoring_id, bool):
        scoring = ScoringRepository(database_path).fetch_scoring_run(scoring_id)
    if isinstance(model_id, int) and not isinstance(model_id, bool):
        model = ModelRunRepository(database_path).fetch_run(model_id)
    if scoring is None:
        reasons.append("SCORING_RUN_MISSING")
    else:
        if scoring.get("status") != "COMPLETED":
            reasons.append("SCORING_RUN_NOT_COMPLETED")
        for field in (
            "model_run_id",
            "artifact_sha256",
            "feature_contract_version",
            "feature_contract_sha256",
        ):
            if scoring.get(field) != current.get(field):
                reasons.append(f"SCORING_{field.upper()}_MISMATCH")
    if model is None:
        reasons.append("MODEL_RUN_MISSING")
    else:
        if model.get("status") != "COMPLETED":
            reasons.append("MODEL_RUN_NOT_COMPLETED")
        if model.get("artifact_sha256") != current.get("artifact_sha256"):
            reasons.append("MODEL_ARTIFACT_MISMATCH")
        if model.get("analysis_run_id") != current.get("analysis_run_id"):
            reasons.append("MODEL_ANALYSIS_LINEAGE_MISMATCH")

    sources = _current_sources(database_path)
    if sources is None:
        reasons.append("CURRENT_SOURCE_IDENTITY_UNAVAILABLE")
        sources = {}
    else:
        for field in (
            "customer_import_id",
            "customer_source_checksum",
            "campaign_sales_import_id",
            "campaign_sales_source_checksum",
            "demographic_import_id",
            "demographic_source_checksum",
        ):
            if current.get(field) != sources[field]:
                reasons.append(f"CURRENT_{field.upper()}_MISMATCH")

    if scoring is not None:
        try:
            summary = json.loads(str(scoring.get("score_summary_json") or ""))
        except (TypeError, ValueError):
            summary = None
        if not isinstance(summary, dict):
            reasons.append("SCORING_SUMMARY_IDENTITY_MISSING")
        else:
            for field in (
                "model_run_id", "analysis_run_id", "customer_import_id",
                "customer_source_checksum", "campaign_sales_import_id",
                "campaign_sales_source_checksum", "demographic_import_id",
                "demographic_source_checksum", "feature_contract_version",
                "feature_contract_sha256", "artifact_sha256",
            ):
                if summary.get(field) != current.get(field):
                    reasons.append(f"SCORING_SUMMARY_{field.upper()}_MISMATCH")

    identity = {
        "verification_contract_version": ATTESTATION_VERIFICATION_CONTRACT_VERSION,
        "integrity_contract_version": ATTESTATION_INTEGRITY_CONTRACT_VERSION,
        "schema_version": SCHEMA_VERSION,
        **{field: current.get(field) for field in _POSITIVE_ID_FIELDS},
        **{field: current.get(field) for field in _SHA256_FIELDS},
        "feature_contract_version": current.get("feature_contract_version"),
        **{field: current.get(field) for field in _POLICY_FIELDS},
    }
    if sources:
        identity["expected_population_count"] = sources["expected_population_count"]
    return identity, list(dict.fromkeys(reasons))


def _key(identity: Mapping[str, Any]) -> str:
    return _sha256(_canonical(identity))


def _rank_analytics_current_lightweight(
    database_path: str | Path, identity: Mapping[str, Any]
) -> bool:
    """Verify bounded rank/analytics metadata without scanning score rows."""

    with get_connection(database_path) as connection:
        boundaries = connection.execute(
            """SELECT COUNT(*) AS boundary_count,
                      MIN(percentile_bucket) AS minimum_bucket,
                      MAX(percentile_bucket) AS maximum_bucket,
                      MIN(rank_contract_version) AS minimum_contract,
                      MAX(rank_contract_version) AS maximum_contract,
                      MIN(total_population) AS minimum_population,
                      MAX(total_population) AS maximum_population
               FROM audience_rank_boundaries WHERE scoring_run_id=?""",
            (int(identity["scoring_run_id"]),),
        ).fetchone()
        analytics = connection.execute(
            """SELECT * FROM audience_analytics_snapshots
               WHERE scoring_run_id=? AND analytics_contract_version=?""",
            (
                int(identity["scoring_run_id"]),
                str(identity["analytics_contract_version"]),
            ),
        ).fetchone()
    expected = int(identity["expected_population_count"])
    if (
        boundaries is None
        or int(boundaries["boundary_count"] or 0) != 100
        or boundaries["minimum_bucket"] != 1
        or boundaries["maximum_bucket"] != 100
        or boundaries["minimum_contract"] != identity["rank_contract_version"]
        or boundaries["maximum_contract"] != identity["rank_contract_version"]
        or boundaries["minimum_population"] != expected
        or boundaries["maximum_population"] != expected
        or analytics is None
    ):
        return False
    analytics_row = dict(analytics)
    for field in (
        "scoring_run_id", "model_run_id", "analysis_run_id",
        "customer_import_id", "customer_source_checksum",
        "campaign_sales_import_id", "campaign_sales_source_checksum",
        "demographic_import_id", "demographic_source_checksum",
        "feature_contract_version", "feature_contract_sha256", "artifact_sha256",
        "rank_contract_version", "analytics_contract_version",
    ):
        if analytics_row.get(field) != identity.get(field):
            return False
    return analytics_row.get("population_count") == expected


def has_current_attestation(
    database_path: str | Path, generation: Mapping[str, Any]
) -> bool:
    """Return true using bounded metadata/currentness checks, never a deep scan."""

    identity, reasons = _identity(database_path, generation)
    if identity is None or reasons:
        return False
    if not _rank_analytics_current_lightweight(database_path, identity):
        return False
    with get_connection(database_path) as connection:
        row = connection.execute(
            """SELECT verification_status FROM intelligence_verification_attestations
               WHERE attestation_key_sha256=? AND verification_status='VERIFIED'
                 AND verification_contract_version=?
                 AND integrity_contract_version=? AND schema_version=?
                 AND verified_facts_sha256 IS NOT NULL
                 AND (expires_at IS NULL OR expires_at > ?)""",
            (
                _key(identity),
                ATTESTATION_VERIFICATION_CONTRACT_VERSION,
                ATTESTATION_INTEGRITY_CONTRACT_VERSION,
                SCHEMA_VERSION,
                datetime.now(timezone.utc).isoformat(),
            ),
        ).fetchone()
    return row is not None


def record_deep_verification_attestation(
    database_path: str | Path, generation: Mapping[str, Any]
) -> dict[str, Any]:
    """Run authoritative deep verification once and persist its exact facts."""

    current = _authoritative_generation(database_path, generation)
    identity, failure_codes = _identity(database_path, generation)
    if current is None or identity is None:
        return {
            "attestation_key_sha256": None,
            "status": "FAILED",
            "verified_row_count": 0,
            "failure_codes": failure_codes,
        }

    integrity: dict[str, Any] = {}
    if not failure_codes:
        try:
            deep = validate_completed_scoring_run_integrity_deep(
                database_path,
                scoring_run_id=int(current["scoring_run_id"]),
                verify_current_source_match=True,
            )
        except Exception:
            failure_codes.append("SCORING_DEEP_INTEGRITY_UNAVAILABLE")
        else:
            integrity = dict(deep.get("score_integrity") or {})
            if not deep.get("is_canonical") or deep.get("issues"):
                failure_codes.append("SCORING_DEEP_INTEGRITY_FAILED")
        try:
            rank = get_phase10_rank_analytics_readiness(
                database_path, int(current["scoring_run_id"])
            )
        except Exception:
            failure_codes.append("RANK_ANALYTICS_VERIFICATION_UNAVAILABLE")
        else:
            if not rank.ready:
                failure_codes.append("RANK_ANALYTICS_NOT_READY")

    expected = int(identity.get("expected_population_count") or 0)
    actual = int(integrity.get("score_count") or 0)
    def count(name: str) -> int:
        value = integrity.get(name)
        return -1 if value is None else int(value)

    if not failure_codes and (
        actual != expected
        or count("distinct_person_count") != expected
        or count("duplicate_person_count") != 0
        or count("missing_person_count") != 0
        or count("extra_person_count") != 0
        or count("invalid_score_count") != 0
    ):
        failure_codes.append("FULL_POPULATION_INTEGRITY_FAILED")

    failure_codes = list(dict.fromkeys(failure_codes))
    facts = {
        "identity": identity,
        "expected_population_count": expected,
        "score_integrity": integrity,
        "failure_codes": failure_codes,
    }
    facts_json = _canonical(facts)
    facts_sha = _sha256(facts_json)
    key = _key(identity)
    source_json = _canonical(
        {
            name: identity[name]
            for name in (
                "customer_import_id",
                "customer_source_checksum",
                "campaign_sales_import_id",
                "campaign_sales_source_checksum",
                "demographic_import_id",
                "demographic_source_checksum",
            )
        }
    )
    verified_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    status = "VERIFIED" if not failure_codes else "FAILED"
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """INSERT OR REPLACE INTO intelligence_verification_attestations (
                   attestation_key_sha256,verification_contract_version,
                   integrity_contract_version,generation_id,scoring_run_id,model_run_id,
                   source_checksums_json,artifact_sha256,feature_contract_version,
                   feature_contract_sha256,score_semantics_sha256,
                   customer_import_id,customer_source_checksum,
                   campaign_sales_import_id,campaign_sales_source_checksum,
                   demographic_import_id,demographic_source_checksum,
                   rank_contract_version,analytics_contract_version,schema_version,
                   verified_facts_json,verified_facts_sha256,failure_codes_json,
                   verified_at,verification_status,verified_row_count
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                key,
                ATTESTATION_VERIFICATION_CONTRACT_VERSION,
                ATTESTATION_INTEGRITY_CONTRACT_VERSION,
                int(current["generation_id"]),
                int(current["scoring_run_id"]),
                int(current["model_run_id"]),
                source_json,
                str(current["artifact_sha256"]),
                str(current["feature_contract_version"]),
                str(current["feature_contract_sha256"]),
                str(current["score_semantics_sha256"]),
                int(current["customer_import_id"]),
                str(current["customer_source_checksum"]),
                int(current["campaign_sales_import_id"]),
                str(current["campaign_sales_source_checksum"]),
                int(current["demographic_import_id"]),
                str(current["demographic_source_checksum"]),
                str(current["rank_contract_version"]),
                str(current["analytics_contract_version"]),
                SCHEMA_VERSION,
                facts_json,
                facts_sha,
                _canonical(failure_codes),
                verified_at,
                status,
                max(0, actual),
            ),
        )
    return {
        "attestation_key_sha256": key,
        "status": status,
        "verified_row_count": max(0, actual),
        "verified_facts_sha256": facts_sha,
        "failure_codes": failure_codes,
    }


__all__ = (
    "ATTESTATION_INTEGRITY_CONTRACT_VERSION",
    "ATTESTATION_VERIFICATION_CONTRACT_VERSION",
    "has_current_attestation",
    "record_deep_verification_attestation",
)
