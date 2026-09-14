"""Business view-model adapter over the exact Phase 6 Audience Engine."""

from __future__ import annotations

import base64
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.schemas.campaign_targeting import MATCH_SCORE_BANDS, MATCH_STRENGTH_THRESHOLDS
from app.services.audience_preparation_service import classify_percentile_bucket
from app.services.audience_query_service import (
    PROFILE_GROUP_MATCHING,
    PROFILE_GROUP_SELECTED,
    AudienceQueryConflictError,
    AudienceQueryValidationError,
    _build_filter_predicates_split,
    _categorical_vocabularies_from_snapshot,
    _fetch_profile_from_materialized_tables,
    _materialize_filtered_matching_members,
    _require_prepared_canonical_context,
    normalize_audience_filters,
)
from app.services.campaign_targeting_context_service import (
    CampaignContextServiceError,
    CampaignContextValidationError,
    get_business_targeting_criteria,
    get_campaign_targeting_context,
)
from app.services.phase10_lifecycle_service import touch_phase10_usage_for_context
from app.services.targeting_intelligence_service import resolve_targeting_intelligence


TARGET_GROUP_PREVIEW_CONTRACT_VERSION = "1"


class TargetGroupPreviewNotReadyError(CampaignContextServiceError):
    pass


def _preview_inputs(
    database_path: str | Path, *, targeting_context_id: int
) -> tuple[Path, dict[str, Any], dict[str, Any], Any]:
    path = initialize_database(database_path)
    resolution = resolve_targeting_intelligence(
        path, targeting_context_id=targeting_context_id
    )
    if resolution.status != "READY" or not resolution.can_preview:
        raise TargetGroupPreviewNotReadyError(
            f"{resolution.message}. {resolution.explanation}"
        )
    criteria = get_business_targeting_criteria(
        path, targeting_context_id=targeting_context_id
    )
    source_id = (
        resolution.technical_details.get("scoring_run_id")
        if resolution.technical_details
        else None
    )
    if not isinstance(source_id, int) or source_id <= 0:
        raise TargetGroupPreviewNotReadyError(
            "Targeting is not yet available for this campaign."
        )
    try:
        audience_context = _require_prepared_canonical_context(
            path, scoring_run_id=source_id
        )
    except AudienceQueryConflictError as exc:
        raise TargetGroupPreviewNotReadyError(str(exc)) from exc
    except AudienceQueryValidationError as exc:
        raise CampaignContextValidationError(str(exc)) from exc
    return path, resolution.as_dict(), criteria, audience_context


def _materialize_business_selection(
    connection: Any,
    *,
    scoring_run_id: int,
    filter_branches: list[dict[str, Any]],
    selection: dict[str, Any],
    boundaries: list[dict[str, Any]],
    categorical_vocabularies: dict[str, set[str]],
    universe_count: int,
) -> str:
    connection.execute("DROP TABLE IF EXISTS temp_phase9_union_members")
    for index, branch in enumerate(filter_branches):
        normalized = normalize_audience_filters(branch)
        (
            score_predicates,
            score_parameters,
            demographic_predicates,
            demographic_parameters,
        ) = _build_filter_predicates_split(
            normalized_filters=normalized,
            boundaries=boundaries,
            categorical_vocabularies=categorical_vocabularies,
        )
        _materialize_filtered_matching_members(
            connection,
            scoring_run_id=scoring_run_id,
            score_predicates=score_predicates,
            score_parameters=score_parameters,
            demographic_predicates=demographic_predicates,
            demographic_parameters=demographic_parameters,
        )
        if index == 0:
            connection.execute(
                "CREATE TEMP TABLE temp_phase9_union_members AS "
                "SELECT * FROM temp_matching_members WHERE 0"
            )
            connection.execute(
                "CREATE UNIQUE INDEX temp_idx_phase9_union_person "
                "ON temp_phase9_union_members (person_id)"
            )
        connection.execute(
            "INSERT OR IGNORE INTO temp_phase9_union_members "
            "SELECT * FROM temp_matching_members"
        )

    connection.execute("DROP TABLE IF EXISTS temp_matching_members")
    connection.execute(
        "ALTER TABLE temp_phase9_union_members RENAME TO temp_matching_members"
    )
    connection.execute(
        "CREATE INDEX temp_idx_phase9_matching_rank "
        "ON temp_matching_members (propensity_score DESC, person_id ASC)"
    )

    if selection.get("mode") != "TOP_N":
        return "temp_matching_members"
    target_count = selection.get("target_count")
    if not isinstance(target_count, int) or isinstance(target_count, bool) or target_count <= 0:
        raise CampaignContextValidationError(
            "A positive target count is required for a specific-size target group."
        )
    if target_count > universe_count:
        raise CampaignContextValidationError(
            "The target count cannot exceed the available potential-customer population."
        )
    connection.execute("DROP TABLE IF EXISTS temp_selected_members")
    connection.execute(
        """
        CREATE TEMP TABLE temp_selected_members AS
        SELECT *
        FROM temp_matching_members
        ORDER BY propensity_score DESC, person_id ASC
        LIMIT ?
        """,
        (target_count,),
    )
    connection.execute(
        "CREATE UNIQUE INDEX temp_idx_phase9_selected_person "
        "ON temp_selected_members (person_id)"
    )
    connection.execute(
        "CREATE INDEX temp_idx_phase9_selected_rank "
        "ON temp_selected_members (propensity_score DESC, person_id ASC)"
    )
    return "temp_selected_members"


def _profile_mix(
    distributions: dict[str, list[dict[str, Any]]],
    criteria: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    dimensions = {
        "Age Mix": "age_band",
        "Gender Mix": "gender",
        "Where They Are Located": "state",
        "Income Mix": "individual_yearly_income_band",
    }
    optional = {
        "Marital Status Mix": ("marital_status", "marital_statuses"),
        "Education Mix": ("education", "education_levels"),
        "Employment Status Mix": ("employment_status", "employment_statuses"),
        "Resident Status Mix": ("resident_status", "resident_statuses"),
        "Resident Type Mix": ("resident_type", "resident_types"),
        "Employment Type Mix": ("type_of_employment", "employment_types"),
    }
    for label, (profile_dimension, criteria_field) in optional.items():
        if criteria.get(criteria_field):
            dimensions[label] = profile_dimension
    if (
        criteria.get("family_member_count_min") is not None
        or criteria.get("family_member_count_max") is not None
    ):
        dimensions["Family Size Mix"] = "family_member_count_band"
    return {label: distributions.get(dimension, []) for label, dimension in dimensions.items()}


def _score_distribution(
    connection: Any, *, selected_table: str, selected_count: int
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for band in MATCH_SCORE_BANDS:
        clauses = ["propensity_score >= ?"]
        parameters: list[Any] = [band.minimum]
        if band.maximum is not None:
            clauses.append(
                f"propensity_score {'<=' if band.maximum_inclusive else '<'} ?"
            )
            parameters.append(band.maximum)
        count = int(
            connection.execute(
                f"SELECT COUNT(*) FROM {selected_table} WHERE " + " AND ".join(clauses),
                parameters,
            ).fetchone()[0]
        )
        result.append(
            {
                "category": band.label,
                "count": count,
                "share": count / selected_count if selected_count else 0.0,
            }
        )
    return result


def _why_these_people(
    *,
    context: dict[str, Any],
    criteria: dict[str, Any],
    resolution: dict[str, Any],
    selected_count: int,
) -> str:
    product_count = len(context.get("product_ids", []))
    source_category = (
        "context-compatible"
        if resolution.get("context_specific")
        else "general"
    )
    strength = str(criteria.get("match_strength", "GOOD")).replace("_", " ").title()
    threshold = MATCH_STRENGTH_THRESHOLDS.get(
        criteria.get("match_strength", "GOOD"), 0.70
    )
    strength_meanings = {
        "VERY_STRONG": "the closest similarity to the current targeting intelligence",
        "STRONG": "a high degree of similarity while allowing a larger group",
        "GOOD": "a solid degree of similarity with a practical balance of size",
        "BROAD": "a wider degree of similarity than the stronger settings",
    }
    preference_parts: list[str] = []
    for field, label in (
        ("age_groups", "age"),
        ("genders", "gender"),
        ("states", "location"),
        ("income_groups", "income"),
        ("marital_statuses", "marital status"),
        ("education_levels", "education"),
        ("employment_statuses", "employment status"),
        ("resident_statuses", "resident status"),
        ("resident_types", "resident type"),
        ("employment_types", "employment type"),
    ):
        values = criteria.get(field) or []
        if values:
            display = ", ".join(str(value) for value in values[:3])
            if len(values) > 3:
                display += f" and {len(values) - 3} more"
            preference_parts.append(f"{label}: {display}")
    if criteria.get("family_member_count_min") or criteria.get(
        "family_member_count_max"
    ):
        preference_parts.append("family size range")
    if criteria.get("top_matching_percent"):
        preference_parts.append(
            f"top matching {criteria['top_matching_percent']}%"
        )
    preference_summary = (
        "; ".join(preference_parts)
        if preference_parts
        else "no additional demographic preferences"
    )
    channel = str(context.get("campaign_channel", "campaign")).replace("_", " ").title()
    strength_key = str(criteria.get("match_strength", "GOOD"))
    return (
        f"This current, up-to-date Target Group contains {selected_count:,} "
        f"potential customer{'s' if selected_count != 1 else ''} for one {channel} request "
        f"covering {product_count} selected product{'s' if product_count != 1 else ''}. "
        f"It reflects your targeting preferences ({preference_summary}) and the {strength} "
        f"setting, which means {strength_meanings.get(strength_key, 'the selected degree of similarity')}. "
        f"The group meets the {strength} threshold of {threshold:.2f} or higher under the "
        f"validated, explicitly linked {source_category} targeting intelligence. "
        "Scores express similarity for ranking; they do not establish why a person "
        "will act or predict a purchase outcome."
    )


def _filter_branches_hash(branches: list[dict[str, Any]]) -> str:
    normalized = [normalize_audience_filters(branch).payload for branch in branches]
    canonical = json.dumps(
        normalized,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_target_group_preview(
    database_path: str | Path, *, targeting_context_id: int
) -> dict[str, Any]:
    path, resolution, criteria_response, audience_context = _preview_inputs(
        database_path, targeting_context_id=targeting_context_id
    )
    criteria = criteria_response["criteria"]
    source_id = int(resolution["technical_details"]["scoring_run_id"])
    boundaries = audience_context.boundaries
    vocabularies = _categorical_vocabularies_from_snapshot(
        audience_context.analytics_snapshot
    )
    universe_count = int(audience_context.scoring_row["scored_person_count"])

    with get_connection(path) as connection:
        selected_table = _materialize_business_selection(
            connection,
            scoring_run_id=source_id,
            filter_branches=criteria_response["audience_filter_branches"],
            selection=criteria_response["audience_selection"],
            boundaries=boundaries,
            categorical_vocabularies=vocabularies,
            universe_count=universe_count,
        )
        summaries, distributions = _fetch_profile_from_materialized_tables(
            connection, selected_table_name=selected_table
        )
        matching = summaries[PROFILE_GROUP_MATCHING]
        selected = summaries[PROFILE_GROUP_SELECTED]
        selected_count = int(selected["count"])
        score_distribution = _score_distribution(
            connection,
            selected_table=selected_table,
            selected_count=selected_count,
        )

    context = get_campaign_targeting_context(
        path, targeting_context_id=targeting_context_id
    )["context"]
    response = {
        "target_group_preview_contract_version": TARGET_GROUP_PREVIEW_CONTRACT_VERSION,
        "targeting_context_id": targeting_context_id,
        "currentness": "UP_TO_DATE",
        "currentness_label": "Up to date",
        "kpis": {
            "potential_customers_available": universe_count,
            "matching_your_preferences": int(matching["count"]),
            "selected_for_target_group": selected_count,
            "percent_of_available_people": (
                selected_count * 100.0 / universe_count if universe_count else 0.0
            ),
            "average_targeting_match_score": selected["score_mean"],
            "strongest_match": selected["score_max"],
            "lowest_selected_match": selected["score_min"],
        },
        "targeting_match_score_distribution": score_distribution,
        "demographic_mix": _profile_mix(
            distributions[PROFILE_GROUP_SELECTED], criteria
        ),
        "why_these_people": _why_these_people(
            context=context,
            criteria=criteria,
            resolution=resolution,
            selected_count=selected_count,
        ),
        "technical_details": {
            **resolution["technical_details"],
            "source_status": resolution["status"],
            "source_currentness": "UP_TO_DATE",
            "audience_filter_hash": _filter_branches_hash(
                criteria_response["audience_filter_branches"]
            ),
            "saved_audience_id": None,
            "targeting_intelligence_resolution_contract_version": resolution[
                "targeting_intelligence_resolution_contract_version"
            ],
            "campaign_targeting_context_contract_version": context[
                "campaign_targeting_context_contract_version"
            ],
            "targeting_segment_contract_version": criteria[
                "targeting_segment_contract_version"
            ],
            "business_match_strength_contract_version": criteria[
                "business_match_strength_contract_version"
            ],
            "audience_filter_contract_version": criteria[
                "audience_filter_contract_version"
            ],
            "target_group_preview_contract_version": (
                TARGET_GROUP_PREVIEW_CONTRACT_VERSION
            ),
            "target_group_campaign_contract_version": None,
            "saved_target_group_contract_version": None,
        },
    }
    touch_phase10_usage_for_context(
        path, targeting_context_id=targeting_context_id
    )
    return response


def _encode_cursor(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def _decode_cursor(
    cursor: str,
    *,
    targeting_context_id: int,
    scoring_run_id: int,
    criteria_hash: str,
) -> tuple[float, str]:
    try:
        padding = "=" * ((4 - len(cursor) % 4) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(cursor + padding).decode("utf-8"))
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise CampaignContextValidationError("The target-group cursor is invalid.") from exc
    if not isinstance(decoded, dict) or decoded.get("v") != "1":
        raise CampaignContextValidationError("The target-group cursor is invalid.")
    if (
        decoded.get("targeting_context_id") != targeting_context_id
        or decoded.get("scoring_run_id") != scoring_run_id
        or decoded.get("criteria_hash") != criteria_hash
    ):
        raise CampaignContextValidationError(
            "The target-group cursor does not match the current preview."
        )
    score = decoded.get("last_score")
    person_id = decoded.get("last_person_id")
    if (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(float(score))
        or not 0 <= float(score) <= 1
        or not isinstance(person_id, str)
        or not person_id
    ):
        raise CampaignContextValidationError("The target-group cursor is invalid.")
    return float(score), person_id


def _match_strength(score: float) -> str:
    labels = {
        "VERY_STRONG": "Very Strong Match",
        "STRONG": "Strong Match",
        "GOOD": "Good Match",
        "BROAD": "Broad Match",
    }
    for value, threshold in MATCH_STRENGTH_THRESHOLDS.items():
        if score >= threshold:
            return labels[value]
    return "Below Broad Match"


def _display_value(value: Any) -> str:
    if value is None:
        return "Unknown/Other"
    text = str(value).strip()
    return text or "Unknown/Other"


def search_target_group_preview(
    database_path: str | Path,
    *,
    targeting_context_id: int,
    page_size: int,
    cursor: str | None,
) -> dict[str, Any]:
    path, resolution, criteria_response, audience_context = _preview_inputs(
        database_path, targeting_context_id=targeting_context_id
    )
    source_id = int(resolution["technical_details"]["scoring_run_id"])
    criteria_hash = str(criteria_response["targeting_criteria_sha256"])
    after: tuple[float, str] | None = None
    if cursor is not None:
        after = _decode_cursor(
            cursor,
            targeting_context_id=targeting_context_id,
            scoring_run_id=source_id,
            criteria_hash=criteria_hash,
        )
    with get_connection(path) as connection:
        selected_table = _materialize_business_selection(
            connection,
            scoring_run_id=source_id,
            filter_branches=criteria_response["audience_filter_branches"],
            selection=criteria_response["audience_selection"],
            boundaries=audience_context.boundaries,
            categorical_vocabularies=_categorical_vocabularies_from_snapshot(
                audience_context.analytics_snapshot
            ),
            universe_count=int(audience_context.scoring_row["scored_person_count"]),
        )
        where_sql = ""
        parameters: list[Any] = []
        if after is not None:
            where_sql = (
                "WHERE propensity_score < ? OR "
                "(propensity_score = ? AND person_id > ?)"
            )
            parameters.extend([after[0], after[0], after[1]])
        parameters.append(page_size + 1)
        rows = [
            dict(row)
            for row in connection.execute(
                f"""
                SELECT * FROM {selected_table}
                {where_sql}
                ORDER BY propensity_score DESC, person_id ASC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        ]
    has_more = len(rows) > page_size
    page_rows = rows[:page_size]
    output_rows = []
    for row in page_rows:
        score = float(row["propensity_score"])
        person_id = str(row["person_id"])
        output_rows.append(
            {
                "potential_customer_id": person_id,
                "targeting_match_score": score,
                "top_matching_percent": classify_percentile_bucket(
                    score, person_id, audience_context.boundaries
                ),
                "match_strength": _match_strength(score),
                "age": int(row["age"]),
                "gender": _display_value(row["gender"]),
                "state": _display_value(row["state"]),
                "individual_yearly_income": float(row["individual_yearly_income"]),
                "marital_status": _display_value(row["marital_status"]),
                "education": _display_value(row["education"]),
                "employment_status": _display_value(row["employment_status"]),
                "resident_status": _display_value(row["resident_status"]),
                "resident_type": _display_value(row["resident_type"]),
                "family_member_count": int(row["family_member_count"]),
                "type_of_employment": _display_value(row["type_of_employment"]),
            }
        )
    next_cursor = None
    if has_more and page_rows:
        last = page_rows[-1]
        next_cursor = _encode_cursor(
            {
                "v": "1",
                "targeting_context_id": targeting_context_id,
                "scoring_run_id": source_id,
                "criteria_hash": criteria_hash,
                "last_score": float(last["propensity_score"]),
                "last_person_id": str(last["person_id"]),
            }
        )
    response = {
        "target_group_preview_contract_version": TARGET_GROUP_PREVIEW_CONTRACT_VERSION,
        "targeting_context_id": targeting_context_id,
        "currentness": "UP_TO_DATE",
        "rows": output_rows,
        "next_cursor": next_cursor,
        "has_more": has_more,
    }
    touch_phase10_usage_for_context(
        path, targeting_context_id=targeting_context_id
    )
    return response


__all__ = (
    "TARGET_GROUP_PREVIEW_CONTRACT_VERSION",
    "TargetGroupPreviewNotReadyError",
    "get_target_group_preview",
    "search_target_group_preview",
)
