"""Validate and reconcile customer-grain inputs for Phase 3 model training."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.ml.feature_contract import (
    INTERNAL_COHORT_COLUMNS,
    ORDERED_FEATURES,
    RAW_TRAINING_COLUMNS,
)
from app.repositories.model_training_repository import (
    ModelTrainingRepository,
)
from app.services.historical_analysis_service import (
    HistoricalAnalysisError,
    HistoricalAnalysisNotFoundError,
    get_historical_analysis_run,
)


class TrainingCohortError(Exception):
    """Base class for safe Phase 3 cohort reconstruction failures."""


class TrainingCohortRunError(TrainingCohortError):
    """Raised when the saved Phase 2 run cannot authorize model training."""


class TrainingCohortDataError(TrainingCohortError):
    """Raised when reconstructed raw fields violate the frozen boundary."""


class TrainingCohortReconciliationError(TrainingCohortError):
    """Raised when current sources no longer match the saved Phase 2 snapshot."""


@dataclass(frozen=True)
class TrainingCohort:
    """One reconciled, customer-grain raw frame for later preprocessing."""

    analysis_run_id: int
    conversion_definition: str
    reference_date: str
    filters: dict[str, Any]
    observation_count: int
    selected_customer_count: int
    positive_customer_count: int
    unlabeled_customer_count: int
    approximate_memory_bytes: int
    frame: pd.DataFrame


def _validate_raw_frame(frame: pd.DataFrame) -> None:
    if tuple(frame.columns) != RAW_TRAINING_COLUMNS:
        raise TrainingCohortDataError(
            "Reconstructed training data does not match the frozen raw feature boundary."
        )
    if frame["customer_id"].isna().any() or not frame["customer_id"].is_unique:
        raise TrainingCohortDataError(
            "Reconstructed training data must contain one unique customer row."
        )
    if frame["pu_label"].isna().any() or not set(frame["pu_label"].unique()) <= {0, 1}:
        raise TrainingCohortDataError(
            "Reconstructed PU labels must contain only known-positive or unlabeled values."
        )
    if not pd.api.types.is_integer_dtype(frame["age"].dtype):
        raise TrainingCohortDataError("Reconstructed age values must be integer or missing.")
    if not pd.api.types.is_float_dtype(frame["individual_yearly_income"].dtype):
        raise TrainingCohortDataError(
            "Reconstructed income values must be numeric or missing."
        )
    income = frame["individual_yearly_income"].dropna().to_numpy(dtype=float)
    if not np.isfinite(income).all():
        raise TrainingCohortDataError(
            "Reconstructed income values must be finite when present."
        )
    if not pd.api.types.is_integer_dtype(frame["family_member_count"].dtype):
        raise TrainingCohortDataError(
            "Reconstructed family counts must be integer or missing."
        )
    for column in ORDERED_FEATURES:
        if column in {"age", "individual_yearly_income", "family_member_count"}:
            continue
        if not isinstance(frame[column].dtype, pd.StringDtype):
            raise TrainingCohortDataError(
                "Reconstructed categorical values must be strings or missing."
            )


def _reconcile_counts(
    *,
    saved_summary: dict[str, Any],
    observation_count: int,
    frame: pd.DataFrame,
) -> tuple[int, int, int]:
    selected_count = len(frame)
    positive_count = int(frame["pu_label"].sum())
    unlabeled_count = selected_count - positive_count
    unique_customer_count = int(frame["customer_id"].nunique(dropna=False))

    actual = {
        "observation_count": observation_count,
        "selected_customer_count": selected_count,
        "positive_customer_count": positive_count,
        "unlabeled_customer_count": unlabeled_count,
    }
    expected = {field: int(saved_summary[field]) for field in actual}
    mismatches = [field for field in actual if actual[field] != expected[field]]
    if positive_count + unlabeled_count != selected_count:
        mismatches.append("positive_unlabeled_invariant")
    if unique_customer_count != selected_count:
        mismatches.append("unique_customer_count")
    if mismatches:
        fields = ", ".join(sorted(set(mismatches)))
        raise TrainingCohortReconciliationError(
            "Current historical sources do not reconcile with the saved analysis "
            f"for: {fields}."
        )
    return selected_count, positive_count, unlabeled_count


def reconstruct_training_cohort(
    database_path: str | Path,
    analysis_run_id: int,
) -> TrainingCohort:
    """Reconstruct and hard-stop unless current sources match a completed run."""
    if isinstance(analysis_run_id, bool) or not isinstance(analysis_run_id, int):
        raise TrainingCohortRunError("analysis_run_id must be a positive integer.")
    if analysis_run_id <= 0:
        raise TrainingCohortRunError("analysis_run_id must be a positive integer.")

    try:
        saved_run = get_historical_analysis_run(database_path, analysis_run_id)
    except HistoricalAnalysisNotFoundError as exc:
        raise TrainingCohortRunError("Historical analysis run was not found.") from exc
    except HistoricalAnalysisError as exc:
        raise TrainingCohortRunError(
            "The saved historical analysis could not be validated for training."
        ) from exc

    if saved_run["status"] != "COMPLETED":
        raise TrainingCohortRunError(
            "Model training requires a completed historical analysis run."
        )

    filters = saved_run["filters"]
    reference_date = filters["contact_date_to"]
    reconstructed = ModelTrainingRepository(database_path).reconstruct_customer_rows(
        filters=filters,
        reference_date=reference_date,
    )
    _validate_raw_frame(reconstructed.frame)
    selected_count, positive_count, unlabeled_count = _reconcile_counts(
        saved_summary=saved_run["summary"],
        observation_count=reconstructed.observation_count,
        frame=reconstructed.frame,
    )

    return TrainingCohort(
        analysis_run_id=analysis_run_id,
        conversion_definition=saved_run["conversion_definition"],
        reference_date=reference_date,
        filters=dict(filters),
        observation_count=reconstructed.observation_count,
        selected_customer_count=selected_count,
        positive_customer_count=positive_count,
        unlabeled_customer_count=unlabeled_count,
        approximate_memory_bytes=int(
            reconstructed.frame.memory_usage(index=True, deep=True).sum()
        ),
        frame=reconstructed.frame,
    )


__all__ = (
    "INTERNAL_COHORT_COLUMNS",
    "ORDERED_FEATURES",
    "RAW_TRAINING_COLUMNS",
    "TrainingCohort",
    "TrainingCohortDataError",
    "TrainingCohortError",
    "TrainingCohortReconciliationError",
    "TrainingCohortRunError",
    "reconstruct_training_cohort",
)
