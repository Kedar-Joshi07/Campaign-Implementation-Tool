"""Exact, deterministic business guidance for match-strength selection."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from app.config import (
    MATCH_STRENGTH_RECOMMENDATION_MINIMUM_COUNT,
    MATCH_STRENGTH_VERY_STRONG_MINIMUM_MULTIPLIER,
)
from app.database.connection import get_connection
from app.schemas.campaign_targeting import (
    MATCH_STRENGTH_THRESHOLDS,
    BusinessMatchStrength,
)
from app.services.audience_query_service import (
    _categorical_vocabularies_from_snapshot,
)
from app.services.target_group_preview_service import (
    _materialize_business_selection,
    _preview_inputs,
)


MATCH_STRENGTH_RECOMMENDATION_CONTRACT_VERSION = "1"
MATCH_STRENGTH_RECOMMENDATION_RULE_VERSION = "1"
MATCH_STRENGTH_ORDER: tuple[BusinessMatchStrength, ...] = (
    "VERY_STRONG",
    "STRONG",
    "GOOD",
    "BROAD",
)
MATCH_STRENGTH_LABELS: dict[BusinessMatchStrength, str] = {
    "VERY_STRONG": "Very Strong Match — 0.90+",
    "STRONG": "Strong Match — 0.80+",
    "GOOD": "Good Match — 0.70+",
    "BROAD": "Broad Match — 0.60+",
}
MATCH_STRENGTH_DISCLAIMER = (
    "Higher match strength means greater similarity under the current targeting "
    "intelligence; it does not guarantee a purchase or response."
)


def _recommend_strength(
    counts: dict[BusinessMatchStrength, int],
    *,
    practical_minimum_count: int,
    very_strong_minimum_count: int,
) -> tuple[BusinessMatchStrength | None, str, str, str]:
    if counts["VERY_STRONG"] >= very_strong_minimum_count:
        return (
            "VERY_STRONG",
            "VERY_STRONG_USABLE",
            "Very Strong Match is recommended",
            "It is sufficiently large for the higher-selectivity rule while keeping "
            "the target group as selective as possible.",
        )
    if counts["STRONG"] >= practical_minimum_count:
        return (
            "STRONG",
            "STRONG_USABLE",
            "Strong Match is recommended",
            "It provides a practically usable target group while remaining more "
            "selective than Good or Broad Match.",
        )
    if counts["GOOD"] >= practical_minimum_count:
        return (
            "GOOD",
            "GOOD_USABLE",
            "Good Match is recommended",
            "Strong Match is too small for the practical minimum. Good Match reaches "
            "that minimum without silently moving to the broadest option.",
        )
    if counts["BROAD"] >= practical_minimum_count:
        return (
            None,
            "BROAD_ONLY_USABLE",
            "Review the target group size",
            "Only Broad Match reaches the practical minimum. It creates a larger "
            "target group, so no broader standard has been selected automatically.",
        )
    return (
        None,
        "ALL_TOO_SMALL",
        "All match-strength options are too small",
        "None reaches the practical minimum. Review the other targeting preferences "
        "or confirm that a smaller target group is acceptable.",
    )


def _relationship(
    strength: BusinessMatchStrength, current: BusinessMatchStrength
) -> str:
    strength_index = MATCH_STRENGTH_ORDER.index(strength)
    current_index = MATCH_STRENGTH_ORDER.index(current)
    if strength_index < current_index:
        return "NARROWER"
    if strength_index > current_index:
        return "BROADER"
    return "CURRENT"


def get_match_strength_recommendation(
    database_path: str | Path, *, targeting_context_id: int
) -> dict[str, Any]:
    path, _resolution, criteria_response, audience_context = _preview_inputs(
        database_path, targeting_context_id=targeting_context_id
    )
    criteria = criteria_response["criteria"]
    current_strength: BusinessMatchStrength = criteria["match_strength"]
    scoring_run_id = int(audience_context.scoring_row["scoring_run_id"])
    available_count = int(audience_context.scoring_row["scored_person_count"])
    vocabularies = _categorical_vocabularies_from_snapshot(
        audience_context.analytics_snapshot
    )
    counts: dict[BusinessMatchStrength, int] = {}

    with get_connection(path) as connection:
        for strength in MATCH_STRENGTH_ORDER:
            comparison_branches = [
                {
                    **branch,
                    "score_min": MATCH_STRENGTH_THRESHOLDS[strength],
                }
                for branch in criteria_response["audience_filter_branches"]
            ]
            matching_table = _materialize_business_selection(
                connection,
                scoring_run_id=scoring_run_id,
                filter_branches=comparison_branches,
                selection={"mode": "ALL_MATCHING", "target_count": None},
                boundaries=audience_context.boundaries,
                categorical_vocabularies=vocabularies,
                universe_count=available_count,
            )
            counts[strength] = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM {matching_table}"
                ).fetchone()[0]
            )

    very_strong_minimum_count = math.ceil(
        MATCH_STRENGTH_RECOMMENDATION_MINIMUM_COUNT
        * MATCH_STRENGTH_VERY_STRONG_MINIMUM_MULTIPLIER
    )
    recommended, reason, heading, explanation = _recommend_strength(
        counts,
        practical_minimum_count=MATCH_STRENGTH_RECOMMENDATION_MINIMUM_COUNT,
        very_strong_minimum_count=very_strong_minimum_count,
    )
    current_count = counts[current_strength]
    comparisons = [
        {
            "match_strength": strength,
            "label": MATCH_STRENGTH_LABELS[strength],
            "minimum_score": MATCH_STRENGTH_THRESHOLDS[strength],
            "exact_matching_count": counts[strength],
            "percent_of_available_population": (
                counts[strength] * 100.0 / available_count if available_count else 0.0
            ),
            "change_from_current": counts[strength] - current_count,
            "relationship_to_current": _relationship(strength, current_strength),
            "recommended": strength == recommended,
        }
        for strength in MATCH_STRENGTH_ORDER
    ]
    return {
        "match_strength_recommendation_contract_version": (
            MATCH_STRENGTH_RECOMMENDATION_CONTRACT_VERSION
        ),
        "recommendation_rule_version": MATCH_STRENGTH_RECOMMENDATION_RULE_VERSION,
        "targeting_context_id": targeting_context_id,
        "currentness": "UP_TO_DATE",
        "current_match_strength": current_strength,
        "practical_minimum_count": MATCH_STRENGTH_RECOMMENDATION_MINIMUM_COUNT,
        "very_strong_minimum_multiplier": (
            MATCH_STRENGTH_VERY_STRONG_MINIMUM_MULTIPLIER
        ),
        "very_strong_minimum_count": very_strong_minimum_count,
        "recommendation_status": (
            "RECOMMENDED" if recommended is not None else "REVIEW_REQUIRED"
        ),
        "recommendation_reason": reason,
        "recommended_match_strength": recommended,
        "recommendation_heading": heading,
        "recommendation_explanation": (
            f"{explanation} The practical minimum is "
            f"{MATCH_STRENGTH_RECOMMENDATION_MINIMUM_COUNT:,} people."
        ),
        "disclaimer": MATCH_STRENGTH_DISCLAIMER,
        "comparisons": comparisons,
    }


__all__ = (
    "MATCH_STRENGTH_DISCLAIMER",
    "MATCH_STRENGTH_RECOMMENDATION_CONTRACT_VERSION",
    "MATCH_STRENGTH_RECOMMENDATION_RULE_VERSION",
    "get_match_strength_recommendation",
)
