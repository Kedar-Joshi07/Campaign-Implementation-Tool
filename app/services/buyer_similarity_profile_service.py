"""Deterministic descriptive buyer profiles for selection contract v3.

``BUYER_PROFILE_DISTANCE_V1`` is deliberately independent from the purchase
probability model.  It learns bounded mixed-type prototypes from historical
FIT buyers only and produces a transparent similarity index.  Artifacts are
canonical JSON; executable/pickle payloads are never accepted.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from app.ml.feature_contract import (
    CATEGORICAL_FEATURES,
    FEATURE_CONTRACT_SHA256,
    NUMERIC_FEATURES,
    ORDERED_FEATURES,
    UNKNOWN_CATEGORY,
    validate_and_normalize_feature_frame,
)
from app.services.buyer_similarity_cohort_service import (
    BUYER_SPLIT_SEED,
    BuyerCohortBuild,
)
from app.services.buyer_similarity_split_service import SUPPORT_AWARE_OBJECTIVE_VERSION, SUPPORT_AWARE_SPLIT_VERSION


SCORE_METHOD_VERSION = "BUYER_PROFILE_DISTANCE_V1"
PREPROCESSOR_CONTRACT_VERSION = "BUYER_PROFILE_Q05_Q95_V1"
SERIALIZATION_CONTRACT_VERSION = "1"
PROFILE_IMPLEMENTATION_VERSION = "1"
CANDIDATE_K_VALUES = (1, 2, 4, 8, 16)
MAX_ITERATIONS = 50
MINIMUM_FEATURE_COVERAGE = 0.80
FEATURE_WEIGHT = 1.0 / len(ORDERED_FEATURES)
DEFAULT_ASSIGNMENT_CHUNK_SIZE = 2_048
ARTIFACT_ROOT = Path("artifacts/buyer_similarity_profiles")
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024

_NUMERIC_FALLBACKS = {
    "age": 1.0,
    "individual_yearly_income": 1.0,
    "family_member_count": 1.0,
}
PREPROCESSOR_CONTRACT_SHA256 = hashlib.sha256(
    json.dumps(
        {
            "version": PREPROCESSOR_CONTRACT_VERSION,
            "ordered_features": list(ORDERED_FEATURES),
            "numeric_scale": "FIT_Q95_MINUS_Q05_LINEAR",
            "numeric_distance": "MIN_1_ABS_X_MINUS_C_DIVIDED_BY_RANGE",
            "zero_range_fallbacks": _NUMERIC_FALLBACKS,
            "categorical_distance": "EXACT_CANONICAL_MATCH_0_ELSE_1",
            "missing_unknown_penalty": 1.0,
            "feature_weight": FEATURE_WEIGHT,
            "minimum_feature_coverage": MINIMUM_FEATURE_COVERAGE,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()
_STORAGE_URI = re.compile(
    r"artifacts/buyer_similarity_profiles/profile_[0-9a-f]{64}/profile\.json"
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


class BuyerSimilarityProfileError(RuntimeError):
    """Base class for bounded profile failures."""


class BuyerSimilarityFitError(BuyerSimilarityProfileError):
    """Raised when a supported deterministic profile cannot be fitted."""


class BuyerSimilarityArtifactError(BuyerSimilarityProfileError):
    """Raised when a profile artifact is unsafe, corrupt, stale, or incompatible."""


@dataclass(frozen=True)
class NumericScale:
    q05: float
    q95: float
    distance_range: float
    used_zero_range_fallback: bool


@dataclass(frozen=True)
class FeatureDistance:
    feature: str
    distance: float
    weighted_contribution: float
    input_known: bool
    prototype_known: bool


@dataclass(frozen=True)
class BuyerSimilarityScore:
    is_valid: bool
    buyer_similarity_score: float | None
    feature_coverage: float
    prototype_key: str | None
    prototype_distance: float | None
    invalid_reason_code: str | None
    feature_distances: tuple[FeatureDistance, ...]


@dataclass(frozen=True)
class StoredProfileArtifact:
    storage_uri: str
    artifact_sha256: str
    profile_payload_sha256: str


def describe_profile_holdout(
    cohort: BuyerCohortBuild,
    artifact: Mapping[str, Any],
) -> dict[str, Any]:
    """Describe customer-disjoint holdout resemblance without predictive claims.

    This is deliberately post-fit.  Nothing returned here participates in scale,
    prototype, or k selection.
    """

    profile = _validate_artifact_payload(dict(artifact))
    product_rows = cohort.frame.loc[
        (cohort.frame["product_id"] == profile["product_id"])
        & (cohort.frame["split"] == "HOLDOUT")
    ]
    scores: list[float] = []
    invalid_reasons: dict[str, int] = {}
    exact_matches = 0
    for row in product_rows.loc[:, ORDERED_FEATURES].to_dict(orient="records"):
        result = score_buyer_similarity_record(row, profile)
        if result.is_valid:
            assert result.buyer_similarity_score is not None
            scores.append(result.buyer_similarity_score)
            exact_matches += int(result.buyer_similarity_score == 1.0)
        else:
            reason = str(result.invalid_reason_code)
            invalid_reasons[reason] = invalid_reasons.get(reason, 0) + 1
    return {
        "validation_kind": "CUSTOMER_DISJOINT_DESCRIPTIVE_HOLDOUT",
        "predictive_validation": False,
        "holdout_count": len(product_rows),
        "valid_score_count": len(scores),
        "invalid_score_count": len(product_rows) - len(scores),
        "invalid_reason_counts": invalid_reasons,
        "exact_prototype_match_count": exact_matches,
        "score_min": None if not scores else min(scores),
        "score_max": None if not scores else max(scores),
        "score_mean": None if not scores else float(sum(scores) / len(scores)),
    }


def _is_missing_numeric(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _known_category(value: Any, vocabulary: set[str] | None = None) -> bool:
    if not isinstance(value, str) or value == UNKNOWN_CATEGORY or not value.strip():
        return False
    return vocabulary is None or value in vocabulary


def _feature_distance(
    feature: str,
    input_value: Any,
    prototype_value: Any,
    *,
    numeric_scales: Mapping[str, Mapping[str, Any]],
    categorical_vocabulary: Mapping[str, Sequence[str]],
) -> tuple[float, bool, bool]:
    """Return the one V1 feature term and knownness used everywhere."""

    if feature in NUMERIC_FEATURES:
        input_known = not _is_missing_numeric(input_value)
        prototype_known = not _is_missing_numeric(prototype_value)
        if not input_known or not prototype_known:
            return 1.0, input_known, prototype_known
        scale = float(numeric_scales[feature]["distance_range"])
        if not math.isfinite(scale) or scale <= 0:
            raise BuyerSimilarityArtifactError("A numeric distance scale is invalid.")
        distance = min(
            1.0,
            abs(float(input_value) - float(prototype_value)) / scale,
        )
        return float(distance), True, True

    vocabulary = set(categorical_vocabulary.get(feature, ()))
    input_known = _known_category(input_value, vocabulary)
    prototype_known = _known_category(prototype_value, vocabulary)
    if not input_known or not prototype_known:
        return 1.0, input_known, prototype_known
    return (0.0 if input_value == prototype_value else 1.0), True, True


def _distance_terms(
    record: Mapping[str, Any],
    prototype_values: Mapping[str, Any],
    *,
    numeric_scales: Mapping[str, Mapping[str, Any]],
    categorical_vocabulary: Mapping[str, Sequence[str]],
) -> tuple[float, float, tuple[FeatureDistance, ...]]:
    terms: list[FeatureDistance] = []
    coverage = 0.0
    total = 0.0
    for feature in ORDERED_FEATURES:
        distance, input_known, prototype_known = _feature_distance(
            feature,
            record.get(feature),
            prototype_values.get(feature),
            numeric_scales=numeric_scales,
            categorical_vocabulary=categorical_vocabulary,
        )
        contribution = FEATURE_WEIGHT * distance
        total += contribution
        if input_known:
            coverage += FEATURE_WEIGHT
        terms.append(
            FeatureDistance(
                feature=feature,
                distance=distance,
                weighted_contribution=contribution,
                input_known=input_known,
                prototype_known=prototype_known,
            )
        )
    return min(1.0, max(0.0, total)), min(1.0, coverage), tuple(terms)


def _validate_artifact_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise BuyerSimilarityArtifactError("The profile artifact root is invalid.")
    required = {
        "serialization_contract_version",
        "score_method_version",
        "preprocessor_contract_version",
        "preprocessor_contract_sha256",
        "profile_implementation_version",
        "feature_contract_sha256",
        "immutable_identity_sha256",
        "product_id",
        "lineage",
        "training_parameters",
        "numeric_scales",
        "categorical_vocabulary",
        "candidate_diagnostics",
        "realized_k",
        "fit_support",
        "holdout_support",
        "prototypes",
        "library_versions",
    }
    if set(payload) != required:
        raise BuyerSimilarityArtifactError("The profile artifact is partial or incompatible.")
    if payload["serialization_contract_version"] != SERIALIZATION_CONTRACT_VERSION:
        raise BuyerSimilarityArtifactError("The serialization contract is incompatible.")
    if payload["score_method_version"] != SCORE_METHOD_VERSION:
        raise BuyerSimilarityArtifactError("The score method is incompatible.")
    if payload["preprocessor_contract_version"] != PREPROCESSOR_CONTRACT_VERSION:
        raise BuyerSimilarityArtifactError("The preprocessor contract is incompatible.")
    if payload["preprocessor_contract_sha256"] != PREPROCESSOR_CONTRACT_SHA256:
        raise BuyerSimilarityArtifactError("The preprocessor checksum is incompatible.")
    if payload["feature_contract_sha256"] != FEATURE_CONTRACT_SHA256:
        raise BuyerSimilarityArtifactError("The feature contract is incompatible.")
    identity = payload["immutable_identity_sha256"]
    if not isinstance(identity, str) or re.fullmatch(r"[0-9a-f]{64}", identity) is None:
        raise BuyerSimilarityArtifactError("The immutable profile identity is invalid.")
    if not isinstance(payload["product_id"], str) or not payload["product_id"]:
        raise BuyerSimilarityArtifactError("The artifact product identity is invalid.")
    lineage = payload["lineage"]
    lineage_fields = {
        "cohort_contract_version",
        "historical_context_sha256",
        "resolved_window_start",
        "resolved_window_end",
        "buyer_conversion_definition",
        "customer_import_id",
        "customer_source_checksum",
        "campaign_sales_import_id",
        "campaign_sales_source_checksum",
        "product_catalog_sha256",
        "fit_identity_sha256",
        "holdout_identity_sha256",
        "split_strategy_version",
        "split_seed",
    }
    if isinstance(lineage, dict) and lineage.get("split_strategy_version") == SUPPORT_AWARE_SPLIT_VERSION:
        lineage_fields.update({"split_objective_version", "partition_manifest_sha256"})
    if not isinstance(lineage, dict) or set(lineage) != lineage_fields:
        raise BuyerSimilarityArtifactError("The source lineage is incomplete.")
    for field in (
        "historical_context_sha256",
        "customer_source_checksum",
        "campaign_sales_source_checksum",
        "product_catalog_sha256",
        "fit_identity_sha256",
        "holdout_identity_sha256",
        *(["partition_manifest_sha256"]
          if lineage["split_strategy_version"] == SUPPORT_AWARE_SPLIT_VERSION else []),
    ):
        if not isinstance(lineage[field], str) or re.fullmatch(
            r"[0-9a-f]{64}", lineage[field]
        ) is None:
            raise BuyerSimilarityArtifactError("A source lineage checksum is invalid.")
    if (lineage["split_strategy_version"] == SUPPORT_AWARE_SPLIT_VERSION
        and lineage["split_objective_version"] != SUPPORT_AWARE_OBJECTIVE_VERSION):
        raise BuyerSimilarityArtifactError("The partition objective lineage is incompatible.")
    scales = payload["numeric_scales"]
    if not isinstance(scales, dict) or set(scales) != set(NUMERIC_FEATURES):
        raise BuyerSimilarityArtifactError("The numeric scales are incomplete.")
    for scale in scales.values():
        if not isinstance(scale, dict) or set(scale) != {
            "q05", "q95", "distance_range", "used_zero_range_fallback"
        }:
            raise BuyerSimilarityArtifactError("A numeric scale is incompatible.")
        try:
            q05 = float(scale["q05"])
            q95 = float(scale["q95"])
            distance_range = float(scale["distance_range"])
        except (TypeError, ValueError) as exc:
            raise BuyerSimilarityArtifactError("A numeric scale is invalid.") from exc
        if (
            not all(math.isfinite(value) for value in (q05, q95, distance_range))
            or q95 < q05
            or distance_range <= 0
            or not isinstance(scale["used_zero_range_fallback"], bool)
        ):
            raise BuyerSimilarityArtifactError("A numeric scale is invalid.")
    vocabulary = payload["categorical_vocabulary"]
    if not isinstance(vocabulary, dict) or set(vocabulary) != set(CATEGORICAL_FEATURES):
        raise BuyerSimilarityArtifactError("The categorical vocabulary is incomplete.")
    for values in vocabulary.values():
        if (
            not isinstance(values, list)
            or any(not isinstance(value, str) or not _known_category(value) for value in values)
            or values != sorted(set(values))
        ):
            raise BuyerSimilarityArtifactError("A categorical vocabulary is invalid.")
    parameters = payload["training_parameters"]
    if not isinstance(parameters, dict) or parameters.get("candidate_k_values") != list(
        CANDIDATE_K_VALUES
    ):
        raise BuyerSimilarityArtifactError("The training parameters are incompatible.")
    if (
        parameters.get("random_seed") != BUYER_SPLIT_SEED
        or parameters.get("maximum_iterations") != MAX_ITERATIONS
        or parameters.get("feature_weight") != FEATURE_WEIGHT
        or parameters.get("minimum_feature_coverage") != MINIMUM_FEATURE_COVERAGE
    ):
        raise BuyerSimilarityArtifactError("The training parameters are incompatible.")
    diagnostics = payload["candidate_diagnostics"]
    if (
        not isinstance(diagnostics, list)
        or any(not isinstance(item, dict) for item in diagnostics)
        or [item.get("k") for item in diagnostics] != list(CANDIDATE_K_VALUES)
    ):
        raise BuyerSimilarityArtifactError("Candidate diagnostics are incompatible.")
    prototypes = payload["prototypes"]
    if not isinstance(prototypes, list) or not prototypes:
        raise BuyerSimilarityArtifactError("The profile artifact has no prototypes.")
    if int(payload["realized_k"]) != len(prototypes):
        raise BuyerSimilarityArtifactError("The realized prototype count is inconsistent.")
    expected_keys = [f"P{index + 1:03d}" for index in range(len(prototypes))]
    support = 0
    for index, prototype in enumerate(prototypes):
        if not isinstance(prototype, dict) or set(prototype) != {
            "prototype_key", "tie_order", "support", "values"
        }:
            raise BuyerSimilarityArtifactError("A prototype record is incompatible.")
        if prototype["prototype_key"] != expected_keys[index] or int(
            prototype["tie_order"]
        ) != index:
            raise BuyerSimilarityArtifactError("Prototype order is not canonical.")
        if not isinstance(prototype["values"], dict) or set(
            prototype["values"]
        ) != set(ORDERED_FEATURES):
            raise BuyerSimilarityArtifactError("Prototype features are incomplete.")
        if any(key in prototype for key in ("customer_id", "person_id", "email", "phone")):
            raise BuyerSimilarityArtifactError("Prototype payload contains a forbidden identity.")
        prototype_support = int(prototype["support"])
        if prototype_support <= 0:
            raise BuyerSimilarityArtifactError("Prototype support is invalid.")
        support += prototype_support
        for feature in NUMERIC_FEATURES:
            value = prototype["values"][feature]
            if value is not None and (
                not isinstance(value, (int, float)) or not math.isfinite(float(value))
            ):
                raise BuyerSimilarityArtifactError("A numeric prototype value is invalid.")
        for feature in CATEGORICAL_FEATURES:
            value = prototype["values"][feature]
            if value is not None and value not in vocabulary[feature]:
                raise BuyerSimilarityArtifactError("A categorical prototype value is invalid.")
    if support != int(payload["fit_support"]):
        raise BuyerSimilarityArtifactError("Prototype support does not equal fit support.")
    expected_identity = _profile_identity(payload, include_existing=False)
    if payload["immutable_identity_sha256"] != expected_identity:
        raise BuyerSimilarityArtifactError("The immutable profile identity is invalid.")
    return payload


def _score_normalized_record(
    normalized: Mapping[str, Any],
    profile: Mapping[str, Any],
) -> BuyerSimilarityScore:
    best: tuple[float, int, tuple[FeatureDistance, ...], float] | None = None
    for prototype in profile["prototypes"]:
        distance, coverage, terms = _distance_terms(
            normalized,
            prototype["values"],
            numeric_scales=profile["numeric_scales"],
            categorical_vocabulary=profile["categorical_vocabulary"],
        )
        candidate = (distance, int(prototype["tie_order"]), terms, coverage)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    assert best is not None
    distance, tie_order, terms, coverage = best
    if coverage + 1e-12 < MINIMUM_FEATURE_COVERAGE:
        return BuyerSimilarityScore(
            is_valid=False,
            buyer_similarity_score=None,
            feature_coverage=coverage,
            prototype_key=None,
            prototype_distance=None,
            invalid_reason_code="INSUFFICIENT_FEATURE_COVERAGE",
            feature_distances=terms,
        )
    score = min(1.0, max(0.0, 1.0 - distance))
    return BuyerSimilarityScore(
        is_valid=True,
        buyer_similarity_score=score,
        feature_coverage=coverage,
        prototype_key=profile["prototypes"][tie_order]["prototype_key"],
        prototype_distance=distance,
        invalid_reason_code=None,
        feature_distances=terms,
    )


def score_buyer_similarity_record(
    record: Mapping[str, Any],
    artifact: Mapping[str, Any],
) -> BuyerSimilarityScore:
    """Score one record and expose contributions from the same distance call."""

    profile = _validate_artifact_payload(dict(artifact))
    if set(record) != set(ORDERED_FEATURES):
        raise BuyerSimilarityProfileError(
            "A scoring record must contain exactly the 11 shared features."
        )
    normalized_frame = validate_and_normalize_feature_frame(
        pd.DataFrame([{feature: record[feature] for feature in ORDERED_FEATURES}])
        .loc[:, ORDERED_FEATURES]
    )
    return _score_normalized_record(normalized_frame.iloc[0].to_dict(), profile)


def score_buyer_similarity_frame(
    frame: pd.DataFrame,
    artifact: Mapping[str, Any],
    *,
    chunk_size: int = DEFAULT_ASSIGNMENT_CHUNK_SIZE,
) -> tuple[BuyerSimilarityScore, ...]:
    """Score a frame in bounded chunks through the one-record scorer."""

    if not isinstance(frame, pd.DataFrame) or tuple(frame.columns) != ORDERED_FEATURES:
        raise BuyerSimilarityProfileError(
            "A scoring frame must exactly match the 11 shared feature columns."
        )
    if chunk_size <= 0:
        raise BuyerSimilarityProfileError("Scoring chunk size must be positive.")
    profile = _validate_artifact_payload(dict(artifact))
    results: list[BuyerSimilarityScore] = []
    for start in range(0, len(frame), chunk_size):
        stop = min(len(frame), start + chunk_size)
        normalized = validate_and_normalize_feature_frame(frame.iloc[start:stop])
        for record in normalized.to_dict(orient="records"):
            results.append(_score_normalized_record(record, profile))
    return tuple(results)


def _fit_scales(fit: pd.DataFrame) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for feature in NUMERIC_FEATURES:
        observed = fit[feature].dropna().astype(float)
        if observed.empty:
            q05 = q95 = 0.0
            fitted_range = 0.0
        else:
            q05 = float(observed.quantile(0.05, interpolation="linear"))
            q95 = float(observed.quantile(0.95, interpolation="linear"))
            fitted_range = q95 - q05
        fallback = fitted_range <= 0.0
        distance_range = _NUMERIC_FALLBACKS[feature] if fallback else fitted_range
        result[feature] = asdict(
            NumericScale(
                q05=q05,
                q95=q95,
                distance_range=float(distance_range),
                used_zero_range_fallback=fallback,
            )
        )
    return result


def _fit_vocabulary(fit: pd.DataFrame) -> dict[str, list[str]]:
    return {
        feature: sorted(
            {
                str(value)
                for value in fit[feature]
                if _known_category(value)
            }
        )
        for feature in CATEGORICAL_FEATURES
    }


def _row_distance(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    numeric_scales: Mapping[str, Mapping[str, Any]],
    categorical_vocabulary: Mapping[str, Sequence[str]],
) -> float:
    return _distance_terms(
        left,
        right,
        numeric_scales=numeric_scales,
        categorical_vocabulary=categorical_vocabulary,
    )[0]


def _initialize_prototypes(
    fit: pd.DataFrame,
    customer_ids: Sequence[str],
    k: int,
    *,
    numeric_scales: Mapping[str, Mapping[str, Any]],
    categorical_vocabulary: Mapping[str, Sequence[str]],
) -> list[dict[str, Any]]:
    if k > len(fit):
        return []
    rng = np.random.default_rng(BUYER_SPLIT_SEED)
    first = int(rng.integers(0, len(fit)))
    selected = [first]
    selected_set = {first}
    records = fit.to_dict(orient="records")
    while len(selected) < k:
        best_index: int | None = None
        best_distance = -1.0
        for row_index, row in enumerate(records):
            if row_index in selected_set:
                continue
            nearest = min(
                _row_distance(
                    row,
                    records[center],
                    numeric_scales=numeric_scales,
                    categorical_vocabulary=categorical_vocabulary,
                )
                for center in selected
            )
            if (
                nearest > best_distance + 1e-15
                or (
                    abs(nearest - best_distance) <= 1e-15
                    and best_index is not None
                    and customer_ids[row_index] < customer_ids[best_index]
                )
            ):
                best_index = row_index
                best_distance = nearest
        if best_index is None:
            return []
        selected.append(best_index)
        selected_set.add(best_index)
    return [dict(records[index]) for index in selected]


def _assign(
    fit: pd.DataFrame,
    prototypes: Sequence[Mapping[str, Any]],
    *,
    numeric_scales: Mapping[str, Mapping[str, Any]],
    categorical_vocabulary: Mapping[str, Sequence[str]],
    chunk_size: int,
) -> np.ndarray:
    if chunk_size <= 0:
        raise BuyerSimilarityFitError("Assignment chunk size must be positive.")
    assignments = np.empty(len(fit), dtype=np.int32)
    for start in range(0, len(fit), chunk_size):
        stop = min(len(fit), start + chunk_size)
        records = fit.iloc[start:stop].to_dict(orient="records")
        for offset, record in enumerate(records):
            distances = [
                _row_distance(
                    record,
                    prototype,
                    numeric_scales=numeric_scales,
                    categorical_vocabulary=categorical_vocabulary,
                )
                for prototype in prototypes
            ]
            assignments[start + offset] = min(
                range(len(distances)), key=lambda index: (distances[index], index)
            )
    return assignments


def _updated_prototypes(
    fit: pd.DataFrame,
    assignments: np.ndarray,
    k: int,
) -> list[dict[str, Any]]:
    prototypes: list[dict[str, Any]] = []
    for cluster in range(k):
        members = fit.loc[assignments == cluster]
        values: dict[str, Any] = {}
        for feature in NUMERIC_FEATURES:
            observed = members[feature].dropna().astype(float)
            values[feature] = None if observed.empty else float(observed.median())
        for feature in CATEGORICAL_FEATURES:
            observed = [
                str(value) for value in members[feature] if _known_category(value)
            ]
            if not observed:
                values[feature] = None
            else:
                counts: dict[str, int] = {}
                for value in observed:
                    counts[value] = counts.get(value, 0) + 1
                maximum = max(counts.values())
                values[feature] = min(
                    value for value, count in counts.items() if count == maximum
                )
        prototypes.append(values)
    return prototypes


def _fit_candidate(
    fit: pd.DataFrame,
    customer_ids: Sequence[str],
    k: int,
    *,
    numeric_scales: Mapping[str, Mapping[str, Any]],
    categorical_vocabulary: Mapping[str, Sequence[str]],
    chunk_size: int,
    minimum_support: int,
) -> tuple[dict[str, Any], list[dict[str, Any]] | None, np.ndarray | None]:
    prototypes = _initialize_prototypes(
        fit,
        customer_ids,
        k,
        numeric_scales=numeric_scales,
        categorical_vocabulary=categorical_vocabulary,
    )
    if not prototypes:
        return ({"k": k, "valid": False, "reason": "K_EXCEEDS_FIT_SUPPORT"}, None, None)
    previous: np.ndarray | None = None
    converged = False
    iterations = 0
    assignments: np.ndarray | None = None
    for iteration in range(1, MAX_ITERATIONS + 1):
        assignments = _assign(
            fit,
            prototypes,
            numeric_scales=numeric_scales,
            categorical_vocabulary=categorical_vocabulary,
            chunk_size=chunk_size,
        )
        iterations = iteration
        if previous is not None and np.array_equal(assignments, previous):
            converged = True
            break
        supports = np.bincount(assignments, minlength=k)
        if np.any(supports == 0):
            return (
                {
                    "k": k,
                    "valid": False,
                    "reason": "EMPTY_CLUSTER",
                    "iterations": iterations,
                    "converged": False,
                    "supports": [int(value) for value in supports],
                },
                None,
                None,
            )
        previous = assignments.copy()
        prototypes = _updated_prototypes(fit, assignments, k)
    assert assignments is not None
    supports = np.bincount(assignments, minlength=k)
    reason = "ELIGIBLE"
    valid = converged
    if not converged:
        reason = "NONCONVERGENCE"
    elif np.any(supports < minimum_support):
        valid = False
        reason = "UNDERSUPPORTED_CLUSTER"
    diagnostic = {
        "k": k,
        "valid": valid,
        "reason": reason,
        "iterations": iterations,
        "converged": converged,
        "supports": [int(value) for value in supports],
    }
    return diagnostic, (prototypes if valid else None), (assignments if valid else None)


def _profile_identity(payload: Mapping[str, Any], *, include_existing: bool) -> str:
    excluded = {"immutable_identity_sha256", "candidate_diagnostics", "prototypes", "library_versions"}
    identity = {key: value for key, value in payload.items() if key not in excluded}
    if include_existing:
        identity["immutable_identity_sha256"] = payload.get("immutable_identity_sha256")
    return _sha256_json(identity)


def fit_buyer_similarity_profile(
    cohort: BuyerCohortBuild,
    *,
    product_id: str,
    assignment_chunk_size: int = DEFAULT_ASSIGNMENT_CHUNK_SIZE,
) -> dict[str, Any]:
    """Fit the largest supported bounded profile using only FIT buyers."""

    product = str(product_id).strip()
    support = next(
        (item for item in cohort.manifest.product_support if item.product_id == product),
        None,
    )
    if support is None:
        raise BuyerSimilarityFitError("The requested product is absent from the cohort.")
    if cohort.manifest.feature_contract_sha256 != FEATURE_CONTRACT_SHA256:
        raise BuyerSimilarityFitError("The cohort feature contract is incompatible.")
    if support.status != "ELIGIBLE":
        raise BuyerSimilarityFitError("The requested product does not have eligible buyer support.")
    if (cohort.manifest.split_strategy_version == SUPPORT_AWARE_SPLIT_VERSION
        and (cohort.manifest.split_status != "FEASIBLE"
             or not cohort.manifest.partition_manifest_sha256)):
        raise BuyerSimilarityFitError("The support-aware partition is not feasible or complete.")
    product_rows = cohort.frame.loc[cohort.frame["product_id"] == product].copy()
    if product_rows.empty or product_rows["customer_id"].duplicated().any():
        raise BuyerSimilarityFitError("The product cohort is empty or not customer-grain.")
    fit_rows = product_rows.loc[product_rows["split"] == "FIT"].copy()
    holdout_rows = product_rows.loc[product_rows["split"] == "HOLDOUT"].copy()
    if len(fit_rows) != support.fit_buyers or len(holdout_rows) != support.holdout_buyers:
        raise BuyerSimilarityFitError("The cohort support manifest is inconsistent.")
    if set(fit_rows["customer_id"]) & set(holdout_rows["customer_id"]):
        raise BuyerSimilarityFitError("FIT and HOLDOUT customer identities overlap.")

    fit_rows = fit_rows.sort_values("customer_id", kind="stable").reset_index(drop=True)
    fit_features = validate_and_normalize_feature_frame(
        fit_rows.loc[:, ORDERED_FEATURES]
    )
    customer_ids = [str(value) for value in fit_rows["customer_id"]]
    numeric_scales = _fit_scales(fit_features)
    vocabulary = _fit_vocabulary(fit_features)
    minimum_support = max(30, math.ceil(0.02 * len(fit_features)))

    diagnostics: list[dict[str, Any]] = []
    selected: tuple[int, list[dict[str, Any]], np.ndarray] | None = None
    for k in CANDIDATE_K_VALUES:
        diagnostic, prototypes, assignments = _fit_candidate(
            fit_features,
            customer_ids,
            k,
            numeric_scales=numeric_scales,
            categorical_vocabulary=vocabulary,
            chunk_size=assignment_chunk_size,
            minimum_support=minimum_support,
        )
        diagnostics.append(diagnostic)
        if diagnostic["valid"]:
            assert prototypes is not None and assignments is not None
            selected = (k, prototypes, assignments)
    if selected is None:
        raise BuyerSimilarityFitError("No supported clustering candidate converged.")
    realized_k, prototype_values, assignments = selected
    supports = np.bincount(assignments, minlength=realized_k)
    prototypes = [
        {
            "prototype_key": f"P{index + 1:03d}",
            "tie_order": index,
            "support": int(supports[index]),
            "values": {
                feature: prototype_values[index][feature] for feature in ORDERED_FEATURES
            },
        }
        for index in range(realized_k)
    ]
    source = cohort.manifest.source_identity
    lineage = {
        "cohort_contract_version": cohort.manifest.cohort_contract_version,
        "historical_context_sha256": cohort.manifest.context_identity_sha256,
        "resolved_window_start": cohort.manifest.window_start,
        "resolved_window_end": cohort.manifest.window_end,
        "buyer_conversion_definition": cohort.manifest.conversion_definition,
        "customer_import_id": source.customer_import_id,
        "customer_source_checksum": source.customer_source_checksum,
        "campaign_sales_import_id": source.campaign_sales_import_id,
        "campaign_sales_source_checksum": source.campaign_sales_source_checksum,
        "product_catalog_sha256": source.product_catalog_sha256,
        "fit_identity_sha256": support.fit_identity_sha256,
        "holdout_identity_sha256": support.holdout_identity_sha256,
        "split_strategy_version": cohort.manifest.split_strategy_version,
        "split_seed": cohort.manifest.split_seed,
    }
    if cohort.manifest.split_strategy_version == SUPPORT_AWARE_SPLIT_VERSION:
        lineage["split_objective_version"] = cohort.manifest.split_objective_version
        lineage["partition_manifest_sha256"] = cohort.manifest.partition_manifest_sha256
    payload: dict[str, Any] = {
        "serialization_contract_version": SERIALIZATION_CONTRACT_VERSION,
        "score_method_version": SCORE_METHOD_VERSION,
        "preprocessor_contract_version": PREPROCESSOR_CONTRACT_VERSION,
        "preprocessor_contract_sha256": PREPROCESSOR_CONTRACT_SHA256,
        "profile_implementation_version": PROFILE_IMPLEMENTATION_VERSION,
        "feature_contract_sha256": FEATURE_CONTRACT_SHA256,
        "immutable_identity_sha256": "",
        "product_id": product,
        "lineage": lineage,
        "training_parameters": {
            "candidate_k_values": list(CANDIDATE_K_VALUES),
            "random_seed": BUYER_SPLIT_SEED,
            "maximum_iterations": MAX_ITERATIONS,
            "convergence_rule": "ASSIGNMENTS_UNCHANGED",
            "initialization": "SEEDED_SORTED_FIRST_THEN_FARTHEST_FIRST",
            "numeric_update": "MEDIAN",
            "categorical_update": "MODE_CANONICAL_LEXICAL_TIE",
            "nearest_tie": "FROZEN_PROTOTYPE_ORDER",
            "minimum_cluster_support": minimum_support,
            "feature_weight": FEATURE_WEIGHT,
            "minimum_feature_coverage": MINIMUM_FEATURE_COVERAGE,
            "assignment_chunk_size_not_identity_bearing": True,
        },
        "numeric_scales": numeric_scales,
        "categorical_vocabulary": vocabulary,
        "candidate_diagnostics": diagnostics,
        "realized_k": realized_k,
        "fit_support": len(fit_features),
        "holdout_support": len(holdout_rows),
        "prototypes": prototypes,
        "library_versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "quantile_method": "linear",
        },
    }
    payload["immutable_identity_sha256"] = _profile_identity(payload, include_existing=False)
    return _validate_artifact_payload(payload)


def serialize_profile_artifact(artifact: Mapping[str, Any]) -> tuple[bytes, str, str]:
    payload = _validate_artifact_payload(dict(artifact))
    data = (_canonical_json(payload) + "\n").encode("utf-8")
    return data, hashlib.sha256(data).hexdigest(), _sha256_json(payload)


def write_profile_artifact(
    artifact: Mapping[str, Any],
    *,
    project_root: str | Path,
) -> StoredProfileArtifact:
    """Atomically write one artifact below its governed immutable path."""

    payload = _validate_artifact_payload(dict(artifact))
    root = Path(project_root).resolve()
    relative = ARTIFACT_ROOT / f"profile_{payload['immutable_identity_sha256']}" / "profile.json"
    destination = (root / relative).resolve()
    if not destination.is_relative_to(root) or destination.is_symlink():
        raise BuyerSimilarityArtifactError("The governed artifact path is unsafe.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    data, artifact_sha256, profile_payload_sha256 = serialize_profile_artifact(payload)
    if destination.exists():
        if destination.is_file() and destination.read_bytes() == data:
            return StoredProfileArtifact(
                storage_uri=relative.as_posix(),
                artifact_sha256=artifact_sha256,
                profile_payload_sha256=profile_payload_sha256,
            )
        raise BuyerSimilarityArtifactError(
            "An immutable profile path already contains different content."
        )
    temporary = destination.parent / f".{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return StoredProfileArtifact(
        storage_uri=relative.as_posix(),
        artifact_sha256=artifact_sha256,
        profile_payload_sha256=profile_payload_sha256,
    )


def load_profile_artifact(
    *,
    project_root: str | Path,
    storage_uri: str,
    expected_artifact_sha256: str,
    expected_product_id: str | None = None,
    expected_lineage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Load only an exact governed JSON artifact with current lineage."""

    if not isinstance(storage_uri, str) or _STORAGE_URI.fullmatch(storage_uri) is None:
        raise BuyerSimilarityArtifactError("The stored artifact URI is not governed.")
    root = Path(project_root).resolve()
    path = (root / Path(storage_uri)).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.is_symlink():
        raise BuyerSimilarityArtifactError("The profile artifact is missing or unsafe.")
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise BuyerSimilarityArtifactError("The profile artifact exceeds the size limit.")
    data = path.read_bytes()
    actual_sha256 = hashlib.sha256(data).hexdigest()
    if actual_sha256 != str(expected_artifact_sha256).strip().lower():
        raise BuyerSimilarityArtifactError("The profile artifact checksum does not match.")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuyerSimilarityArtifactError("The profile artifact JSON is invalid.") from exc
    profile = _validate_artifact_payload(payload)
    if expected_product_id is not None and profile["product_id"] != expected_product_id:
        raise BuyerSimilarityArtifactError("The profile product identity is stale.")
    for field, expected in (expected_lineage or {}).items():
        if field not in profile["lineage"] or profile["lineage"][field] != expected:
            raise BuyerSimilarityArtifactError("The profile source lineage is stale.")
    if profile["lineage"]["split_strategy_version"] == SUPPORT_AWARE_SPLIT_VERSION:
        from app.services.buyer_similarity_partition_service import (
            BuyerPartitionError, load_partition_manifest,
        )

        try:
            partition = load_partition_manifest(
                project_root=root,
                context_sha256=profile["lineage"]["historical_context_sha256"],
                partition_sha256=profile["lineage"]["partition_manifest_sha256"],
            )
        except BuyerPartitionError as exc:
            raise BuyerSimilarityArtifactError("The profile partition is unavailable.") from exc
        support = next((item for item in partition["product_support"]
                        if item["product_id"] == profile["product_id"]), None)
        if (support is None or support["fit_identity_sha256"] != profile["lineage"]["fit_identity_sha256"]
            or support["holdout_identity_sha256"] != profile["lineage"]["holdout_identity_sha256"]):
            raise BuyerSimilarityArtifactError("The profile partition membership is stale.")
    return profile


__all__ = (
    "ARTIFACT_ROOT",
    "BuyerSimilarityArtifactError",
    "BuyerSimilarityFitError",
    "BuyerSimilarityProfileError",
    "BuyerSimilarityScore",
    "CANDIDATE_K_VALUES",
    "DEFAULT_ASSIGNMENT_CHUNK_SIZE",
    "FEATURE_WEIGHT",
    "MAX_ITERATIONS",
    "MINIMUM_FEATURE_COVERAGE",
    "PREPROCESSOR_CONTRACT_VERSION",
    "PREPROCESSOR_CONTRACT_SHA256",
    "PROFILE_IMPLEMENTATION_VERSION",
    "SCORE_METHOD_VERSION",
    "SERIALIZATION_CONTRACT_VERSION",
    "StoredProfileArtifact",
    "describe_profile_holdout",
    "fit_buyer_similarity_profile",
    "load_profile_artifact",
    "score_buyer_similarity_record",
    "score_buyer_similarity_frame",
    "serialize_profile_artifact",
    "write_profile_artifact",
)
