"""Shared calibrated Phase 11 selection contract.

Preflight and materialization must use this module rather than maintaining
parallel SQL predicate implementations.
"""

from __future__ import annotations

from typing import Any, Mapping


CALIBRATED_SELECTION_CONTRACT_VERSION = "2"
PROPENSITY_BUCKETS: dict[str, tuple[float, float, bool]] = {
    "0.90": (0.90, 1.00, True),
    "0.80": (0.80, 0.90, False),
    "0.70": (0.70, 0.80, False),
    "0.60": (0.60, 0.70, False),
    "0.50": (0.50, 0.60, False),
}


def propensity_bucket_bounds(bucket: str) -> tuple[float, float, bool]:
    try:
        return PROPENSITY_BUCKETS[bucket]
    except KeyError as exc:
        raise ValueError("Unsupported propensity bucket.") from exc


def build_branch_predicates(
    branch: Mapping[str, Any],
    *,
    calibrated: bool,
    calibration_artifact_id: int | None = None,
    propensity_bucket: str | None = None,
) -> tuple[list[str], list[Any]]:
    """Build the exact AND predicates for one normalized OR branch."""

    predicates: list[str] = []
    parameters: list[Any] = []
    if calibrated:
        if (
            isinstance(calibration_artifact_id, bool)
            or not isinstance(calibration_artifact_id, int)
            or calibration_artifact_id <= 0
            or propensity_bucket not in PROPENSITY_BUCKETS
        ):
            raise ValueError("Calibrated selection lineage is invalid.")
        predicates.extend(("p.calibration_artifact_id=?", "p.propensity_bucket=?"))
        parameters.extend((calibration_artifact_id, propensity_bucket))

    numeric = {
        "age_min": "d.age >= ?",
        "age_max": "d.age <= ?",
        "individual_yearly_income_min": "d.individual_yearly_income >= ?",
        "individual_yearly_income_max": "d.individual_yearly_income <= ?",
        "family_member_count_min": "d.family_member_count >= ?",
        "family_member_count_max": "d.family_member_count <= ?",
    }
    if calibrated:
        numeric.update(
            {
                "score_min": "p.calibrated_probability >= ?",
                "score_max": "p.calibrated_probability <= ?",
                "top_percentile_max": "p.percentile_bucket <= ?",
            }
        )
    for key, predicate in numeric.items():
        if branch.get(key) is not None:
            predicates.append(predicate)
            parameters.append(branch[key])

    if calibrated and branch.get("deciles"):
        values = list(branch["deciles"])
        predicates.append(f"p.decile IN ({','.join('?' for _ in values)})")
        parameters.extend(values)
    if calibrated and branch.get("rank_bands"):
        values = list(branch["rank_bands"])
        predicates.append(f"p.rank_band IN ({','.join('?' for _ in values)})")
        parameters.extend(values)
    for field in (
        "gender", "state", "marital_status", "education", "employment_status",
        "resident_status", "resident_type", "type_of_employment",
    ):
        values = list(branch.get(field) or [])
        if values:
            predicates.append(
                f"COALESCE(NULLIF(TRIM(CAST(d.{field} AS TEXT)),''),'Unknown/Other') "
                f"IN ({','.join('?' for _ in values)})"
            )
            parameters.extend(values)
    return predicates, parameters


__all__ = (
    "CALIBRATED_SELECTION_CONTRACT_VERSION",
    "PROPENSITY_BUCKETS",
    "build_branch_predicates",
    "propensity_bucket_bounds",
)
