"""End-to-end governed PU training, artifact persistence, and verification."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
import os
import platform
import sqlite3
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from app.database.schema import initialize_database
from app.ml.evaluation import evaluate_and_select_model
from app.ml.feature_contract import (
    FEATURE_CONTRACT_SHA256,
    FEATURE_CONTRACT_VERSION,
    ORDERED_FEATURES,
)
from app.ml.preprocessing import prepare_feature_matrices, split_customer_cohort
from app.ml.pu_estimators import positive_class_scores
from app.ml.training import train_pu_candidates
from app.repositories.model_run_repository import ModelRunRepository
from app.services.training_cohort_service import reconstruct_training_cohort


logger = logging.getLogger(__name__)

ARTIFACT_VERSION = "1"
DEFAULT_ARTIFACT_ROOT = Path("artifacts/models")
RELOAD_VALIDATION_SAMPLE_SIZE = 128
RELOAD_RELATIVE_TOLERANCE = 1e-12
RELOAD_ABSOLUTE_TOLERANCE = 1e-12
MAXIMUM_MODEL_NAME_LENGTH = 160
MAXIMUM_INTERNAL_ERROR_LENGTH = 65_536


class ModelTrainingServiceError(RuntimeError):
    """Base class for safe Phase 3 model-training service errors."""


class ModelTrainingValidationError(ModelTrainingServiceError):
    """Raised before a governed run can be created."""


class ModelTrainingExecutionError(ModelTrainingServiceError):
    """Raised after a governed run has failed."""

    def __init__(self, message: str, *, model_run_id: int) -> None:
        super().__init__(message)
        self.model_run_id = model_run_id


class ModelArtifactError(ModelTrainingServiceError):
    """Raised when a saved artifact is missing, corrupt, or incompatible."""


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _normalized_model_name(model_name: str | None, analysis_run_id: int) -> str:
    normalized = (
        f"PU model for analysis {analysis_run_id}"
        if model_name is None
        else model_name.strip()
    )
    if not normalized:
        raise ModelTrainingValidationError("model_name must not be blank.")
    if len(normalized) > MAXIMUM_MODEL_NAME_LENGTH:
        raise ModelTrainingValidationError(
            f"model_name must not exceed {MAXIMUM_MODEL_NAME_LENGTH} characters."
        )
    return normalized


def _project_and_artifact_roots(
    *,
    project_root: str | Path | None,
    artifact_root: str | Path,
) -> tuple[Path, Path]:
    project = Path.cwd().resolve() if project_root is None else Path(project_root).resolve()
    relative_root = Path(artifact_root)
    if relative_root.is_absolute() or ".." in relative_root.parts:
        raise ModelTrainingValidationError(
            "artifact_root must be a safe path relative to the project root."
        )
    resolved_root = (project / relative_root).resolve()
    if not resolved_root.is_relative_to(project):
        raise ModelTrainingValidationError(
            "artifact_root must remain within the project root."
        )
    return project, resolved_root


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _library_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        **{
            distribution: importlib.metadata.version(distribution)
            for distribution in (
                "joblib",
                "numpy",
                "pandas",
                "pulearn",
                "scikit-learn",
                "scipy",
            )
        },
    }


def _preprocessing_metadata(prepared: Any) -> dict[str, Any]:
    return {
        "preprocessing_contract_version": "1",
        "raw_feature_order": list(prepared.raw_feature_names),
        "raw_feature_count": len(prepared.raw_feature_names),
        "transformed_feature_names": list(prepared.transformed_feature_names),
        "transformed_feature_count": prepared.transformed_feature_count,
        "category_cardinalities": prepared.category_cardinalities,
        "numeric_imputation_values": prepared.numeric_imputation_values,
        "unknown_categories": "ignored_safely",
        "fit_scope": "training_partition_only",
    }


def _matrix_storage_bytes(matrix: Any) -> int:
    if all(hasattr(matrix, attribute) for attribute in ("data", "indices", "indptr")):
        return int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes)
    return int(np.asarray(matrix).nbytes)


def _artifact_payload(prepared: Any, evaluation: Any) -> dict[str, Any]:
    estimator = evaluation.selected_candidate_result.estimator
    if estimator is None:
        raise ModelArtifactError("The selected candidate has no fitted estimator.")
    return {
        "artifact_version": ARTIFACT_VERSION,
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "feature_contract_sha256": FEATURE_CONTRACT_SHA256,
        "raw_feature_order": list(ORDERED_FEATURES),
        "preprocessor": prepared.preprocessor,
        "estimator": estimator,
        "selected_candidate": evaluation.selected_candidate,
    }


def _validate_artifact_payload(payload: Any) -> dict[str, Any]:
    required_keys = {
        "artifact_version",
        "feature_contract_version",
        "feature_contract_sha256",
        "raw_feature_order",
        "preprocessor",
        "estimator",
        "selected_candidate",
    }
    if not isinstance(payload, dict) or set(payload) != required_keys:
        raise ModelArtifactError("The model artifact payload is incompatible.")
    if payload["artifact_version"] != ARTIFACT_VERSION:
        raise ModelArtifactError("The model artifact version is incompatible.")
    if payload["feature_contract_version"] != FEATURE_CONTRACT_VERSION:
        raise ModelArtifactError("The artifact feature-contract version is invalid.")
    if payload["feature_contract_sha256"] != FEATURE_CONTRACT_SHA256:
        raise ModelArtifactError("The artifact feature-contract checksum is invalid.")
    if tuple(payload["raw_feature_order"]) != ORDERED_FEATURES:
        raise ModelArtifactError("The artifact raw feature order is invalid.")
    if not isinstance(payload["selected_candidate"], str):
        raise ModelArtifactError("The artifact selected candidate is invalid.")
    if not hasattr(payload["preprocessor"], "transform") or not hasattr(
        payload["estimator"], "predict_proba"
    ):
        raise ModelArtifactError("The model artifact cannot transform and score.")
    return payload


def _verify_reloaded_scores(
    artifact_path: Path,
    *,
    validation_features: Any,
    expected_scores: np.ndarray,
) -> dict[str, Any]:
    try:
        payload = _validate_artifact_payload(joblib.load(artifact_path))
        sample_size = min(RELOAD_VALIDATION_SAMPLE_SIZE, len(validation_features))
        if sample_size <= 0:
            raise ModelArtifactError("Reload verification requires validation rows.")
        sample = validation_features.iloc[:sample_size]
        loaded_matrix = payload["preprocessor"].transform(sample)
        loaded_scores = positive_class_scores(
            payload["estimator"],
            loaded_matrix,
            require_unit_interval=False,
        )
        expected = np.asarray(expected_scores[:sample_size], dtype=np.float64)
        if loaded_scores.shape != expected.shape or not np.allclose(
            loaded_scores,
            expected,
            rtol=RELOAD_RELATIVE_TOLERANCE,
            atol=RELOAD_ABSOLUTE_TOLERANCE,
        ):
            raise ModelArtifactError(
                "Reloaded artifact scores do not match pre-persistence scores."
            )
        return payload
    except ModelArtifactError:
        raise
    except Exception as exc:
        raise ModelArtifactError("The persisted model artifact could not be reloaded.") from exc


def _cleanup_created_artifact(
    *,
    temporary_path: Path | None,
    final_path: Path | None,
    run_directory: Path | None,
    run_directory_created: bool,
) -> None:
    for path in (temporary_path, final_path):
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Unable to remove incomplete model artifact | path=%s", path)
    if run_directory_created and run_directory is not None:
        try:
            run_directory.rmdir()
        except OSError:
            logger.exception(
                "Unable to remove incomplete model artifact directory | path=%s",
                run_directory,
            )


def _stored_artifact_path(project_root: Path, raw_path: Any) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise ModelArtifactError("The completed model run has no artifact path.")
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ModelArtifactError("The stored model artifact path is unsafe.")
    resolved = (project_root / relative).resolve()
    if not resolved.is_relative_to(project_root):
        raise ModelArtifactError("The stored model artifact path is unsafe.")
    return resolved


def load_verified_model_artifact(
    database_path: str | Path,
    model_run_id: int,
    *,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Load a completed local artifact only after path and checksum verification."""
    if isinstance(model_run_id, bool) or not isinstance(model_run_id, int) or model_run_id <= 0:
        raise ModelTrainingValidationError("model_run_id must be a positive integer.")
    project = Path.cwd().resolve() if project_root is None else Path(project_root).resolve()
    row = ModelRunRepository(database_path).fetch_run(model_run_id)
    if row is None:
        raise ModelArtifactError("Model run was not found.")
    if row["status"] != "COMPLETED":
        raise ModelArtifactError("Only a completed model run can be loaded.")
    artifact_path = _stored_artifact_path(project, row["artifact_path"])
    if not artifact_path.is_file():
        raise ModelArtifactError("The model artifact file is missing.")
    actual_sha256 = _file_sha256(artifact_path)
    if actual_sha256 != row["artifact_sha256"]:
        raise ModelArtifactError("The model artifact checksum does not match.")
    try:
        payload = _validate_artifact_payload(joblib.load(artifact_path))
    except ModelArtifactError:
        raise
    except Exception as exc:
        raise ModelArtifactError("The model artifact could not be loaded.") from exc
    if payload["selected_candidate"] != row["selected_candidate"]:
        raise ModelArtifactError("The artifact selected candidate does not match metadata.")
    return payload


def train_and_persist_model(
    database_path: str | Path | None,
    analysis_run_id: int,
    *,
    model_name: str | None = None,
    random_seed: int = 42,
    validation_fraction: float = 0.20,
    run_challenger: bool = True,
    project_root: str | Path | None = None,
    artifact_root: str | Path = DEFAULT_ARTIFACT_ROOT,
) -> dict[str, Any]:
    """Execute the governed RUNNING-to-COMPLETED/FAILED model lifecycle."""
    if (
        isinstance(analysis_run_id, bool)
        or not isinstance(analysis_run_id, int)
        or analysis_run_id <= 0
    ):
        raise ModelTrainingValidationError(
            "analysis_run_id must be a positive integer."
        )
    if isinstance(random_seed, bool) or not isinstance(random_seed, int):
        raise ModelTrainingValidationError("random_seed must be an integer.")
    if (
        isinstance(validation_fraction, bool)
        or not isinstance(validation_fraction, (int, float))
        or not np.isfinite(validation_fraction)
        or not 0 < float(validation_fraction) < 1
    ):
        raise ModelTrainingValidationError(
            "validation_fraction must be between 0 and 1."
        )
    normalized_name = _normalized_model_name(model_name, analysis_run_id)
    project, artifact_storage_root = _project_and_artifact_roots(
        project_root=project_root,
        artifact_root=artifact_root,
    )
    initialized_path = initialize_database(database_path)
    repository = ModelRunRepository(initialized_path)
    try:
        model_run_id = repository.create_run(
            analysis_run_id=analysis_run_id,
            model_name=normalized_name,
            created_at=_utc_timestamp(),
            random_seed=random_seed,
            validation_fraction=float(validation_fraction),
        )
    except sqlite3.IntegrityError as exc:
        raise ModelTrainingValidationError(
            "The source historical analysis run does not exist."
        ) from exc

    run_directory: Path | None = None
    temporary_path: Path | None = None
    final_path: Path | None = None
    run_directory_created = False
    execution_started = time.perf_counter()
    stage_seconds: dict[str, float] = {}
    try:
        stage_started = time.perf_counter()
        cohort = reconstruct_training_cohort(initialized_path, analysis_run_id)
        stage_seconds["reconstruction"] = time.perf_counter() - stage_started
        stage_started = time.perf_counter()
        split = split_customer_cohort(
            cohort.frame,
            validation_fraction=float(validation_fraction),
            random_seed=random_seed,
        )
        stage_seconds["split"] = time.perf_counter() - stage_started
        stage_started = time.perf_counter()
        prepared = prepare_feature_matrices(split)
        stage_seconds["preprocessing"] = time.perf_counter() - stage_started
        stage_started = time.perf_counter()
        candidates = train_pu_candidates(
            prepared,
            split,
            random_seed=random_seed,
            run_challenger=run_challenger,
        )
        stage_seconds["candidate_training"] = time.perf_counter() - stage_started
        stage_started = time.perf_counter()
        evaluation = evaluate_and_select_model(candidates, split)
        stage_seconds["evaluation_selection"] = time.perf_counter() - stage_started
        selected_result = evaluation.selected_candidate_result
        expected_scores = selected_result.validation_scores
        if expected_scores is None:
            raise ModelArtifactError("The selected candidate has no validation scores.")

        stage_started = time.perf_counter()
        artifact_storage_root.mkdir(parents=True, exist_ok=True)
        run_directory = artifact_storage_root / f"model_run_{model_run_id:06d}"
        run_directory.mkdir(exist_ok=False)
        run_directory_created = True
        final_path = run_directory / "pu_model.joblib"
        temporary_path = run_directory / f".{uuid.uuid4().hex}.joblib.tmp"
        joblib.dump(_artifact_payload(prepared, evaluation), temporary_path, compress=3)
        os.replace(temporary_path, final_path)
        temporary_path = None
        _verify_reloaded_scores(
            final_path,
            validation_features=split.validation_features,
            expected_scores=np.asarray(expected_scores, dtype=np.float64),
        )
        artifact_sha256 = _file_sha256(final_path)
        artifact_relative_path = final_path.relative_to(project).as_posix()
        stage_seconds["persistence_reload_checksum"] = (
            time.perf_counter() - stage_started
        )

        counts = {
            "reconstructed_observation_count": cohort.observation_count,
            "selected_customer_count": cohort.selected_customer_count,
            "positive_customer_count": cohort.positive_customer_count,
            "unlabeled_customer_count": cohort.unlabeled_customer_count,
            "train_customer_count": len(split.train_labels),
            "validation_customer_count": len(split.validation_labels),
            "train_positive_count": int(split.train_labels.sum()),
            "validation_positive_count": int(split.validation_labels.sum()),
        }
        selected_metrics = evaluation.candidate_results[evaluation.selected_candidate]
        top10_lift = selected_metrics["top_slice_metrics"]["top_10_percent"][
            "known_positive_lift_at_k"
        ]
        summary = {
            "model_run_id": model_run_id,
            "analysis_run_id": analysis_run_id,
            "model_name": normalized_name,
            "status": "COMPLETED",
            "selected_candidate": evaluation.selected_candidate,
            "selected_customer_count": cohort.selected_customer_count,
            "positive_customer_count": cohort.positive_customer_count,
            "unlabeled_customer_count": cohort.unlabeled_customer_count,
            "train_customer_count": len(split.train_labels),
            "validation_customer_count": len(split.validation_labels),
            "validation_positive_count": int(split.validation_labels.sum()),
            "validation_lift_at_10_percent": float(top10_lift),
            "transformed_feature_count": prepared.transformed_feature_count,
            "approximate_memory_bytes": {
                "reconstructed_cohort_frame": cohort.approximate_memory_bytes,
                "training_feature_matrix": _matrix_storage_bytes(
                    prepared.train_matrix
                ),
                "validation_feature_matrix": _matrix_storage_bytes(
                    prepared.validation_matrix
                ),
            },
            "stage_seconds": stage_seconds,
            "quality_flags": list(evaluation.quality_flags),
            "artifact_path": artifact_relative_path,
            "artifact_sha256": artifact_sha256,
        }
        repository.complete_run(
            model_run_id=model_run_id,
            completed_at=_utc_timestamp(),
            algorithm=str(selected_result.algorithm_metadata["algorithm"]),
            selected_candidate=evaluation.selected_candidate,
            counts=counts,
            feature_contract_json=prepared.feature_contract_json,
            preprocessing_json=_canonical_json(_preprocessing_metadata(prepared)),
            hyperparameters_json=_canonical_json(
                {
                    "selected_candidate": evaluation.selected_candidate,
                    "algorithm_metadata": selected_result.algorithm_metadata,
                }
            ),
            metrics_json=evaluation.canonical_json,
            library_versions_json=_canonical_json(_library_versions()),
            artifact_path=artifact_relative_path,
            artifact_sha256=artifact_sha256,
        )
        summary["total_seconds"] = time.perf_counter() - execution_started
        return summary
    except Exception as exc:
        internal_diagnostic = traceback.format_exc()[-MAXIMUM_INTERNAL_ERROR_LENGTH:]
        _cleanup_created_artifact(
            temporary_path=temporary_path,
            final_path=final_path,
            run_directory=run_directory,
            run_directory_created=run_directory_created,
        )
        try:
            repository.fail_run(
                model_run_id=model_run_id,
                completed_at=_utc_timestamp(),
                error_message=internal_diagnostic,
            )
        except Exception:
            logger.exception(
                "Unable to persist failed model run | model_run_id=%s",
                model_run_id,
            )
        logger.exception(
            "PU model training failed | model_run_id=%s analysis_run_id=%s",
            model_run_id,
            analysis_run_id,
            exc_info=exc,
        )
        raise ModelTrainingExecutionError(
            "The PU model could not be trained and persisted.",
            model_run_id=model_run_id,
        ) from exc


__all__ = (
    "ARTIFACT_VERSION",
    "ModelArtifactError",
    "ModelTrainingExecutionError",
    "ModelTrainingServiceError",
    "ModelTrainingValidationError",
    "load_verified_model_artifact",
    "train_and_persist_model",
)
