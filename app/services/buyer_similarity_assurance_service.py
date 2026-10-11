"""Bounded, descriptive assurance for the v3 buyer-similarity method.

No result here estimates purchase probability, response, or lift. Inputs must
come from explicitly identified, current sources; this module never selects an
audience or changes a scoring generation.
"""

from __future__ import annotations

import csv
import gzip
import math
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from app.ml.feature_contract import (
    CATEGORICAL_FEATURES, NUMERIC_FEATURES, ORDERED_FEATURES,
    UNKNOWN_CATEGORY, validate_and_normalize_feature_frame,
)
from app.services.buyer_similarity_cohort_service import BuyerCohortBuild
from app.services.buyer_similarity_profile_service import (
    BuyerSimilarityScore, MINIMUM_FEATURE_COVERAGE, _distance_terms, _fit_candidate, _fit_scales,
    _fit_vocabulary, _validate_artifact_payload,
    load_profile_artifact, score_buyer_similarity_frame, score_buyer_similarity_record,
)


ASSURANCE_CONTRACT_VERSION = "BUYER_SIMILARITY_DESCRIPTIVE_ASSURANCE_V1"
PSI_EPSILON = 1e-6
MAX_SAMPLE_ROWS = 10_000
NUMERIC_QUANTILES = (0.0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0)
BOOTSTRAP_SEEDS = (20261008, 20261009, 20261010)
BOOTSTRAP_FIT_BUDGET = 256
ASSURANCE_HOLDOUT_BUDGET = 256
EXPLANATION_SAMPLE_LIMIT = 50
MINIMUM_AGGREGATE_EXPLANATION_SUPPORT = 5


class BuyerSimilarityAssuranceError(ValueError):
    """Assurance inputs are stale, mixed, or outside the bounded contract."""


def _features(frame: pd.DataFrame, *, label: str) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or tuple(frame.columns) != ORDERED_FEATURES:
        raise BuyerSimilarityAssuranceError(f"{label} must have the exact shared feature order.")
    if not 1 <= len(frame) <= MAX_SAMPLE_ROWS:
        raise BuyerSimilarityAssuranceError(f"{label} sample size is outside the bounded range.")
    return validate_and_normalize_feature_frame(frame.reset_index(drop=True))


def _psi(left: np.ndarray, right: np.ndarray) -> float:
    if len(left) != len(right):
        raise BuyerSimilarityAssuranceError("Distribution bins do not align.")
    p = np.maximum(left.astype(float), PSI_EPSILON)
    q = np.maximum(right.astype(float), PSI_EPSILON)
    return float(np.sum((q - p) * np.log(q / p)))


def _distribution(training: pd.DataFrame, comparison: pd.DataFrame) -> dict[str, Any]:
    """Fix all numeric edges and categorical vocabularies on training only."""

    numeric: dict[str, Any] = {}
    categorical: dict[str, Any] = {}
    for feature in NUMERIC_FEATURES:
        fit = training[feature].dropna().to_numpy(dtype=float)
        other = comparison[feature].dropna().to_numpy(dtype=float)
        edges = sorted(set(float(np.quantile(fit, q)) for q in (0.05, 0.25, 0.5, 0.75, 0.95))) if len(fit) else []
        # Searchsorted places both tails in bounded bins; missing is separate.
        left_counts = np.append(np.bincount(np.searchsorted(edges, fit, side="right"), minlength=len(edges) + 1), len(training) - len(fit))
        right_counts = np.append(np.bincount(np.searchsorted(edges, other, side="right"), minlength=len(edges) + 1), len(comparison) - len(other))
        observed = np.union1d(fit, other)
        ks = (float(np.max(np.abs(
            np.searchsorted(np.sort(fit), observed, side="right") / len(fit)
            - np.searchsorted(np.sort(other), observed, side="right") / len(other)
        ))) if len(fit) and len(other) else None)
        numeric[feature] = {
            "training_quantiles": {str(q): (float(np.quantile(fit, q)) if len(fit) else None) for q in NUMERIC_QUANTILES},
            "training_range": [float(min(fit)), float(max(fit))] if len(fit) else None,
            "comparison_range": [float(min(other)), float(max(other))] if len(other) else None,
            "training_defined_bin_edges": edges,
            "training_bin_counts_including_missing": left_counts.astype(int).tolist(),
            "comparison_bin_counts_including_missing": right_counts.astype(int).tolist(),
            "training_missing_count": len(training) - len(fit),
            "comparison_missing_count": len(comparison) - len(other),
            "ks_nonmissing": ks,
            "psi_including_missing": _psi(left_counts / len(training), right_counts / len(comparison)),
        }
    for feature in CATEGORICAL_FEATURES:
        vocab = sorted(set(training[feature].astype(str)) - {UNKNOWN_CATEGORY})
        bins = vocab + ["__OTHER__", "__MISSING__"]
        def counts(frame: pd.DataFrame) -> list[int]:
            values = frame[feature].astype(str)
            return [int((values == value).sum()) for value in vocab] + [
                int((~values.isin(vocab) & (values != UNKNOWN_CATEGORY)).sum()),
                int((values == UNKNOWN_CATEGORY).sum()),
            ]
        left = np.asarray(counts(training), dtype=float)
        right = np.asarray(counts(comparison), dtype=float)
        categorical[feature] = {
            "training_defined_bins": bins,
            "training_counts": left.astype(int).tolist(),
            "comparison_counts": right.astype(int).tolist(),
            "total_variation": float(0.5 * np.sum(np.abs(left / len(training) - right / len(comparison)))),
            "psi": _psi(left / len(training), right / len(comparison)),
        }
    return {"training_count": len(training), "comparison_count": len(comparison),
            "psi_epsilon": PSI_EPSILON, "numeric": numeric, "categorical": categorical}


def _score_description(frame: pd.DataFrame, profile: Mapping[str, Any]) -> dict[str, Any]:
    scored = score_buyer_similarity_frame(frame, profile)
    valid = np.asarray([item.buyer_similarity_score for item in scored if item.is_valid], dtype=float)
    invalid: dict[str, int] = {}
    for item in scored:
        if not item.is_valid:
            reason = str(item.invalid_reason_code)
            invalid[reason] = invalid.get(reason, 0) + 1
    return {
        "population_count": len(scored), "valid_count": len(valid),
        "invalid_count": len(scored) - len(valid), "invalid_reasons": invalid,
        "minimum": float(np.min(valid)) if len(valid) else None,
        "median": float(np.median(valid)) if len(valid) else None,
        "maximum": float(np.max(valid)) if len(valid) else None,
        "mean": float(np.mean(valid)) if len(valid) else None,
        "all_valid_scores_tied": bool(len(valid) and np.min(valid) == np.max(valid)),
    }


def _bootstrap_stability(
    fit: pd.DataFrame, holdout: pd.DataFrame, profile: Mapping[str, Any],
) -> dict[str, Any]:
    """Refit fixed published k on FIT buyers only; no holdout-based selection."""

    fit_sample = fit.iloc[:BOOTSTRAP_FIT_BUDGET].reset_index(drop=True)
    check = holdout.iloc[:ASSURANCE_HOLDOUT_BUDGET].reset_index(drop=True)
    baseline = score_buyer_similarity_frame(check, profile)
    baseline_values = np.asarray([
        np.nan if score.buyer_similarity_score is None else score.buyer_similarity_score
        for score in baseline
    ])
    repetitions: list[dict[str, Any]] = []
    for seed in BOOTSTRAP_SEEDS:
        rng = np.random.default_rng(seed)
        sample = fit_sample.iloc[
            rng.integers(0, len(fit_sample), size=len(fit_sample))
        ].reset_index(drop=True)
        scales = _fit_scales(sample)
        vocabulary = _fit_vocabulary(sample)
        diagnostic, prototypes, assignments = _fit_candidate(
            sample, [f"B{row:06d}" for row in range(len(sample))],
            int(profile["realized_k"]), numeric_scales=scales,
            categorical_vocabulary=vocabulary, chunk_size=256,
            minimum_support=max(30, math.ceil(0.02 * len(sample))),
        )
        if prototypes is None or assignments is None:
            repetitions.append({"seed": seed, "valid": False,
                                "reason": diagnostic["reason"]})
            continue
        values_list: list[float] = []
        for row in check.to_dict(orient="records"):
            best = min(
                (_distance_terms(row, prototype, numeric_scales=scales,
                                 categorical_vocabulary=vocabulary)[:2], index)
                for index, prototype in enumerate(prototypes)
            )[0]
            values_list.append(1.0 - best[0] if best[1] >= MINIMUM_FEATURE_COVERAGE else np.nan)
        values = np.asarray(values_list)
        mask = np.isfinite(baseline_values) & np.isfinite(values)
        newly_invalid = int(np.sum(np.isfinite(baseline_values) & ~np.isfinite(values)))
        if not np.any(mask):
            repetitions.append({"seed": seed, "valid": True,
                                "reason": "NO_VALID_REFERENCE_HOLDOUT_SCORES",
                                "newly_invalid_holdout_count": newly_invalid,
                                "mean_absolute_score_change": None,
                                "top_quartile_overlap_jaccard": None})
            continue
        before = baseline_values[mask]
        after = values[mask]
        n_top = max(1, math.ceil(len(before) * 0.25))
        left = set(np.argsort(-before, kind="stable")[:n_top].tolist())
        right = set(np.argsort(-after, kind="stable")[:n_top].tolist())
        repetitions.append({
            "seed": seed, "valid": True, "reason": "DESCRIPTIVE_ONLY",
            "newly_invalid_holdout_count": newly_invalid,
            "comparable_holdout_count": int(np.sum(mask)),
            "mean_absolute_score_change": float(np.mean(np.abs(before - after))),
            "top_quartile_overlap_jaccard": len(left & right) / len(left | right),
            "prototype_supports": np.bincount(assignments, minlength=len(prototypes)).astype(int).tolist(),
        })
    changes = [r["mean_absolute_score_change"] for r in repetitions
               if r["valid"] and r["mean_absolute_score_change"] is not None]
    overlaps = [r["top_quartile_overlap_jaccard"] for r in repetitions
                if r["valid"] and r["top_quartile_overlap_jaccard"] is not None]
    return {
        "fit_only": True, "fixed_published_k": profile["realized_k"],
        "fit_sample_count": len(fit_sample), "holdout_check_count": len(check),
        "seeds": list(BOOTSTRAP_SEEDS), "repetitions": repetitions,
        "mean_absolute_score_change_range": [min(changes), max(changes)] if changes else None,
        "top_quartile_overlap_range": [min(overlaps), max(overlaps)] if overlaps else None,
        "uncertainty_note": "Three bounded bootstrap replicates are a sensitivity diagnostic, not a confidence interval or predictive validation.",
    }


def _perturbation_sensitivity(
    holdout: pd.DataFrame, profile: Mapping[str, Any],
) -> dict[str, Any]:
    check = holdout.iloc[:ASSURANCE_HOLDOUT_BUDGET].reset_index(drop=True)
    baseline = score_buyer_similarity_frame(check, profile)
    base = np.asarray([np.nan if s.buyer_similarity_score is None else s.buyer_similarity_score
                       for s in baseline])
    by_feature: dict[str, Any] = {}
    for feature in ORDERED_FEATURES:
        modified = check.copy()
        modified[feature] = np.nan if feature in NUMERIC_FEATURES else UNKNOWN_CATEGORY
        changed = score_buyer_similarity_frame(modified, profile)
        scores = np.asarray([np.nan if s.buyer_similarity_score is None else s.buyer_similarity_score
                             for s in changed])
        comparable = np.isfinite(base) & np.isfinite(scores)
        by_feature[feature] = {
            "perturbation": "MASK_FEATURE_TO_MISSING",
            "comparable_count": int(np.sum(comparable)),
            "newly_invalid_count": int(np.sum(np.isfinite(base) & ~np.isfinite(scores))),
            "mean_absolute_score_change": (float(np.mean(np.abs(base[comparable] - scores[comparable])))
                                           if np.any(comparable) else None),
        }
    return {"holdout_check_count": len(check), "by_feature": by_feature}


def explain_buyer_similarity_record(
    record: Mapping[str, Any], artifact: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the scorer's exact terms, without prototype values or identities."""

    profile = _validate_artifact_payload(dict(artifact))
    scored: BuyerSimilarityScore = score_buyer_similarity_record(record, profile)
    terms = [{"feature": term.feature, "weight": 1 / len(ORDERED_FEATURES),
              "distance": term.distance, "weighted_contribution": term.weighted_contribution,
              "input_known": term.input_known, "prototype_known": term.prototype_known}
             for term in scored.feature_distances]
    if scored.is_valid and not math.isclose(
        sum(term["weighted_contribution"] for term in terms),
        float(scored.prototype_distance), abs_tol=1e-12,
    ):
        raise BuyerSimilarityAssuranceError("Explanation does not reconcile to the score.")
    return {
        "explanation_contract_version": "WINNING_PROFILE_DISTANCE_V1",
        "product_id": profile["product_id"],
        "historical_context_sha256": profile["lineage"]["historical_context_sha256"],
        "fit_buyer_support": profile["fit_support"],
        "winning_profile_support": next((p["support"] for p in profile["prototypes"]
                                         if p["prototype_key"] == scored.prototype_key), None),
        "feature_coverage": scored.feature_coverage,
        "similarity_score": scored.buyer_similarity_score,
        "distance": scored.prototype_distance,
        "valid": scored.is_valid,
        "invalid_reason_code": scored.invalid_reason_code,
        "feature_terms": terms,
        "meaning": "Weighted demographic resemblance to a supported product-buyer profile; not purchase probability, response, or causation.",
    }


def summarize_result_explanations(
    database_path: str | Path, *, project_root: str | Path,
    snapshot: Mapping[str, Any], profile_rows: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    """Aggregate exact winning-profile terms for at most 50 snapshot members.

    Caller must have verified that the immutable result and profiles are current.
    No person, prototype, or contact identifier is returned.
    """

    root = Path(project_root).resolve()
    membership = (root / str(snapshot["storage_uri"])).resolve()
    if not membership.is_relative_to(root / "artifacts" / "similarity_results"):
        raise BuyerSimilarityAssuranceError("Result membership path is not governed.")
    with gzip.open(membership, "rt", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        selected = []
        for index, row in enumerate(reader):
            if index >= EXPLANATION_SAMPLE_LIMIT:
                break
            selected.append(row)
    if not selected:
        return {"scope": "EMPTY_RESULT", "sample_count": 0, "feature_drivers": []}
    if len(selected) < MINIMUM_AGGREGATE_EXPLANATION_SUPPORT:
        return {"scope": "INSUFFICIENT_AGGREGATE_SUPPORT",
                "sample_count": len(selected),
                "result_count": int(snapshot["resolved_count"]),
                "feature_drivers": [],
                "meaning": "At least five selected members are required for an aggregate feature explanation."}
    profile_by_product = {
        str(row["product_id"]): load_profile_artifact(
            project_root=root, storage_uri=str(row["storage_uri"]),
            expected_artifact_sha256=str(row["artifact_sha256"]),
            expected_product_id=str(row["product_id"]),
        ) for row in profile_rows
    }
    identifiers = [str(row["person_id"]) for row in selected]
    marks = ",".join("?" for _ in identifiers)
    connection = sqlite3.connect(Path(database_path).resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        records = {str(row["person_id"]): dict(row) for row in connection.execute(
            f"SELECT person_id,{','.join(ORDERED_FEATURES)} FROM demographics WHERE person_id IN ({marks})",
            identifiers,
        )}
    finally:
        connection.close()
    totals = Counter({feature: 0.0 for feature in ORDERED_FEATURES})
    products = Counter()
    for member in selected:
        record = records.get(str(member["person_id"]))
        profile = profile_by_product.get(str(member["matched_product_id"]))
        if record is None or profile is None:
            raise BuyerSimilarityAssuranceError("An explanatory source member is unavailable.")
        record.pop("person_id")
        explanation = explain_buyer_similarity_record(record, profile)
        if (not explanation["valid"]
            or not math.isclose(float(explanation["similarity_score"]),
                                float(member["buyer_similarity_score"]), abs_tol=1e-12)):
            raise BuyerSimilarityAssuranceError("Explanatory score differs from immutable membership.")
        products[str(member["matched_product_id"])] += 1
        for term in explanation["feature_terms"]:
            totals[term["feature"]] += term["weighted_contribution"]
    drivers = sorted(
        ({"feature": feature, "mean_weighted_distance": total / len(selected)}
         for feature, total in totals.items()),
        key=lambda item: (-item["mean_weighted_distance"], item["feature"]),
    )
    return {
        "scope": "FIRST_50_SNAPSHOT_MEMBERS_BY_SAVED_RESULT_ORDER",
        "sample_count": len(selected),
        "result_count": int(snapshot["resolved_count"]),
        "selected_product_counts_in_sample": dict(sorted(products.items())),
        "fit_buyer_support_by_product": {
            product: profile_by_product[product]["fit_support"] for product in sorted(products)
        },
        "historical_context_sha256_by_product": {
            product: profile_by_product[product]["lineage"]["historical_context_sha256"]
            for product in sorted(products)
        },
        "feature_drivers": drivers,
        "meaning": "Observed weighted demographic differences in this bounded result sample; not purchase probability, response, or causation.",
    }


def evaluate_bounded_similarity_assurance(
    *, broad_training: pd.DataFrame, prospects: pd.DataFrame,
    cohort: BuyerCohortBuild, artifact: Mapping[str, Any],
    broad_training_source_checksum: str, prospect_source_checksum: str,
    expected_prospect_source_checksum: str, current_sources: bool,
    unrelated_product_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run fixed, bounded descriptive comparisons; never fit/tune on holdout."""

    profile = _validate_artifact_payload(dict(artifact))
    if not current_sources or prospect_source_checksum != expected_prospect_source_checksum:
        raise BuyerSimilarityAssuranceError("A current prospect source is required.")
    if broad_training_source_checksum != profile["lineage"]["customer_source_checksum"]:
        raise BuyerSimilarityAssuranceError("The broad training source is not the profile source.")
    if cohort.manifest.context_identity_sha256 != profile["lineage"]["historical_context_sha256"]:
        raise BuyerSimilarityAssuranceError("The buyer context is not the profile context.")
    support = next((s for s in cohort.manifest.product_support if s.product_id == profile["product_id"]), None)
    if support is None or support.fit_identity_sha256 != profile["lineage"]["fit_identity_sha256"] or support.holdout_identity_sha256 != profile["lineage"]["holdout_identity_sha256"]:
        raise BuyerSimilarityAssuranceError("The buyer split identity is not the profile split.")
    broad = _features(broad_training, label="Broad training")
    prospect = _features(prospects, label="Prospect")
    product_rows = cohort.frame.loc[cohort.frame["product_id"] == profile["product_id"]]
    fit = _features(product_rows.loc[product_rows["split"] == "FIT", ORDERED_FEATURES], label="Fit buyers")
    holdout = _features(product_rows.loc[product_rows["split"] == "HOLDOUT", ORDERED_FEATURES], label="Holdout buyers")
    if len(fit) != profile["fit_support"] or len(holdout) != profile["holdout_support"]:
        raise BuyerSimilarityAssuranceError("Buyer support differs from the published profile.")
    if set(product_rows.loc[product_rows["split"] == "FIT", "customer_id"]) & set(product_rows.loc[product_rows["split"] == "HOLDOUT", "customer_id"]):
        raise BuyerSimilarityAssuranceError("Buyer fit and holdout identities overlap.")
    control: dict[str, Any] | None = None
    if unrelated_product_artifact is not None:
        unrelated = _validate_artifact_payload(dict(unrelated_product_artifact))
        if unrelated["product_id"] == profile["product_id"]:
            raise BuyerSimilarityAssuranceError("Product control must be unrelated.")
        if unrelated["lineage"]["customer_source_checksum"] != broad_training_source_checksum:
            raise BuyerSimilarityAssuranceError("Product control uses a different customer source.")
        control = {"product_id": unrelated["product_id"],
                   "same_holdout_scored_by_control": _score_description(holdout, unrelated)}
    return {
        "contract_version": ASSURANCE_CONTRACT_VERSION,
        "scope": "BOUNDED_DESCRIPTIVE_SAMPLE",
        "source_identity": {"customer_source_checksum": broad_training_source_checksum,
                            "prospect_source_checksum": prospect_source_checksum,
                            "profile_identity_sha256": profile["immutable_identity_sha256"],
                            "fit_identity_sha256": support.fit_identity_sha256,
                            "holdout_identity_sha256": support.holdout_identity_sha256},
        "comparison_semantics": "UNLABELED_PROSPECTS_NOT_CONFIRMED_NONBUYERS",
        "broad_training_vs_prospects": _distribution(broad, prospect),
        "product_fit_buyers_vs_prospects": _distribution(fit, prospect),
        "independent_descriptive_holdout": _score_description(holdout, profile),
        "unlabeled_prospect_scores": _score_description(prospect, profile),
        "prototype_diagnostics": {"realized_k": profile["realized_k"],
                                  "fit_support": profile["fit_support"],
                                  "candidate_diagnostics": profile["candidate_diagnostics"],
                                  "prototype_supports": [p["support"] for p in profile["prototypes"]]},
        "bootstrap_fit_stability": _bootstrap_stability(fit, holdout, profile),
        "perturbation_sensitivity": _perturbation_sensitivity(holdout, profile),
        "unrelated_product_control": control,
        "predictive_validation": "UNAVAILABLE_INDEPENDENT_OUTCOMES_OR_DESIGN_REQUIRED",
        "response_lift_validation": "UNAVAILABLE",
    }


__all__ = ("ASSURANCE_CONTRACT_VERSION", "BuyerSimilarityAssuranceError",
           "evaluate_bounded_similarity_assurance", "explain_buyer_similarity_record",
           "summarize_result_explanations")
