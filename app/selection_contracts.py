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


@dataclass(frozen=True)
class PropensityBucketDefinition:
    key: PropensityBucket
    minimum: float
    maximum: float
    maximum_inclusive: bool
    display_label: str
    result_label: str
    legacy_match_strength: str


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
    "CALIBRATED_MEMBERSHIP_CONTRACT_VERSION",
    "CALIBRATED_SELECTION_CONTRACT_VERSION",
    "CALIBRATED_SELECTION_SEMANTICS",
    "DEFAULT_PROPENSITY_BUCKET",
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
)
