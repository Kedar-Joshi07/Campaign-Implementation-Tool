"""Dependency-free registry for approved customer-selection contracts.

This module deliberately imports no database, service, router, frontend, or
framework code. Runtime layers consume the same immutable v2 definition so a
future contract can be added without copying probability policy throughout the
application.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


PropensityBucket = Literal["0.90", "0.80", "0.70", "0.60", "0.50"]
LegacyMatchStrength = Literal["VERY_STRONG", "STRONG", "GOOD", "BROAD"]
BuyerSimilarityMinimum = Literal[0.90, 0.80, 0.70, 0.60, 0.50]
BuyerSimilarityTier = Literal[
    "VERY_STRONG", "STRONG", "GOOD", "BROAD", "EXPLORATORY"
]


@dataclass(frozen=True)
class PropensityBucketDefinition:
    key: PropensityBucket
    minimum: float
    maximum: float
    maximum_inclusive: bool
    display_label: str
    result_label: str
    legacy_match_strength: str


@dataclass(frozen=True)
class BuyerSimilarityTierDefinition:
    minimum: BuyerSimilarityMinimum
    maximum: float
    maximum_inclusive: bool
    key: BuyerSimilarityTier
    display_label: str


CALIBRATED_SELECTION_CONTRACT_VERSION = "2"
CALIBRATED_SELECTION_SEMANTICS = "CALIBRATED_PURCHASE_PROBABILITY"
CALIBRATED_MEMBERSHIP_CONTRACT_VERSION = "2"
DEFAULT_PROPENSITY_BUCKET: PropensityBucket = "0.70"
DEMO_QUALIFICATION_MINIMUM = 10_000

PROPENSITY_BUCKET_DEFINITIONS: tuple[PropensityBucketDefinition, ...] = (
    PropensityBucketDefinition(
        "0.90", 0.90, 1.00, True,
        "90% to 100% purchase propensity", "90% to 100%", "VERY_STRONG",
    ),
    PropensityBucketDefinition(
        "0.80", 0.80, 0.90, False,
        "80% to under 90% purchase propensity", "80% to <90%", "STRONG",
    ),
    PropensityBucketDefinition(
        "0.70", 0.70, 0.80, False,
        "70% to under 80% purchase propensity", "70% to <80%", "GOOD",
    ),
    PropensityBucketDefinition(
        "0.60", 0.60, 0.70, False,
        "60% to under 70% purchase propensity", "60% to <70%", "BROAD",
    ),
    PropensityBucketDefinition(
        "0.50", 0.50, 0.60, False,
        "50% to under 60% purchase propensity", "50% to <60%", "BROAD",
    ),
)
PROPENSITY_BUCKET_REGISTRY = {
    definition.key: definition for definition in PROPENSITY_BUCKET_DEFINITIONS
}
PROPENSITY_BUCKET_KEYS = tuple(PROPENSITY_BUCKET_REGISTRY)
PROPENSITY_BUCKET_BY_LEGACY_MATCH_STRENGTH: dict[
    LegacyMatchStrength, PropensityBucket
] = {
    "VERY_STRONG": "0.90",
    "STRONG": "0.80",
    "GOOD": "0.70",
    "BROAD": "0.60",
}
# Bucket-to-legacy projection is intentionally many-to-one: both 0.60 and
# 0.50 project to BROAD. Legacy-to-bucket translation is a separately frozen
# compatibility contract and must never be derived by dictionary inversion.
PROPENSITY_BUCKETS = {
    key: (
        definition.minimum,
        definition.maximum,
        definition.maximum_inclusive,
    )
    for key, definition in PROPENSITY_BUCKET_REGISTRY.items()
}


# V3 is intentionally independent of the probability registry above.  These
# names are mode-specific so callers cannot accidentally treat similarity as a
# calibrated purchase probability.
BUYER_SIMILARITY_SELECTION_CONTRACT_VERSION = "3"
BUYER_SIMILARITY_SCORE_SEMANTICS = "PRODUCT_BUYER_SIMILARITY"
BUYER_SIMILARITY_SCORE_METHOD_VERSION = "BUYER_PROFILE_DISTANCE_V1"
BUYER_SIMILARITY_MEMBERSHIP_CONTRACT_VERSION = "3"
BUYER_SIMILARITY_THRESHOLD_PREDICATE = "GREATER_THAN_OR_EQUAL"
BUYER_SIMILARITY_PRODUCT_MATCH_POLICY = "ANY_SELECTED_PRODUCT_MAX_V1"
DEFAULT_BUYER_SIMILARITY_MINIMUM: BuyerSimilarityMinimum = 0.70
BUYER_SIMILARITY_MINIMUMS: tuple[BuyerSimilarityMinimum, ...] = (
    0.90, 0.80, 0.70, 0.60, 0.50,
)
BUYER_SIMILARITY_TIER_DEFINITIONS: tuple[BuyerSimilarityTierDefinition, ...] = (
    BuyerSimilarityTierDefinition(0.90, 1.00, True, "VERY_STRONG", "Very Strong"),
    BuyerSimilarityTierDefinition(0.80, 0.90, False, "STRONG", "Strong"),
    BuyerSimilarityTierDefinition(0.70, 0.80, False, "GOOD", "Good"),
    BuyerSimilarityTierDefinition(0.60, 0.70, False, "BROAD", "Broad"),
    BuyerSimilarityTierDefinition(0.50, 0.60, False, "EXPLORATORY", "Exploratory"),
)


def buyer_similarity_meets_minimum(score: float, minimum: float) -> bool:
    """Apply the frozen v3 inclusive threshold without numeric coercion."""

    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ValueError("Buyer similarity score must be numeric.")
    if isinstance(minimum, bool) or minimum not in BUYER_SIMILARITY_MINIMUMS:
        raise ValueError("Unsupported buyer similarity minimum.")
    numeric_score = float(score)
    if not 0.0 <= numeric_score <= 1.0:
        raise ValueError("Buyer similarity score must be between zero and one.")
    return numeric_score >= float(minimum)


def buyer_similarity_tier(score: float) -> BuyerSimilarityTier:
    """Return the frozen v3 business tier for a selectable score."""

    for definition in BUYER_SIMILARITY_TIER_DEFINITIONS:
        if (
            score >= definition.minimum
            and (score <= definition.maximum if definition.maximum_inclusive else score < definition.maximum)
        ):
            return definition.key
    raise ValueError("Buyer similarity score is outside the selectable range.")


def propensity_bucket_definition(bucket: str) -> PropensityBucketDefinition:
    try:
        return PROPENSITY_BUCKET_REGISTRY[bucket]  # type: ignore[index]
    except KeyError as exc:
        raise ValueError("Unsupported propensity bucket.") from exc


def propensity_bucket_bounds(bucket: str) -> tuple[float, float, bool]:
    definition = propensity_bucket_definition(bucket)
    return (
        definition.minimum,
        definition.maximum,
        definition.maximum_inclusive,
    )


__all__ = (
    "BUYER_SIMILARITY_MEMBERSHIP_CONTRACT_VERSION",
    "BUYER_SIMILARITY_MINIMUMS",
    "BUYER_SIMILARITY_PRODUCT_MATCH_POLICY",
    "BUYER_SIMILARITY_SCORE_METHOD_VERSION",
    "BUYER_SIMILARITY_SCORE_SEMANTICS",
    "BUYER_SIMILARITY_SELECTION_CONTRACT_VERSION",
    "BUYER_SIMILARITY_THRESHOLD_PREDICATE",
    "BUYER_SIMILARITY_TIER_DEFINITIONS",
    "BuyerSimilarityMinimum",
    "BuyerSimilarityTier",
    "BuyerSimilarityTierDefinition",
    "CALIBRATED_MEMBERSHIP_CONTRACT_VERSION",
    "CALIBRATED_SELECTION_CONTRACT_VERSION",
    "CALIBRATED_SELECTION_SEMANTICS",
    "DEFAULT_PROPENSITY_BUCKET",
    "DEFAULT_BUYER_SIMILARITY_MINIMUM",
    "DEMO_QUALIFICATION_MINIMUM",
    "LegacyMatchStrength",
    "PROPENSITY_BUCKET_DEFINITIONS",
    "PROPENSITY_BUCKET_BY_LEGACY_MATCH_STRENGTH",
    "PROPENSITY_BUCKET_KEYS",
    "PROPENSITY_BUCKET_REGISTRY",
    "PROPENSITY_BUCKETS",
    "PropensityBucket",
    "PropensityBucketDefinition",
    "propensity_bucket_bounds",
    "propensity_bucket_definition",
    "buyer_similarity_meets_minimum",
    "buyer_similarity_tier",
)
