"""PU-aware validation metrics and genuine-PU model selection."""

from __future__ import annotations

import importlib.metadata
import json
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

from app.ml.preprocessing import CustomerCohortSplit
from app.ml.pu_estimators import (
    BAGGING_PU_NAME,
    ELKAN_NOTO_NAME,
    NAIVE_BASELINE_NAME,
)
from app.ml.training import CandidateTrainingResult, TrainingCandidateSet


EVALUATION_CONTRACT_VERSION = "1"
TOP_SLICE_FRACTIONS = (0.05, 0.10, 0.20)
LOW_POSITIVE_COUNT_THRESHOLD = 30
LOW_SCORE_STANDARD_DEVIATION_THRESHOLD = 1e-12
MINIMUM_MEANINGFUL_TOP10_LIFT = 1.05
PROPENSITY_STABILITY_BOUNDS = (0.01, 0.99)

OBSERVED_LABEL_DISCLAIMER = (
    "These measure separation of labeled positives from unlabeled observations, "
    "not true positives from true negatives."
)


class ModelEvaluationError(RuntimeError):
    """Raised when validation or genuine-PU selection cannot be completed safely."""


@dataclass(frozen=True)
class ModelEvaluationResult:
    """Runtime selection result plus its bounded persistence-safe snapshot."""

    selected_candidate: str
    selected_candidate_result: CandidateTrainingResult
    selection_reason: str
    quality_flags: tuple[str, ...]
    candidate_results: dict[str, dict[str, Any]]
    snapshot: dict[str, Any]
    canonical_json: str


def _finite_number(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ModelEvaluationError("Evaluation produced a non-finite metric.")
    return number


def _score_summary(scores: np.ndarray) -> dict[str, int | float]:
    if scores.size == 0:
        raise ModelEvaluationError("Score summaries require a non-empty label group.")
    quantiles = np.quantile(scores, (0.10, 0.25, 0.75, 0.90), method="linear")
    return {
        "count": int(scores.size),
        "mean": _finite_number(np.mean(scores)),
        "median": _finite_number(np.median(scores)),
        "std": _finite_number(np.std(scores, ddof=0)),
        "p10": _finite_number(quantiles[0]),
        "p25": _finite_number(quantiles[1]),
        "p75": _finite_number(quantiles[2]),
        "p90": _finite_number(quantiles[3]),
    }


def _ks_statistic(left: np.ndarray, right: np.ndarray) -> float:
    """Return the two-sample empirical KS statistic without another dependency."""
    combined = np.sort(np.concatenate((left, right)))
    left_cdf = np.searchsorted(np.sort(left), combined, side="right") / left.size
    right_cdf = np.searchsorted(np.sort(right), combined, side="right") / right.size
    return _finite_number(np.max(np.abs(left_cdf - right_cdf)))


def _top_slice_metrics(
    labels: np.ndarray,
    scores: np.ndarray,
    *,
    positive_count: int,
    prevalence: float,
) -> dict[str, dict[str, int | float]]:
    # Split order is deterministic. Positional order is therefore a stable,
    # non-PII secondary key for exact score ties.
    positions = np.arange(labels.size, dtype=np.int64)
    ranking = np.lexsort((positions, -scores))
    results: dict[str, dict[str, int | float]] = {}
    for fraction in TOP_SLICE_FRACTIONS:
        top_n = max(1, math.ceil(labels.size * fraction))
        captured = int(np.sum(labels[ranking[:top_n]] == 1))
        concentration = captured / top_n
        key = f"top_{round(fraction * 100):02d}_percent"
        results[key] = {
            "fraction": fraction,
            "top_n": top_n,
            "known_positives_captured": captured,
            "known_positive_recall_at_k": _finite_number(
                captured / positive_count
            ),
            "known_positive_concentration_at_k": _finite_number(concentration),
            "known_positive_lift_at_k": _finite_number(
                concentration / prevalence
            ),
        }
    return results


def _quality_flags(
    candidate: CandidateTrainingResult,
    *,
    positive_count: int,
    score_std: float,
    top10_lift: float,
    mean_difference: float,
) -> tuple[str, ...]:
    flags: list[str] = []
    if positive_count < LOW_POSITIVE_COUNT_THRESHOLD:
        flags.append("LOW_POSITIVE_COUNT")
    if score_std <= LOW_SCORE_STANDARD_DEVIATION_THRESHOLD:
        flags.append("LOW_SCORE_VARIANCE")
    if top10_lift < MINIMUM_MEANINGFUL_TOP10_LIFT:
        flags.append("LOW_TOP10_LIFT")
    if mean_difference < 0:
        flags.append("POSITIVE_SCORE_DISTRIBUTION_WORSE")
    if candidate.name == ELKAN_NOTO_NAME:
        propensity = candidate.algorithm_metadata.get("labeling_propensity_c")
        if isinstance(propensity, (int, float)) and not isinstance(propensity, bool):
            lower, upper = PROPENSITY_STABILITY_BOUNDS
            if not lower <= float(propensity) <= upper:
                flags.append("PU_PROPENSITY_ESTIMATE_UNSTABLE")
    return tuple(flags)


def _evaluate_fitted_candidate(
    candidate: CandidateTrainingResult,
    labels: np.ndarray,
    *,
    positive_count: int,
    unlabeled_count: int,
    prevalence: float,
) -> dict[str, Any]:
    scores = candidate.validation_scores
    if scores is None:
        raise ModelEvaluationError(
            f"Fitted candidate {candidate.name} has no validation scores."
        )
    score_array = np.asarray(scores, dtype=np.float64)
    if score_array.ndim != 1 or score_array.size != labels.size:
        raise ModelEvaluationError(
            f"Candidate {candidate.name} validation scores have an invalid shape."
        )
    if not np.isfinite(score_array).all():
        raise ModelEvaluationError(
            f"Candidate {candidate.name} returned non-finite validation scores."
        )
    if (score_array < 0).any():
        raise ModelEvaluationError(
            f"Candidate {candidate.name} returned negative validation scores."
        )
    if candidate.fit_seconds < 0 or candidate.score_seconds < 0:
        raise ModelEvaluationError(
            f"Candidate {candidate.name} returned a negative runtime."
        )

    positive_scores = score_array[labels == 1]
    unlabeled_scores = score_array[labels == 0]
    positive_summary = _score_summary(positive_scores)
    unlabeled_summary = _score_summary(unlabeled_scores)
    top_slices = _top_slice_metrics(
        labels,
        score_array,
        positive_count=positive_count,
        prevalence=prevalence,
    )
    mean_difference = _finite_number(
        positive_summary["mean"] - unlabeled_summary["mean"]
    )
    score_std = _finite_number(np.std(score_array, ddof=0))
    top10_lift = float(
        top_slices["top_10_percent"]["known_positive_lift_at_k"]
    )
    flags = _quality_flags(
        candidate,
        positive_count=positive_count,
        score_std=score_std,
        top10_lift=top10_lift,
        mean_difference=mean_difference,
    )

    return {
        "name": candidate.name,
        "status": candidate.status,
        "is_genuine_pu": candidate.is_genuine_pu,
        "role": "official_candidate" if candidate.is_genuine_pu else "diagnostic_only",
        "validation_context": {
            "validation_customer_count": int(labels.size),
            "validation_positive_count": positive_count,
            "validation_unlabeled_count": unlabeled_count,
            "observed_positive_prevalence": prevalence,
        },
        "observed_label_diagnostics": {
            "observed_label_roc_auc": _finite_number(
                roc_auc_score(labels, score_array)
            ),
            "observed_label_average_precision": _finite_number(
                average_precision_score(labels, score_array)
            ),
            "disclaimer": OBSERVED_LABEL_DISCLAIMER,
        },
        "top_slice_metrics": top_slices,
        "score_distributions": {
            "known_positive": positive_summary,
            "unlabeled": unlabeled_summary,
        },
        "separation_diagnostics": {
            "positive_minus_unlabeled_mean_score": mean_difference,
            "observed_label_ks_statistic": _ks_statistic(
                positive_scores, unlabeled_scores
            ),
            "overall_score_standard_deviation": score_std,
        },
        "runtime": {
            "fit_seconds": _finite_number(candidate.fit_seconds),
            "scoring_seconds": _finite_number(candidate.score_seconds),
        },
        "algorithm_metadata": candidate.algorithm_metadata,
        "library_versions": {
            "pulearn": importlib.metadata.version("pulearn"),
            "scikit-learn": importlib.metadata.version("scikit-learn"),
        },
        "warnings": list(candidate.warnings),
        "quality_flags": list(flags),
    }


def _skipped_candidate_snapshot(candidate: CandidateTrainingResult) -> dict[str, Any]:
    return {
        "name": candidate.name,
        "status": candidate.status,
        "is_genuine_pu": candidate.is_genuine_pu,
        "role": "official_candidate" if candidate.is_genuine_pu else "diagnostic_only",
        "skip_reason": candidate.skip_reason,
        "runtime": {
            "fit_seconds": _finite_number(candidate.fit_seconds),
            "scoring_seconds": _finite_number(candidate.score_seconds),
        },
        "algorithm_metadata": candidate.algorithm_metadata,
        "warnings": list(candidate.warnings),
        "quality_flags": (
            ["CHALLENGER_SKIPPED_RUNTIME"]
            if candidate.status == "SKIPPED_RUNTIME"
            else []
        ),
    }


def _selection_key(result: dict[str, Any]) -> tuple[float, ...]:
    slices = result["top_slice_metrics"]
    separation = result["separation_diagnostics"]
    observed = result["observed_label_diagnostics"]
    runtime = result["runtime"]
    return (
        float(slices["top_10_percent"]["known_positive_lift_at_k"]),
        float(slices["top_10_percent"]["known_positive_recall_at_k"]),
        float(slices["top_05_percent"]["known_positive_lift_at_k"]),
        float(slices["top_20_percent"]["known_positive_lift_at_k"]),
        float(separation["observed_label_ks_statistic"]),
        float(observed["observed_label_average_precision"]),
        -(float(runtime["fit_seconds"]) + float(runtime["scoring_seconds"])),
        1.0 if result["name"] == ELKAN_NOTO_NAME else 0.0,
    )


def _select_genuine_pu(
    candidates: tuple[CandidateTrainingResult, ...],
    results: dict[str, dict[str, Any]],
) -> tuple[CandidateTrainingResult, str]:
    eligible = [
        candidate
        for candidate in candidates
        if candidate.status == "FITTED"
        and candidate.is_genuine_pu
        and candidate.name != NAIVE_BASELINE_NAME
        and "LOW_SCORE_VARIANCE" not in results[candidate.name]["quality_flags"]
    ]
    if not eligible:
        raise ModelEvaluationError(
            "No fitted, finite, nonconstant genuine PU candidate is eligible for selection."
        )

    selected = max(eligible, key=lambda item: _selection_key(results[item.name]))
    selected_metrics = results[selected.name]
    top10 = selected_metrics["top_slice_metrics"]["top_10_percent"]
    separation = selected_metrics["separation_diagnostics"]
    comparison = ", ".join(
        (
            f"{candidate.name} top-10 lift="
            f"{results[candidate.name]['top_slice_metrics']['top_10_percent']['known_positive_lift_at_k']:.6f}"
            "/recall="
            f"{results[candidate.name]['top_slice_metrics']['top_10_percent']['known_positive_recall_at_k']:.6f}"
        )
        for candidate in eligible
    )
    reason = (
        f"Selected {selected.name}, a genuine PU candidate, using deterministic "
        "top-slice ranking, separation, runtime, and simplicity priorities: "
        f"top-10 lift={top10['known_positive_lift_at_k']:.6f}, "
        f"top-10 recall={top10['known_positive_recall_at_k']:.6f}, "
        "observed-label KS="
        f"{separation['observed_label_ks_statistic']:.6f}. Genuine-PU comparison: "
        f"{comparison}. "
        f"{NAIVE_BASELINE_NAME} was diagnostic-only and ineligible."
    )
    return selected, reason


def evaluate_and_select_model(
    candidates: TrainingCandidateSet,
    split: CustomerCohortSplit,
) -> ModelEvaluationResult:
    """Evaluate every fitted candidate and select only a genuine PU candidate."""
    if not isinstance(candidates, TrainingCandidateSet) or not isinstance(
        split, CustomerCohortSplit
    ):
        raise ModelEvaluationError(
            "Evaluation requires the validated Step 4 candidates and Step 3 split."
        )
    labels = np.asarray(split.validation_labels, dtype=np.int8)
    if labels.ndim != 1 or labels.size == 0 or not set(np.unique(labels)) <= {0, 1}:
        raise ModelEvaluationError("Validation labels must be a non-empty 0/1 vector.")
    positive_count = int(np.sum(labels == 1))
    unlabeled_count = int(np.sum(labels == 0))
    if positive_count == 0 or unlabeled_count == 0:
        raise ModelEvaluationError(
            "Evaluation requires both validation positives and unlabeled customers."
        )
    if len(split.validation_customer_ids) != labels.size:
        raise ModelEvaluationError("Validation customer and label counts do not match.")
    if split.validation_customer_ids.isna().any() or not split.validation_customer_ids.is_unique:
        raise ModelEvaluationError("Validation customer keys must be present and unique.")

    prevalence = _finite_number(positive_count / labels.size)
    ordered_candidates = (
        candidates.elkan_noto,
        candidates.bagging_pu,
        candidates.naive_diagnostic,
    )
    if len({candidate.name for candidate in ordered_candidates}) != 3:
        raise ModelEvaluationError("Candidate names must be unique.")
    candidate_results: dict[str, dict[str, Any]] = {}
    for candidate in ordered_candidates:
        if candidate.status == "FITTED":
            candidate_results[candidate.name] = _evaluate_fitted_candidate(
                candidate,
                labels,
                positive_count=positive_count,
                unlabeled_count=unlabeled_count,
                prevalence=prevalence,
            )
        else:
            candidate_results[candidate.name] = _skipped_candidate_snapshot(candidate)

    selected, selection_reason = _select_genuine_pu(
        ordered_candidates, candidate_results
    )
    overall_flags = {"OBSERVED_LABEL_METRICS_ONLY"}
    overall_flags.update(candidate_results[selected.name]["quality_flags"])
    if any(candidate.status == "SKIPPED_RUNTIME" for candidate in ordered_candidates):
        overall_flags.add("CHALLENGER_SKIPPED_RUNTIME")
    quality_flags = tuple(sorted(overall_flags))
    snapshot = {
        "evaluation_contract_version": EVALUATION_CONTRACT_VERSION,
        "candidate_results": candidate_results,
        "selected_candidate": selected.name,
        "selection_reason": selection_reason,
        "quality_flags": list(quality_flags),
    }
    try:
        canonical_json = json.dumps(
            snapshot,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ModelEvaluationError(
            "Evaluation snapshot contains non-canonical JSON metadata."
        ) from exc

    return ModelEvaluationResult(
        selected_candidate=selected.name,
        selected_candidate_result=selected,
        selection_reason=selection_reason,
        quality_flags=quality_flags,
        candidate_results=candidate_results,
        snapshot=snapshot,
        canonical_json=canonical_json,
    )


__all__ = (
    "EVALUATION_CONTRACT_VERSION",
    "ModelEvaluationError",
    "ModelEvaluationResult",
    "OBSERVED_LABEL_DISCLAIMER",
    "evaluate_and_select_model",
)
