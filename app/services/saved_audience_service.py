"""Immutable saved-audience service and currentness validation for Phase 6 Step 6."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.database.schema import initialize_database
from app.repositories.audience_rank_repository import AudienceRankRepository
from app.repositories.historical_repository import HistoricalRepository
from app.repositories.model_run_repository import ModelRunRepository
from app.repositories.saved_audience_repository import (
    SavedAudienceNotFoundError,
    SavedAudienceRepository,
    SavedAudienceValidationError,
)
from app.repositories.scoring_repository import ScoringRepository
from app.services.audience_query_service import (
    AUDIENCE_FILTER_CONTRACT_VERSION,
    AUDIENCE_RANK_CONTRACT_VERSION,
    AUDIENCE_SELECTION_CONTRACT_VERSION,
    RANK_BOUNDARIES_NOT_READY_MESSAGE,
    AudienceQueryConflictError,
    AudienceQueryValidationError,
    SCORING_RUN_NOT_CANONICAL_MESSAGE,
    SCORING_RUN_NOT_COMPLETED_MESSAGE,
    SCORING_RUN_NOT_FOUND_MESSAGE,
    _PII_POLICY,
    _SCORE_SEMANTICS,
    _require_prepared_canonical_context,
    estimate_audience,
    normalize_audience_filters,
    normalize_selection,
    profile_audience,
)
from app.services.prospect_scoring_service import (
    resolve_current_scoring_context_lightweight,
)


DEFAULT_SAVED_AUDIENCE_LIST_LIMIT = 20
MAXIMUM_SAVED_AUDIENCE_LIST_LIMIT = 100

SAVED_AUDIENCE_NOT_FOUND_MESSAGE = "The requested saved audience was not found."
SAVED_AUDIENCE_EMPTY_MESSAGE = "The selected audience is empty and cannot be saved."
SAVED_AUDIENCE_EXPORT_POLICY = {
    "export_supported": False,
    "reason": "Phase 6 does not expose saved-audience export APIs.",
}


class SavedAudienceServiceError(RuntimeError):
    """Base class for saved-audience service failures."""


class SavedAudienceServiceValidationError(SavedAudienceServiceError):
    """Raised when saved-audience request or payload constraints are invalid."""


class SavedAudienceServiceConflictError(SavedAudienceServiceError):
    """Raised when saved-audience storage conflicts with current system state."""


class SavedAudienceServiceNotFoundError(SavedAudienceServiceError):
    """Raised when a requested saved audience does not exist."""


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _require_positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SavedAudienceServiceValidationError(f"{field_name} must be a positive integer.")
    return value


def _require_non_empty_text(value: Any, *, field_name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise SavedAudienceServiceValidationError(f"{field_name} must be text.")
    normalized = value.strip()
    if not normalized:
        raise SavedAudienceServiceValidationError(f"{field_name} must not be blank.")
    if len(normalized) > maximum:
        raise SavedAudienceServiceValidationError(f"{field_name} must not exceed {maximum} characters.")
    return normalized


def _optional_bounded_text(value: Any, *, field_name: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SavedAudienceServiceValidationError(f"{field_name} must be text when provided.")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise SavedAudienceServiceValidationError(f"{field_name} must not exceed {maximum} characters.")
    return normalized


def _decode_json_object(raw: Any, *, field_name: str) -> dict[str, Any]:
    if not isinstance(raw, str) or not raw.strip():
        raise SavedAudienceServiceValidationError(f"{field_name} is missing.")
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise SavedAudienceServiceValidationError(f"{field_name} is invalid.") from exc
    if not isinstance(decoded, dict):
        raise SavedAudienceServiceValidationError(f"{field_name} is invalid.")
    return decoded


def _require_bool(value: Any, *, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise SavedAudienceServiceValidationError(f"{field_name} must be a boolean.")
    return value


def _validate_list_bounds(*, limit: int, offset: int) -> tuple[int, int]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAXIMUM_SAVED_AUDIENCE_LIST_LIMIT:
        raise SavedAudienceServiceValidationError(
            f"limit must be an integer between 1 and {MAXIMUM_SAVED_AUDIENCE_LIST_LIMIT}."
        )
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise SavedAudienceServiceValidationError("offset must be a non-negative integer.")
    return limit, offset


def _compact_issue(issue: str) -> str:
    compact = issue.strip()
    if len(compact) <= 160:
        return compact
    return compact[:157].rstrip() + "..."


def _normalized_saved_row_json(row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    filters = _decode_json_object(row.get("filters_json"), field_name="saved_audience.filters_json")
    selection = _decode_json_object(row.get("selection_json"), field_name="saved_audience.selection_json")
    profile_snapshot: dict[str, Any] | None = None
    if row.get("profile_summary_json"):
        profile_snapshot = _decode_json_object(
            row["profile_summary_json"],
            field_name="saved_audience.profile_summary_json",
        )
    return filters, selection, profile_snapshot


def _deduplicate_issues(issues: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for issue in issues:
        normalized = issue.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _evaluate_saved_audience_currentness(
    path: Path,
    row: dict[str, Any],
    *,
    cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    saved_scoring_run_id = int(row["scoring_run_id"])
    saved_model_run_id = int(row["model_run_id"])
    saved_analysis_run_id = int(row["analysis_run_id"])

    shared_cache = {} if cache is None else cache
    scoring_rows_cache: dict[int, dict[str, Any] | None] = shared_cache.setdefault(
        "saved_scoring_rows", {}
    )
    scoring_summary_cache: dict[int, dict[str, Any] | None] = shared_cache.setdefault(
        "saved_scoring_summaries", {}
    )
    scoring_currentness_cache: dict[int, dict[str, Any] | None] = shared_cache.setdefault(
        "saved_scoring_currentness", {}
    )
    analysis_rows_cache: dict[int, dict[str, Any] | None] = shared_cache.setdefault(
        "saved_analysis_rows", {}
    )
    boundaries_cache: dict[int, list[dict[str, Any]]] = shared_cache.setdefault(
        "saved_boundary_rows", {}
    )

    issues: list[str] = []

    if str(row["filter_contract_version"]) != AUDIENCE_FILTER_CONTRACT_VERSION:
        issues.append("Saved filter contract version is no longer supported.")
    if str(row["rank_contract_version"]) != AUDIENCE_RANK_CONTRACT_VERSION:
        issues.append("Saved rank contract version is no longer supported.")
    if str(row["selection_contract_version"]) != AUDIENCE_SELECTION_CONTRACT_VERSION:
        issues.append("Saved selection contract version is no longer supported.")

    if saved_scoring_run_id not in scoring_rows_cache:
        scoring_rows_cache[saved_scoring_run_id] = ScoringRepository(path).fetch_scoring_run(
            saved_scoring_run_id
        )
    scoring_row = scoring_rows_cache[saved_scoring_run_id]
    if scoring_row is None:
        issues.append("Saved scoring run no longer exists.")
    else:
        if str(scoring_row["status"]) != "COMPLETED":
            issues.append("Saved scoring run is no longer completed.")
        if int(scoring_row["model_run_id"]) != saved_model_run_id:
            issues.append("Saved scoring run model linkage has changed.")
        if str(scoring_row["feature_contract_version"]) != str(row["feature_contract_version"]):
            issues.append("Saved scoring run feature contract version mismatch.")
        if (
            str(scoring_row["feature_contract_sha256"]).strip().lower()
            != str(row["feature_contract_sha256"]).strip().lower()
        ):
            issues.append("Saved scoring run feature contract hash mismatch.")
        if str(scoring_row["artifact_sha256"]).strip().lower() != str(row["artifact_sha256"]).strip().lower():
            issues.append("Saved artifact hash no longer matches scoring run provenance.")

        if saved_scoring_run_id not in scoring_summary_cache:
            try:
                scoring_summary_cache[saved_scoring_run_id] = _decode_json_object(
                    scoring_row.get("score_summary_json"),
                    field_name="scoring_run.score_summary_json",
                )
            except SavedAudienceServiceValidationError:
                scoring_summary_cache[saved_scoring_run_id] = None

        summary_payload = scoring_summary_cache[saved_scoring_run_id]
        if summary_payload is None:
            issues.append("Saved scoring run summary payload is invalid.")
        else:
            summary_pairs = (
                ("analysis_run_id", int(row["analysis_run_id"])),
                ("customer_import_id", int(row["customer_import_id"])),
                ("customer_source_checksum", str(row["customer_source_checksum"]).strip().lower()),
                ("campaign_sales_import_id", int(row["campaign_sales_import_id"])),
                (
                    "campaign_sales_source_checksum",
                    str(row["campaign_sales_source_checksum"]).strip().lower(),
                ),
                ("demographic_import_id", int(row["demographic_import_id"])),
                ("demographic_source_checksum", str(row["demographic_source_checksum"]).strip().lower()),
                ("feature_contract_version", str(row["feature_contract_version"])),
                ("feature_contract_sha256", str(row["feature_contract_sha256"]).strip().lower()),
                ("artifact_sha256", str(row["artifact_sha256"]).strip().lower()),
            )
            for key, expected in summary_pairs:
                if summary_payload.get(key) != expected:
                    issues.append(f"Saved {key} no longer matches scoring provenance.")

        if saved_scoring_run_id not in scoring_currentness_cache:
            try:
                scoring_currentness_cache[saved_scoring_run_id] = resolve_current_scoring_context_lightweight(
                    path,
                    scoring_run_id=saved_scoring_run_id,
                    verify_current_source_match=True,
                    cache=shared_cache,
                )
            except Exception:
                scoring_currentness_cache[saved_scoring_run_id] = None

        provenance = scoring_currentness_cache[saved_scoring_run_id]
        if provenance is None:
            issues.append("Saved scoring run provenance could not be validated.")
        else:
            if not provenance["is_canonical"]:
                issues.append("Saved scoring run provenance is stale or invalid.")
                for item in provenance.get("issues", [])[:3]:
                    issues.append(f"provenance: {item}")
            if int(provenance.get("scoring_run_id") or 0) != saved_scoring_run_id:
                issues.append("Saved scoring run provenance is inconsistent.")

    model_row = ModelRunRepository(path).fetch_run(saved_model_run_id)
    if model_row is None:
        issues.append("Saved model run no longer exists.")
    else:
        if str(model_row["status"]) != "COMPLETED":
            issues.append("Saved model run is no longer completed.")
        if int(model_row["analysis_run_id"]) != saved_analysis_run_id:
            issues.append("Saved model-to-analysis linkage has changed.")
        model_artifact_sha = model_row.get("artifact_sha256")
        if not isinstance(model_artifact_sha, str) or (
            model_artifact_sha.strip().lower() != str(row["artifact_sha256"]).strip().lower()
        ):
            issues.append("Saved artifact hash no longer matches model run metadata.")

    if saved_analysis_run_id not in analysis_rows_cache:
        analysis_rows_cache[saved_analysis_run_id] = HistoricalRepository(path).fetch_analysis_run(
            saved_analysis_run_id
        )
    analysis_row = analysis_rows_cache[saved_analysis_run_id]
    if analysis_row is None:
        issues.append("Saved analysis run no longer exists.")
    else:
        if str(analysis_row.get("status")) != "COMPLETED":
            issues.append("Saved analysis run is no longer completed.")
        analysis_pairs = (
            ("customer_import_id", int(row["customer_import_id"])),
            ("customer_source_checksum", str(row["customer_source_checksum"]).strip().lower()),
            ("campaign_sales_import_id", int(row["campaign_sales_import_id"])),
            (
                "campaign_sales_source_checksum",
                str(row["campaign_sales_source_checksum"]).strip().lower(),
            ),
        )
        for key, expected in analysis_pairs:
            if analysis_row.get(key) != expected:
                issues.append(f"Saved {key} no longer matches analysis provenance.")
        # Current historical provenance is validated via canonical scoring currentness.

    if saved_scoring_run_id not in boundaries_cache:
        boundaries_cache[saved_scoring_run_id] = AudienceRankRepository(path).fetch_boundaries(
            saved_scoring_run_id
        )
    boundaries = boundaries_cache[saved_scoring_run_id]
    if len(boundaries) != 100:
        issues.append(RANK_BOUNDARIES_NOT_READY_MESSAGE)
    else:
        for index, boundary in enumerate(boundaries, start=1):
            if int(boundary["percentile_bucket"]) != index:
                issues.append(RANK_BOUNDARIES_NOT_READY_MESSAGE)
                break
            if str(boundary["rank_contract_version"]) != str(row["rank_contract_version"]):
                issues.append("Saved rank boundary contract version no longer matches persisted boundaries.")
                break

    deduped_issues = _deduplicate_issues(issues)
    return {
        "audience_id": int(row["audience_id"]),
        "is_current": len(deduped_issues) == 0,
        "issues": deduped_issues,
    }


def replay_saved_audience_definition(
    database_path: str | Path,
    *,
    audience_id: int,
) -> dict[str, Any]:
    path = initialize_database(database_path)
    try:
        row = SavedAudienceRepository(path).fetch_saved_audience(_require_positive_int(audience_id, field_name="audience_id"))
    except SavedAudienceNotFoundError as exc:
        raise SavedAudienceServiceNotFoundError(SAVED_AUDIENCE_NOT_FOUND_MESSAGE) from exc
    except SavedAudienceValidationError as exc:
        raise SavedAudienceServiceValidationError(str(exc)) from exc

    filters_payload, selection_payload, _ = _normalized_saved_row_json(row)
    return {
        "scoring_run_id": int(row["scoring_run_id"]),
        "filters": filters_payload,
        "selection": selection_payload,
    }


def validate_saved_audience_currentness(
    database_path: str | Path,
    *,
    audience_id: int,
) -> dict[str, Any]:
    path = initialize_database(database_path)
    try:
        row = SavedAudienceRepository(path).fetch_saved_audience(_require_positive_int(audience_id, field_name="audience_id"))
    except SavedAudienceNotFoundError as exc:
        raise SavedAudienceServiceNotFoundError(SAVED_AUDIENCE_NOT_FOUND_MESSAGE) from exc
    except SavedAudienceValidationError as exc:
        raise SavedAudienceServiceValidationError(str(exc)) from exc
    return _evaluate_saved_audience_currentness(path, row, cache={})


def save_audience(
    database_path: str | Path,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(request_payload, dict):
        raise SavedAudienceServiceValidationError("Save audience request must be a JSON object.")

    audience_name = _require_non_empty_text(
        request_payload.get("audience_name"),
        field_name="audience_name",
        maximum=120,
    )
    description = _optional_bounded_text(
        request_payload.get("description"),
        field_name="description",
        maximum=500,
    )
    scoring_run_id = _require_positive_int(
        request_payload.get("scoring_run_id"),
        field_name="scoring_run_id",
    )
    include_profile_snapshot = _require_bool(
        request_payload.get("include_profile_snapshot", True),
        field_name="include_profile_snapshot",
    )

    normalized_filters = normalize_audience_filters(request_payload.get("filters", {}))
    normalized_selection = normalize_selection(request_payload.get("selection", {}))

    try:
        context = _require_prepared_canonical_context(
            database_path,
            scoring_run_id=scoring_run_id,
        )
        path = context.path
        scoring_row = context.scoring_row
    except AudienceQueryConflictError as exc:
        raise SavedAudienceServiceConflictError(str(exc)) from exc
    except AudienceQueryValidationError as exc:
        raise SavedAudienceServiceValidationError(str(exc)) from exc

    profile_snapshot: dict[str, Any] | None = None
    resolved_count: int | None = None
    if include_profile_snapshot:
        try:
            profile = profile_audience(
                path,
                {
                    "scoring_run_id": scoring_run_id,
                    "filters": normalized_filters.payload,
                    "selection": normalized_selection.payload,
                },
            )
        except AudienceQueryConflictError as exc:
            raise SavedAudienceServiceConflictError(str(exc)) from exc
        except AudienceQueryValidationError as exc:
            raise SavedAudienceServiceValidationError(str(exc)) from exc
        resolved_count = int(profile["summary"]["selected"]["count"])
        profile_snapshot = {
            "historical_reference_date": profile["historical_reference_date"],
            "summary": profile["summary"],
            "top_overindexed_traits": profile["top_overindexed_traits"],
        }
    else:
        try:
            estimate = estimate_audience(
                path,
                {
                    "scoring_run_id": scoring_run_id,
                    "filters": normalized_filters.payload,
                    "selection": normalized_selection.payload,
                },
            )
        except AudienceQueryConflictError as exc:
            raise SavedAudienceServiceConflictError(str(exc)) from exc
        except AudienceQueryValidationError as exc:
            raise SavedAudienceServiceValidationError(str(exc)) from exc
        resolved_count = int(estimate["selected_count"])

    if resolved_count is None or resolved_count < 1:
        raise SavedAudienceServiceValidationError(SAVED_AUDIENCE_EMPTY_MESSAGE)

    score_summary = _decode_json_object(
        scoring_row.get("score_summary_json"),
        field_name="scoring_run.score_summary_json",
    )
    created_at = _utc_timestamp()

    try:
        audience_id = SavedAudienceRepository(path).create_saved_audience(
            audience_name=audience_name,
            description=description,
            created_at=created_at,
            scoring_run_id=int(scoring_row["scoring_run_id"]),
            model_run_id=int(scoring_row["model_run_id"]),
            analysis_run_id=_require_positive_int(score_summary.get("analysis_run_id"), field_name="analysis_run_id"),
            selection_mode=str(normalized_selection.payload["mode"]),
            target_count=normalized_selection.payload.get("target_count"),
            resolved_count=resolved_count,
            filter_contract_version=AUDIENCE_FILTER_CONTRACT_VERSION,
            rank_contract_version=AUDIENCE_RANK_CONTRACT_VERSION,
            selection_contract_version=AUDIENCE_SELECTION_CONTRACT_VERSION,
            filters_payload=normalized_filters.payload,
            selection_payload=normalized_selection.payload,
            profile_summary_payload=profile_snapshot,
            customer_import_id=_require_positive_int(score_summary.get("customer_import_id"), field_name="customer_import_id"),
            customer_source_checksum=str(score_summary.get("customer_source_checksum", "")),
            campaign_sales_import_id=_require_positive_int(
                score_summary.get("campaign_sales_import_id"),
                field_name="campaign_sales_import_id",
            ),
            campaign_sales_source_checksum=str(score_summary.get("campaign_sales_source_checksum", "")),
            demographic_import_id=_require_positive_int(
                score_summary.get("demographic_import_id"),
                field_name="demographic_import_id",
            ),
            demographic_source_checksum=str(score_summary.get("demographic_source_checksum", "")),
            feature_contract_version=str(scoring_row["feature_contract_version"]),
            feature_contract_sha256=str(scoring_row["feature_contract_sha256"]),
            artifact_sha256=str(scoring_row["artifact_sha256"]),
        )
    except SavedAudienceValidationError as exc:
        raise SavedAudienceServiceValidationError(str(exc)) from exc

    return get_saved_audience_detail(path, audience_id=audience_id)


def list_saved_audiences(
    database_path: str | Path,
    *,
    limit: int = DEFAULT_SAVED_AUDIENCE_LIST_LIMIT,
    offset: int = 0,
    scoring_run_id: int | None = None,
    model_run_id: int | None = None,
) -> list[dict[str, Any]]:
    normalized_limit, normalized_offset = _validate_list_bounds(limit=limit, offset=offset)
    path = initialize_database(database_path)

    try:
        rows = SavedAudienceRepository(path).list_saved_audiences(
            limit=normalized_limit,
            offset=normalized_offset,
            scoring_run_id=scoring_run_id,
            model_run_id=model_run_id,
        )
    except SavedAudienceValidationError as exc:
        raise SavedAudienceServiceValidationError(str(exc)) from exc

    payload: list[dict[str, Any]] = []
    request_cache: dict[str, Any] = {}
    for row in rows:
        currentness = _evaluate_saved_audience_currentness(path, row, cache=request_cache)
        payload.append(
            {
                "audience_id": int(row["audience_id"]),
                "audience_name": str(row["audience_name"]),
                "description": row.get("description"),
                "created_at": row["created_at"],
                "selection_mode": str(row["selection_mode"]),
                "target_count": int(row["target_count"]) if row.get("target_count") is not None else None,
                "resolved_count": int(row["resolved_count"]),
                "scoring_run_id": int(row["scoring_run_id"]),
                "model_run_id": int(row["model_run_id"]),
                "is_current": bool(currentness["is_current"]),
                "stale_reason": None if currentness["is_current"] else _compact_issue(currentness["issues"][0]),
            }
        )
    return payload


def get_saved_audience_detail(
    database_path: str | Path,
    *,
    audience_id: int,
) -> dict[str, Any]:
    path = initialize_database(database_path)
    normalized_audience_id = _require_positive_int(audience_id, field_name="audience_id")

    try:
        row = SavedAudienceRepository(path).fetch_saved_audience(normalized_audience_id)
    except SavedAudienceNotFoundError as exc:
        raise SavedAudienceServiceNotFoundError(SAVED_AUDIENCE_NOT_FOUND_MESSAGE) from exc
    except SavedAudienceValidationError as exc:
        raise SavedAudienceServiceValidationError(str(exc)) from exc

    filters_payload, selection_payload, profile_snapshot = _normalized_saved_row_json(row)
    currentness = _evaluate_saved_audience_currentness(path, row, cache={})
    replay_payload = replay_saved_audience_definition(path, audience_id=normalized_audience_id)

    return {
        "audience_id": int(row["audience_id"]),
        "audience_name": str(row["audience_name"]),
        "description": row.get("description"),
        "created_at": row["created_at"],
        "definition": {
            "scoring_run_id": int(row["scoring_run_id"]),
            "filters": filters_payload,
            "selection": selection_payload,
            "selection_mode": str(row["selection_mode"]),
            "target_count": int(row["target_count"]) if row.get("target_count") is not None else None,
            "resolved_count": int(row["resolved_count"]),
            "filters_json": row["filters_json"],
            "selection_json": row["selection_json"],
        },
        "contracts": {
            "filter_contract_version": str(row["filter_contract_version"]),
            "rank_contract_version": str(row["rank_contract_version"]),
            "selection_contract_version": str(row["selection_contract_version"]),
        },
        "provenance": {
            "scoring_run_id": int(row["scoring_run_id"]),
            "model_run_id": int(row["model_run_id"]),
            "analysis_run_id": int(row["analysis_run_id"]),
            "customer_import_id": int(row["customer_import_id"]),
            "customer_source_checksum": str(row["customer_source_checksum"]),
            "campaign_sales_import_id": int(row["campaign_sales_import_id"]),
            "campaign_sales_source_checksum": str(row["campaign_sales_source_checksum"]),
            "demographic_import_id": int(row["demographic_import_id"]),
            "demographic_source_checksum": str(row["demographic_source_checksum"]),
            "feature_contract_version": str(row["feature_contract_version"]),
            "feature_contract_sha256": str(row["feature_contract_sha256"]),
            "artifact_sha256": str(row["artifact_sha256"]),
        },
        "profile_snapshot": profile_snapshot,
        "currentness": currentness,
        "score_semantics": _SCORE_SEMANTICS,
        "pii_policy": _PII_POLICY,
        "export_policy": SAVED_AUDIENCE_EXPORT_POLICY,
        "replay_request": replay_payload,
    }


__all__ = (
    "DEFAULT_SAVED_AUDIENCE_LIST_LIMIT",
    "MAXIMUM_SAVED_AUDIENCE_LIST_LIMIT",
    "SAVED_AUDIENCE_EMPTY_MESSAGE",
    "SAVED_AUDIENCE_EXPORT_POLICY",
    "SAVED_AUDIENCE_NOT_FOUND_MESSAGE",
    "SavedAudienceServiceConflictError",
    "SavedAudienceServiceError",
    "SavedAudienceServiceNotFoundError",
    "SavedAudienceServiceValidationError",
    "get_saved_audience_detail",
    "list_saved_audiences",
    "replay_saved_audience_definition",
    "save_audience",
    "validate_saved_audience_currentness",
)
