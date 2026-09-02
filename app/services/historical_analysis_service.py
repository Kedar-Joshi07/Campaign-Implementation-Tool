"""Authoritative customer-grain cohort analysis and saved-run lifecycle."""

from __future__ import annotations

import json
import logging
import math
import traceback
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.repositories.historical_repository import HistoricalRepository
from app.schemas.historical import HistoricalAnalysisFilters
from app.services.historical_source_provenance_service import (
    HistoricalSourceProvenance,
    HistoricalSourceProvenanceError,
    is_saved_analysis_provenance_current,
    resolve_current_historical_source_provenance,
)
from app.services.historical_service import _normalize_aggregate


logger = logging.getLogger(__name__)

PROFILE_GROUPS = ("selected", "positive", "unlabeled", "historical_baseline")
PROFILE_DIMENSIONS = (
    "age_band",
    "gender",
    "state",
    "individual_income_band",
    "marital_status",
    "education",
    "employment_status",
    "resident_status",
    "resident_type",
    "family_member_count_band",
    "type_of_employment",
)
_BAND_ORDERS = {
    "age_band": (
        "18–24", "25–34", "35–44", "45–54", "55–64", "65+", "Unknown/Other"
    ),
    "individual_income_band": (
        "<25K", "25K–49,999", "50K–74,999", "75K–99,999",
        "100K–149,999", "150K–249,999", "250K+", "Unknown/Other",
    ),
    "family_member_count_band": ("1", "2", "3–4", "5+", "Unknown/Other"),
}
_RESULT_KEYS = {
    "summary",
    "monthly_trend",
    "channel_performance",
    "product_category_performance",
    "top_campaigns",
    "top_products",
    "profiles",
}
_SUMMARY_KEYS = {
    "observation_count",
    "selected_customer_count",
    "positive_customer_count",
    "unlabeled_customer_count",
    "positive_customer_rate",
    "response_count",
    "purchase_count",
    "attributed_purchase_count",
    "net_sales_amount",
    "gross_margin_amount",
}
_FORBIDDEN_RESULT_KEYS = {
    "customer_id",
    "person_id",
    "first_name",
    "last_name",
    "address_line_1",
    "address_line_2",
    "street",
    "postal_code",
    "phone_number",
    "email",
    "sql",
    "path",
}


class HistoricalAnalysisError(Exception):
    """Base class whose message is safe to expose through a future API."""


class HistoricalAnalysisValidationError(HistoricalAnalysisError):
    pass


class HistoricalDataNotReadyError(HistoricalAnalysisError):
    pass


class NoMatchingObservationsError(HistoricalAnalysisError):
    pass


class HistoricalDataIntegrityError(HistoricalAnalysisError):
    pass


class HistoricalAnalysisExecutionError(HistoricalAnalysisError):
    pass


class HistoricalAnalysisNotFoundError(HistoricalAnalysisError):
    pass


class HistoricalSavedRunError(HistoricalAnalysisError):
    pass


def _assert_historical_source_provenance_stable(
    *,
    captured: HistoricalSourceProvenance,
    current: HistoricalSourceProvenance,
) -> None:
    if captured.customer_import_id != current.customer_import_id:
        raise HistoricalDataIntegrityError(
            "Historical customer import provenance changed during analysis execution."
        )
    if captured.customer_source_checksum != current.customer_source_checksum:
        raise HistoricalDataIntegrityError(
            "Historical customer source checksum changed during analysis execution."
        )
    if captured.campaign_sales_import_id != current.campaign_sales_import_id:
        raise HistoricalDataIntegrityError(
            "Historical campaign_sales import provenance changed during analysis execution."
        )
    if captured.campaign_sales_source_checksum != current.campaign_sales_source_checksum:
        raise HistoricalDataIntegrityError(
            "Historical campaign_sales source checksum changed during analysis execution."
        )


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _stable_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def normalize_historical_filters(
    database_path: str | Path,
    value: HistoricalAnalysisFilters | dict[str, Any],
) -> HistoricalAnalysisFilters:
    try:
        filters = (
            value
            if isinstance(value, HistoricalAnalysisFilters)
            else HistoricalAnalysisFilters.model_validate(value)
        )
    except ValidationError as exc:
        raise HistoricalAnalysisValidationError(
            "Historical analysis filters are invalid."
        ) from exc

    available = HistoricalRepository(database_path).fetch_available_date_range()
    if available["available_date_from"] is None or available["available_date_to"] is None:
        raise HistoricalDataNotReadyError("Historical campaign data is not loaded.")

    try:
        available_from = date.fromisoformat(available["available_date_from"])
        available_to = date.fromisoformat(available["available_date_to"])
        normalized_from = filters.contact_date_from or available_from
        normalized_to = filters.contact_date_to or available_to
        if normalized_from < available_from or normalized_to > available_to:
            raise HistoricalAnalysisValidationError(
                "Historical analysis dates must be within the available contact-date range."
            )
        analysis_name = filters.analysis_name or (
            f"Historical analysis: {normalized_from.isoformat()} to {normalized_to.isoformat()}"
        )
        return HistoricalAnalysisFilters.model_validate(
            {
                **filters.model_dump(),
                "analysis_name": analysis_name,
                "contact_date_from": normalized_from,
                "contact_date_to": normalized_to,
            }
        )
    except HistoricalAnalysisValidationError:
        raise
    except (ValidationError, ValueError) as exc:
        raise HistoricalAnalysisValidationError(
            "Historical analysis filters are invalid."
        ) from exc


def _profile_group_counts(
    summary: dict[str, Any],
    profile_rows: list[dict[str, Any]],
) -> dict[str, int]:
    counts = {
        "selected": summary["selected_customer_count"],
        "positive": summary["positive_customer_count"],
        "unlabeled": summary["unlabeled_customer_count"],
        "historical_baseline": 0,
    }
    counts["historical_baseline"] = sum(
        int(row["category_count"])
        for row in profile_rows
        if row["group_name"] == "historical_baseline"
        and row["dimension"] == PROFILE_DIMENSIONS[0]
    )
    return counts


def _compose_profiles(
    profile_rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Any]:
    group_counts = _profile_group_counts(summary, profile_rows)
    profiles = {
        group: {
            dimension: {"group_count": group_counts[group], "categories": []}
            for dimension in PROFILE_DIMENSIONS
        }
        for group in PROFILE_GROUPS
    }

    for row in profile_rows:
        group_name = row["group_name"]
        dimension = row["dimension"]
        if group_name not in profiles or dimension not in profiles[group_name]:
            raise RuntimeError("Unexpected profile group or dimension returned by SQLite")
        count = int(row["category_count"])
        group_count = group_counts[group_name]
        profiles[group_name][dimension]["categories"].append(
            {
                "label": row["category"],
                "count": count,
                "share": round(count / group_count, 6) if group_count else 0.0,
            }
        )

    for group_name, group in profiles.items():
        for dimension, profile in group.items():
            categories = profile["categories"]
            if sum(item["count"] for item in categories) != group_counts[group_name]:
                raise RuntimeError("Profile categories do not reconcile with their group count")
            if dimension in _BAND_ORDERS:
                positions = {
                    label: index for index, label in enumerate(_BAND_ORDERS[dimension])
                }
                categories.sort(
                    key=lambda item: (
                        positions.get(item["label"], len(positions)),
                        item["label"].casefold(),
                        item["label"],
                    )
                )
            else:
                categories.sort(
                    key=lambda item: (
                        -item["count"],
                        item["label"].casefold(),
                        item["label"],
                    )
                )
    return profiles


def _compose_analysis_result(raw: dict[str, Any]) -> dict[str, Any]:
    raw_summary = raw["summary"]
    if int(raw_summary["observation_count"] or 0) == 0:
        raise NoMatchingObservationsError(
            "No campaign observations match the selected filters."
        )
    if int(raw_summary["pu_consistency_violation_count"] or 0) > 0:
        raise HistoricalDataIntegrityError(
            "Historical campaign data failed consistency checks."
        )

    aggregate = _normalize_aggregate(raw_summary)
    selected_count = int(raw_summary["selected_customer_count"] or 0)
    positive_count = int(raw_summary["positive_customer_count"] or 0)
    unlabeled_count = int(raw_summary["unlabeled_customer_count"] or 0)
    if positive_count + unlabeled_count != selected_count:
        raise RuntimeError("Positive and unlabeled customer counts do not reconcile")

    summary = {
        "observation_count": aggregate["observation_count"],
        "selected_customer_count": selected_count,
        "positive_customer_count": positive_count,
        "unlabeled_customer_count": unlabeled_count,
        "positive_customer_rate": (
            round(positive_count / selected_count, 6) if selected_count else 0.0
        ),
        "response_count": aggregate["response_count"],
        "purchase_count": aggregate["purchase_count"],
        "attributed_purchase_count": aggregate["attributed_purchase_count"],
        "net_sales_amount": aggregate["net_sales_amount"],
        "gross_margin_amount": aggregate["gross_margin_amount"],
    }
    return {
        "summary": summary,
        "monthly_trend": [
            _normalize_aggregate(row) for row in raw["monthly_trend"]
        ],
        "channel_performance": [
            _normalize_aggregate(row) for row in raw["channel_performance"]
        ],
        "product_category_performance": [
            _normalize_aggregate(row)
            for row in raw["product_category_performance"]
        ],
        "top_campaigns": [
            _normalize_aggregate(row) for row in raw["top_campaigns"]
        ],
        "top_products": [
            _normalize_aggregate(row) for row in raw["top_products"]
        ],
        "profiles": _compose_profiles(raw["profile_rows"], summary),
    }


def _decode_json_object(raw_value: str, *, label: str) -> dict[str, Any]:
    try:
        decoded = json.loads(
            raw_value,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"Invalid JSON constant: {value}")
            ),
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"Stored {label} JSON is invalid") from exc
    if not isinstance(decoded, dict):
        raise ValueError(f"Stored {label} JSON must be an object")
    return decoded


def _decode_filters(row: dict[str, Any]) -> dict[str, Any]:
    payload = _decode_json_object(row["filters_json"], label="filters")
    try:
        filters = HistoricalAnalysisFilters.model_validate(
            {"analysis_name": row["analysis_name"], **payload}
        )
    except ValidationError as exc:
        raise ValueError("Stored filters do not match the filter contract") from exc
    normalized = filters.filter_payload()
    if (
        payload != normalized
        or filters.analysis_name != row["analysis_name"]
        or filters.conversion_definition != row["conversion_definition"]
    ):
        raise ValueError("Stored filters are not normalized or consistent")
    if filters.contact_date_from is None or filters.contact_date_to is None:
        raise ValueError("Stored filters do not contain normalized dates")
    return normalized


def _assert_no_forbidden_keys(value: Any) -> None:
    if isinstance(value, dict):
        if _FORBIDDEN_RESULT_KEYS.intersection(value):
            raise ValueError("Stored results contain prohibited fields")
        for nested in value.values():
            _assert_no_forbidden_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_keys(nested)


def _decode_results(row: dict[str, Any]) -> dict[str, Any]:
    if row["results_json"] is None:
        raise ValueError("Completed analysis has no results")
    results = _decode_json_object(row["results_json"], label="results")
    if set(results) != _RESULT_KEYS:
        raise ValueError("Stored results do not match the completed result contract")
    if not isinstance(results["summary"], dict) or set(results["summary"]) != _SUMMARY_KEYS:
        raise ValueError("Stored results summary is invalid")
    for field in (
        "monthly_trend",
        "channel_performance",
        "product_category_performance",
        "top_campaigns",
        "top_products",
    ):
        if not isinstance(results[field], list) or not all(
            isinstance(item, dict) for item in results[field]
        ):
            raise ValueError(f"Stored results field {field} must be a list")
    if not isinstance(results["profiles"], dict) or set(results["profiles"]) != set(
        PROFILE_GROUPS
    ):
        raise ValueError("Stored results profiles are invalid")

    summary = results["summary"]
    for field in (
        "observation_count",
        "selected_customer_count",
        "positive_customer_count",
        "unlabeled_customer_count",
        "response_count",
        "purchase_count",
        "attributed_purchase_count",
    ):
        if not isinstance(summary[field], int) or summary[field] < 0:
            raise ValueError("Stored results contain an invalid count")
    for field in ("positive_customer_rate", "net_sales_amount", "gross_margin_amount"):
        if (
            not isinstance(summary[field], (int, float))
            or not math.isfinite(summary[field])
        ):
            raise ValueError("Stored results contain a non-finite number")
    if not 0 <= summary["positive_customer_rate"] <= 1:
        raise ValueError("Stored positive customer rate is invalid")

    for field in (
        "observation_count",
        "selected_customer_count",
        "positive_customer_count",
        "unlabeled_customer_count",
        "positive_customer_rate",
    ):
        if field not in summary or summary[field] != row[field]:
            raise ValueError("Stored results summary does not match run metadata")
    if summary["positive_customer_count"] + summary["unlabeled_customer_count"] != (
        summary["selected_customer_count"]
    ):
        raise ValueError("Stored customer counts do not reconcile")

    for group_name, group in results["profiles"].items():
        if not isinstance(group, dict) or set(group) != set(PROFILE_DIMENSIONS):
            raise ValueError("Stored profile dimensions are invalid")
        for profile in group.values():
            if not isinstance(profile, dict) or set(profile) != {"group_count", "categories"}:
                raise ValueError("Stored profile shape is invalid")
            group_count = profile["group_count"]
            categories = profile["categories"]
            if (
                not isinstance(group_count, int)
                or group_count < 0
                or not isinstance(categories, list)
            ):
                raise ValueError("Stored profile count or categories are invalid")
            category_total = 0
            for category in categories:
                if not isinstance(category, dict) or set(category) != {"label", "count", "share"}:
                    raise ValueError("Stored profile category shape is invalid")
                if not isinstance(category["label"], str) or not category["label"]:
                    raise ValueError("Stored profile category label is invalid")
                if not isinstance(category["count"], int) or category["count"] < 0:
                    raise ValueError("Stored profile category count is invalid")
                if (
                    not isinstance(category["share"], (int, float))
                    or not math.isfinite(category["share"])
                    or not 0 <= category["share"] <= 1
                ):
                    raise ValueError("Stored profile category share is invalid")
                category_total += category["count"]
            if category_total != group_count:
                raise ValueError(
                    f"Stored profile group {group_name} does not reconcile"
                )
    _assert_no_forbidden_keys(results)
    return results


def _public_run_response(row: dict[str, Any]) -> dict[str, Any]:
    try:
        filters = _decode_filters(row)
        response = {
            "analysis_run_id": int(row["analysis_run_id"]),
            "analysis_name": row["analysis_name"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
            "status": row["status"],
            "conversion_definition": row["conversion_definition"],
            "filters": filters,
        }
        if row["status"] == "COMPLETED":
            response.update(_decode_results(row))
        elif row["status"] == "FAILED":
            response["failure_message"] = "The historical analysis could not be completed."
        return response
    except (KeyError, TypeError, ValueError) as exc:
        logger.exception(
            "Saved historical analysis is invalid | analysis_run_id=%s",
            row.get("analysis_run_id"),
            exc_info=exc,
        )
        raise HistoricalSavedRunError(
            "The saved historical analysis could not be read."
        ) from exc


def create_historical_analysis(
    database_path: str | Path,
    value: HistoricalAnalysisFilters | dict[str, Any],
) -> dict[str, Any]:
    normalized = normalize_historical_filters(database_path, value)
    try:
        source_provenance = resolve_current_historical_source_provenance(database_path)
    except HistoricalSourceProvenanceError as exc:
        raise HistoricalDataNotReadyError(
            "Historical customer/campaign import provenance is not ready."
        ) from exc

    repository = HistoricalRepository(database_path)
    filters = normalized.filter_payload()
    created_at = _utc_timestamp()
    analysis_run_id = repository.insert_analysis_run(
        analysis_name=normalized.analysis_name,
        created_at=created_at,
        conversion_definition=normalized.conversion_definition,
        filters_json=_stable_json(filters),
        customer_import_id=source_provenance.customer_import_id,
        customer_source_checksum=source_provenance.customer_source_checksum,
        campaign_sales_import_id=source_provenance.campaign_sales_import_id,
        campaign_sales_source_checksum=source_provenance.campaign_sales_source_checksum,
    )

    try:
        raw = repository.analyze_cohort(filters)
        results = _compose_analysis_result(raw)
        try:
            current_provenance = resolve_current_historical_source_provenance(database_path)
        except HistoricalSourceProvenanceError as exc:
            raise HistoricalDataIntegrityError(
                "Historical source provenance became unavailable during analysis execution."
            ) from exc
        _assert_historical_source_provenance_stable(
            captured=source_provenance,
            current=current_provenance,
        )
        completed_at = _utc_timestamp()
        repository.complete_analysis_run(
            analysis_run_id=analysis_run_id,
            completed_at=completed_at,
            summary=results["summary"],
            results_json=_stable_json(results),
        )
    except Exception as exc:
        internal_diagnostic = traceback.format_exc()
        try:
            repository.fail_analysis_run(
                analysis_run_id=analysis_run_id,
                completed_at=_utc_timestamp(),
                error_message=internal_diagnostic,
            )
        except Exception:
            logger.exception(
                "Unable to persist failed historical analysis | analysis_run_id=%s",
                analysis_run_id,
            )
        if isinstance(exc, HistoricalAnalysisError):
            raise
        logger.exception(
            "Historical analysis execution failed | analysis_run_id=%s",
            analysis_run_id,
            exc_info=exc,
        )
        raise HistoricalAnalysisExecutionError(
            "The historical analysis could not be completed."
        ) from exc

    return get_historical_analysis_run(database_path, analysis_run_id)


def get_historical_analysis_run(
    database_path: str | Path,
    analysis_run_id: int,
) -> dict[str, Any]:
    if analysis_run_id <= 0:
        raise HistoricalAnalysisValidationError(
            "analysis_run_id must be a positive integer."
        )
    row = HistoricalRepository(database_path).fetch_analysis_run(analysis_run_id)
    if row is None:
        raise HistoricalAnalysisNotFoundError("Historical analysis run was not found.")
    return _public_run_response(row)


def list_historical_analysis_runs(
    database_path: str | Path,
    *,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    if not 1 <= limit <= 100 or offset < 0:
        raise HistoricalAnalysisValidationError(
            "Analysis-run pagination is invalid."
        )

    rows = HistoricalRepository(database_path).list_analysis_runs(
        limit=limit,
        offset=offset,
    )
    responses = []
    for row in rows:
        try:
            filters = _decode_filters(row)
        except (KeyError, TypeError, ValueError) as exc:
            logger.exception(
                "Saved historical analysis list item is invalid | analysis_run_id=%s",
                row.get("analysis_run_id"),
                exc_info=exc,
            )
            raise HistoricalSavedRunError(
                "The saved historical analysis could not be read."
            ) from exc
        item = {
            "analysis_run_id": int(row["analysis_run_id"]),
            "analysis_name": row["analysis_name"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
            "status": row["status"],
            "conversion_definition": row["conversion_definition"],
            "filters": filters,
            "observation_count": int(row["observation_count"]),
            "selected_customer_count": int(row["selected_customer_count"]),
            "positive_customer_count": int(row["positive_customer_count"]),
            "unlabeled_customer_count": int(row["unlabeled_customer_count"]),
            "positive_customer_rate": (
                float(row["positive_customer_rate"])
                if row["positive_customer_rate"] is not None
                else None
            ),
        }

        if row["status"] == "COMPLETED":
            try:
                is_current, reason = is_saved_analysis_provenance_current(database_path, row)
            except HistoricalSourceProvenanceError:
                is_current = False
                reason = "Current historical source provenance is unavailable."
            item["is_current"] = bool(is_current)
            item["trainability_status"] = "CURRENT" if is_current else "STALE"
            item["trainability_reason"] = None if is_current else reason
        else:
            item["is_current"] = False
            item["trainability_status"] = "STALE"
            item["trainability_reason"] = "Only completed analyses can be used for training."

        if row["status"] == "FAILED":
            item["failure_message"] = "The historical analysis could not be completed."
        responses.append(item)
    return responses
