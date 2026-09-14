"""Exact Phase 10 model reuse, synchronous training, and pre-scoring validation."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pulearn import BaggingPuClassifier

from app.jobs.model_training_worker import run_model_training_job
from app.ml.evaluation import EVALUATION_CONTRACT_VERSION
from app.ml.feature_contract import (
    CATEGORICAL_FEATURES,
    FEATURE_CONTRACT,
    FEATURE_CONTRACT_SHA256,
    FEATURE_CONTRACT_VERSION,
    NUMERIC_FEATURES,
    ORDERED_FEATURES,
)
from app.ml.model_roles import (
    CHALLENGER_1_MODEL_NAME,
    CHALLENGER_1_ROLE,
    DIAGNOSTIC_CONTROL_NAME,
    DIAGNOSTIC_CONTROL_ROLE,
    MODEL_ROLE_POLICY_VERSION,
    PRIMARY_MODEL_NAME,
    PRIMARY_ROLE,
    PRIMARY_ROLE_GOVERNED_SELECTION,
)
from app.ml.preprocessing import split_customer_cohort
from app.repositories.job_repository import JobRepository
from app.repositories.model_run_repository import ModelRunRepository
from app.repositories.phase10_intelligence_repository import (
    Phase10IntelligenceRepository,
)
from app.schemas.phase10_intelligence import (
    PHASE10_AUTOMATED_TRAINING_POLICY_VERSION,
    PHASE10_AUTOMATED_TRAINING_RANDOM_SEED,
    PHASE10_AUTOMATED_TRAINING_RUN_ELKAN_CHALLENGER,
    PHASE10_AUTOMATED_TRAINING_VALIDATION_FRACTION,
    PHASE10_COMPATIBILITY_CONTRACT_VERSION,
    PHASE10_HISTORICAL_WINDOW_POLICY_VERSION,
    PHASE10_MULTI_PRODUCT_POSITIVE_POLICY_VERSION,
    PHASE10_TRAINING_ELIGIBILITY_POLICY_VERSION,
)
from app.services.historical_source_provenance_service import (
    HistoricalSourceProvenance,
    HistoricalSourceProvenanceError,
    resolve_current_historical_source_provenance,
)
from app.services.model_training_service import (
    DEFAULT_ARTIFACT_ROOT,
    ModelArtifactError,
    load_verified_model_artifact,
)
from app.services.phase10_context_identity_service import (
    CompatibilityFingerprint,
    ModelingContextIdentity,
    build_historical_compatibility_fingerprint,
    build_model_compatibility_fingerprint,
    normalize_modeling_context,
)
from app.services.phase10_historical_resolution_service import (
    HistoricalAnalysisResolution,
)
from app.services.training_cohort_service import (
    TrainingCohort,
    TrainingCohortError,
    reconstruct_training_cohort,
)


ModelResolutionStatus = Literal["READY", "BLOCKED"]
ModelDiscoverySource = Literal[
    "PHASE10_CURRENT_GENERATION",
    "PHASE10_REUSABLE_GENERATION",
    "LEGACY_MODEL_RUN",
]

_EXPECTED_PREPROCESSING_KEYS = {
    "preprocessing_contract_version",
    "raw_feature_order",
    "raw_feature_count",
    "transformed_feature_names",
    "transformed_feature_count",
    "category_cardinalities",
    "numeric_imputation_values",
    "unknown_categories",
    "fit_scope",
}
_EXPECTED_HYPERPARAMETER_KEYS = {
    "model_role_policy_version",
    "primary_candidate",
    "challenger_1",
    "diagnostic_control",
    "selected_candidate",
    "selection_policy",
    "algorithm_metadata",
}
_EXPECTED_EVALUATION_KEYS = {
    "evaluation_contract_version",
    "model_role_policy_version",
    "primary_candidate",
    "challenger_candidates",
    "diagnostic_controls",
    "selection_policy",
    "candidate_results",
    "challenger_comparison",
    "selected_candidate",
    "selection_reason",
    "quality_flags",
}
_PROHIBITED_METADATA_KEYS = {
    "customer_id",
    "customer_ids",
    "person_id",
    "person_ids",
    "first_name",
    "last_name",
    "email",
    "phone_number",
    "address_line_1",
    "address_line_2",
    "street",
    "postal_code",
    "train_matrix",
    "validation_matrix",
    "validation_scores",
    "raw_training_rows",
}


class Phase10ModelResolutionError(RuntimeError):
    """Raised when the Phase 10 model boundary cannot resolve safely."""


class Phase10ModelValidationError(Phase10ModelResolutionError):
    """Raised when a selected model fails the mandatory pre-scoring gate."""

    def __init__(self, reason_codes: tuple[str, ...]) -> None:
        super().__init__(
            "The model is not compatible with the current Phase 10 contract: "
            + ", ".join(reason_codes)
        )
        self.reason_codes = reason_codes


@dataclass(frozen=True)
class ModelCandidateRecord:
    model_run_id: int
    discovery_source: ModelDiscoverySource
    generation_id: int | None


@dataclass(frozen=True)
class ModelCandidateRejection(ModelCandidateRecord):
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class ValidatedPhase10Model:
    model_run_id: int
    analysis_run_id: int
    artifact_sha256: str
    model_compatibility: CompatibilityFingerprint


@dataclass(frozen=True)
class Phase10ModelResolution:
    status: ModelResolutionStatus
    analysis_run_id: int | None
    model_run_id: int | None
    training_job_id: int | None
    reused: bool
    trained: bool
    model_compatibility: CompatibilityFingerprint | None
    compatible_candidates: tuple[ModelCandidateRecord, ...]
    rejected_candidates: tuple[ModelCandidateRejection, ...]
    business_message: str


SynchronousTrainingWorker = Callable[..., None]
TrainingProgressObserver = Callable[[str, int, str | None], None]


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _decode_json_object(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _contains_prohibited_metadata(value: Any) -> bool:
    if isinstance(value, dict):
        if _PROHIBITED_METADATA_KEYS.intersection(value):
            return True
        return any(_contains_prohibited_metadata(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_prohibited_metadata(item) for item in value)
    return False


def _append_reason(reasons: list[str], code: str) -> None:
    if code not in reasons:
        reasons.append(code)


def _expected_split_counts(cohort: TrainingCohort) -> dict[str, int]:
    split = split_customer_cohort(
        cohort.frame,
        validation_fraction=PHASE10_AUTOMATED_TRAINING_VALIDATION_FRACTION,
        random_seed=PHASE10_AUTOMATED_TRAINING_RANDOM_SEED,
    )
    return {
        "reconstructed_observation_count": cohort.observation_count,
        "selected_customer_count": cohort.selected_customer_count,
        "positive_customer_count": cohort.positive_customer_count,
        "unlabeled_customer_count": cohort.unlabeled_customer_count,
        "train_customer_count": len(split.train_labels),
        "validation_customer_count": len(split.validation_labels),
        "train_positive_count": int(split.train_labels.sum()),
        "validation_positive_count": int(split.validation_labels.sum()),
    }


def _valid_preprocessing_metadata(value: dict[str, Any] | None) -> bool:
    if value is None or set(value) != _EXPECTED_PREPROCESSING_KEYS:
        return False
    names = value.get("transformed_feature_names")
    cardinalities = value.get("category_cardinalities")
    imputations = value.get("numeric_imputation_values")
    return (
        value.get("preprocessing_contract_version") == "1"
        and value.get("raw_feature_order") == list(ORDERED_FEATURES)
        and value.get("raw_feature_count") == len(ORDERED_FEATURES)
        and isinstance(names, list)
        and bool(names)
        and all(isinstance(item, str) and item for item in names)
        and len(set(names)) == len(names)
        and value.get("transformed_feature_count") == len(names)
        and isinstance(cardinalities, dict)
        and set(cardinalities) == set(CATEGORICAL_FEATURES)
        and all(isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in cardinalities.values())
        and isinstance(imputations, dict)
        and set(imputations) == set(NUMERIC_FEATURES)
        and all(
            isinstance(item, (int, float))
            and not isinstance(item, bool)
            and math.isfinite(float(item))
            for item in imputations.values()
        )
        and value.get("unknown_categories") == "ignored_safely"
        and value.get("fit_scope") == "training_partition_only"
    )


def _valid_hyperparameter_metadata(
    value: dict[str, Any] | None,
    *,
    row_algorithm: Any,
) -> bool:
    if value is None or set(value) != _EXPECTED_HYPERPARAMETER_KEYS:
        return False
    algorithm = value.get("algorithm_metadata")
    if not isinstance(algorithm, dict):
        return False
    parameters = algorithm.get("hyperparameters")
    return (
        value.get("model_role_policy_version") == MODEL_ROLE_POLICY_VERSION
        and value.get("primary_candidate") == PRIMARY_MODEL_NAME
        and value.get("challenger_1") == CHALLENGER_1_MODEL_NAME
        and value.get("diagnostic_control") == DIAGNOSTIC_CONTROL_NAME
        and value.get("selected_candidate") == PRIMARY_MODEL_NAME
        and value.get("selection_policy") == PRIMARY_ROLE_GOVERNED_SELECTION
        and algorithm.get("algorithm") == "pulearn.BaggingPuClassifier"
        and algorithm.get("algorithm") == row_algorithm
        and algorithm.get("candidate_role") == PRIMARY_ROLE
        and algorithm.get("eligible_for_official_selection") is True
        and algorithm.get("bounded_cpu_jobs") == 1
        and algorithm.get("label_input_contract")
        == {"known_positive": 1, "unlabeled": 0}
        and isinstance(parameters, dict)
        and parameters.get("n_jobs") == 1
        and parameters.get("random_state")
        == PHASE10_AUTOMATED_TRAINING_RANDOM_SEED
    )


def _valid_evaluation_metadata(value: dict[str, Any] | None) -> bool:
    if value is None or set(value) != _EXPECTED_EVALUATION_KEYS:
        return False
    candidates = value.get("candidate_results")
    if not isinstance(candidates, dict) or set(candidates) != {
        PRIMARY_MODEL_NAME,
        CHALLENGER_1_MODEL_NAME,
        DIAGNOSTIC_CONTROL_NAME,
    }:
        return False
    primary = candidates.get(PRIMARY_MODEL_NAME)
    challenger = candidates.get(CHALLENGER_1_MODEL_NAME)
    diagnostic = candidates.get(DIAGNOSTIC_CONTROL_NAME)
    if not all(isinstance(item, dict) for item in (primary, challenger, diagnostic)):
        return False
    assert isinstance(primary, dict)
    assert isinstance(challenger, dict)
    assert isinstance(diagnostic, dict)
    challenger_status = challenger.get("status")
    challenger_policy_valid = (
        challenger_status != "SKIPPED_DISABLED"
        if PHASE10_AUTOMATED_TRAINING_RUN_ELKAN_CHALLENGER
        else challenger_status == "SKIPPED_DISABLED"
    )
    return (
        value.get("evaluation_contract_version") == EVALUATION_CONTRACT_VERSION
        and value.get("model_role_policy_version") == MODEL_ROLE_POLICY_VERSION
        and value.get("primary_candidate") == PRIMARY_MODEL_NAME
        and value.get("challenger_candidates") == [CHALLENGER_1_MODEL_NAME]
        and value.get("diagnostic_controls") == [DIAGNOSTIC_CONTROL_NAME]
        and value.get("selection_policy") == PRIMARY_ROLE_GOVERNED_SELECTION
        and value.get("selected_candidate") == PRIMARY_MODEL_NAME
        and isinstance(value.get("selection_reason"), str)
        and bool(value["selection_reason"].strip())
        and isinstance(value.get("quality_flags"), list)
        and primary.get("candidate_role") == PRIMARY_ROLE
        and primary.get("eligible_for_official_selection") is True
        and primary.get("status") == "FITTED"
        and primary.get("is_genuine_pu") is True
        and challenger.get("candidate_role") == CHALLENGER_1_ROLE
        and challenger.get("eligible_for_official_selection") is False
        and challenger_policy_valid
        and diagnostic.get("candidate_role") == DIAGNOSTIC_CONTROL_ROLE
        and diagnostic.get("eligible_for_official_selection") is False
        and diagnostic.get("status") == "FITTED"
        and diagnostic.get("is_genuine_pu") is False
    )


def _model_reason_codes(
    database_path: str | Path,
    row: Mapping[str, Any],
    *,
    analysis_run_id: int,
    expected_counts: Mapping[str, int],
    project_root: str | Path | None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if row.get("status") != "COMPLETED":
        _append_reason(reasons, "STATUS_NOT_COMPLETED")
    if row.get("analysis_run_id") != analysis_run_id:
        _append_reason(reasons, "ANALYSIS_LINK_MISMATCH")
    if any(row.get(field) != value for field, value in expected_counts.items()):
        _append_reason(reasons, "COHORT_COUNTS_MISMATCH")
    if row.get("selected_candidate") != PRIMARY_MODEL_NAME:
        _append_reason(reasons, "PRIMARY_NOT_SELECTED")
    if (
        row.get("random_seed") != PHASE10_AUTOMATED_TRAINING_RANDOM_SEED
        or row.get("validation_fraction")
        != PHASE10_AUTOMATED_TRAINING_VALIDATION_FRACTION
    ):
        _append_reason(reasons, "AUTOMATED_TRAINING_POLICY_MISMATCH")

    feature = _decode_json_object(row.get("feature_contract_json"))
    preprocessing = _decode_json_object(row.get("preprocessing_json"))
    hyperparameters = _decode_json_object(row.get("hyperparameters_json"))
    evaluation = _decode_json_object(row.get("metrics_json"))
    libraries = _decode_json_object(row.get("library_versions_json"))

    if (
        feature != FEATURE_CONTRACT
        or feature is None
        or _json_sha256(feature) != FEATURE_CONTRACT_SHA256
        or feature.get("version") != FEATURE_CONTRACT_VERSION
    ):
        _append_reason(reasons, "FEATURE_CONTRACT_MISMATCH")
    if not _valid_preprocessing_metadata(preprocessing):
        _append_reason(reasons, "PREPROCESSING_METADATA_INVALID")
    if not _valid_hyperparameter_metadata(
        hyperparameters,
        row_algorithm=row.get("algorithm"),
    ):
        _append_reason(reasons, "HYPERPARAMETER_METADATA_INVALID")
    if evaluation is None or evaluation.get("model_role_policy_version") != (
        MODEL_ROLE_POLICY_VERSION
    ):
        _append_reason(reasons, "MODEL_ROLE_POLICY_MISMATCH")
    if evaluation is None or evaluation.get("evaluation_contract_version") != (
        EVALUATION_CONTRACT_VERSION
    ):
        _append_reason(reasons, "EVALUATION_CONTRACT_MISMATCH")
    challenger_status = None
    if evaluation is not None and isinstance(evaluation.get("candidate_results"), dict):
        challenger = evaluation["candidate_results"].get(CHALLENGER_1_MODEL_NAME)
        if isinstance(challenger, dict):
            challenger_status = challenger.get("status")
    if (
        PHASE10_AUTOMATED_TRAINING_RUN_ELKAN_CHALLENGER
        and challenger_status == "SKIPPED_DISABLED"
    ) or (
        not PHASE10_AUTOMATED_TRAINING_RUN_ELKAN_CHALLENGER
        and challenger_status != "SKIPPED_DISABLED"
    ):
        _append_reason(reasons, "AUTOMATED_TRAINING_POLICY_MISMATCH")
    if not _valid_evaluation_metadata(evaluation):
        _append_reason(reasons, "EVALUATION_METADATA_INVALID")
    if libraries is None:
        _append_reason(reasons, "LIBRARY_METADATA_INVALID")
    if any(
        _contains_prohibited_metadata(item)
        for item in (feature, preprocessing, hyperparameters, evaluation, libraries)
        if item is not None
    ):
        _append_reason(reasons, "PROHIBITED_MODEL_INPUT")

    model_run_id = row.get("model_run_id")
    if row.get("status") == "COMPLETED" and isinstance(model_run_id, int):
        try:
            payload = load_verified_model_artifact(
                database_path,
                model_run_id,
                project_root=project_root,
            )
            if (
                not isinstance(payload.get("estimator"), BaggingPuClassifier)
                or payload.get("raw_feature_order") != list(ORDERED_FEATURES)
            ):
                _append_reason(reasons, "ARTIFACT_INVALID")
        except (ModelArtifactError, OSError, ValueError, TypeError):
            _append_reason(reasons, "ARTIFACT_INVALID")
    else:
        _append_reason(reasons, "ARTIFACT_INVALID")
    return tuple(reasons)


def _generation_reason_codes(
    generation: Mapping[str, Any],
    model_row: Mapping[str, Any] | None,
    *,
    analysis_run_id: int,
    historical_filters_sha256: str,
    current_source: HistoricalSourceProvenance,
) -> tuple[str, ...]:
    reasons: list[str] = []
    expected = {
        "compatibility_contract_version": PHASE10_COMPATIBILITY_CONTRACT_VERSION,
        "historical_filters_sha256": historical_filters_sha256,
        "historical_window_policy_version": PHASE10_HISTORICAL_WINDOW_POLICY_VERSION,
        "multi_product_positive_policy_version": (
            PHASE10_MULTI_PRODUCT_POSITIVE_POLICY_VERSION
        ),
        "training_eligibility_policy_version": (
            PHASE10_TRAINING_ELIGIBILITY_POLICY_VERSION
        ),
        "customer_import_id": current_source.customer_import_id,
        "customer_source_checksum": current_source.customer_source_checksum,
        "campaign_sales_import_id": current_source.campaign_sales_import_id,
        "campaign_sales_source_checksum": current_source.campaign_sales_source_checksum,
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "feature_contract_sha256": FEATURE_CONTRACT_SHA256,
        "model_role_policy_version": MODEL_ROLE_POLICY_VERSION,
        "evaluation_contract_version": EVALUATION_CONTRACT_VERSION,
        "automated_training_policy_version": (
            PHASE10_AUTOMATED_TRAINING_POLICY_VERSION
        ),
        "analysis_run_id": analysis_run_id,
    }
    if any(generation.get(field) != value for field, value in expected.items()):
        _append_reason(reasons, "GENERATION_COMPATIBILITY_MISMATCH")
    if model_row is None:
        _append_reason(reasons, "MODEL_NOT_FOUND")
    elif generation.get("artifact_sha256") != model_row.get("artifact_sha256"):
        _append_reason(reasons, "GENERATION_ARTIFACT_MISMATCH")
    return tuple(reasons)


def _validated_model(
    row: Mapping[str, Any],
    *,
    historical_fingerprint: CompatibilityFingerprint,
) -> ValidatedPhase10Model:
    model_fingerprint = build_model_compatibility_fingerprint(
        historical_fingerprint=historical_fingerprint,
        analysis_run_id=int(row["analysis_run_id"]),
        feature_contract_version=FEATURE_CONTRACT_VERSION,
        feature_contract_sha256=FEATURE_CONTRACT_SHA256,
        model_role_policy_version=MODEL_ROLE_POLICY_VERSION,
        evaluation_contract_version=EVALUATION_CONTRACT_VERSION,
    )
    return ValidatedPhase10Model(
        model_run_id=int(row["model_run_id"]),
        analysis_run_id=int(row["analysis_run_id"]),
        artifact_sha256=str(row["artifact_sha256"]),
        model_compatibility=model_fingerprint,
    )


def validate_phase10_model_before_scoring(
    database_path: str | Path,
    model_run_id: int,
    *,
    analysis_run_id: int,
    historical_fingerprint: CompatibilityFingerprint,
    project_root: str | Path | None = None,
) -> ValidatedPhase10Model:
    """Re-run the complete Phase 10 model gate immediately before scoring."""

    row = ModelRunRepository(database_path).fetch_run(model_run_id)
    if row is None:
        raise Phase10ModelValidationError(("MODEL_NOT_FOUND",))
    try:
        cohort = reconstruct_training_cohort(database_path, analysis_run_id)
        expected_counts = _expected_split_counts(cohort)
    except (TrainingCohortError, ValueError) as exc:
        raise Phase10ModelValidationError(("COHORT_RECONCILIATION_FAILED",)) from exc
    reasons = _model_reason_codes(
        database_path,
        row,
        analysis_run_id=analysis_run_id,
        expected_counts=expected_counts,
        project_root=project_root,
    )
    if reasons:
        raise Phase10ModelValidationError(reasons)
    return _validated_model(row, historical_fingerprint=historical_fingerprint)


def _run_synchronous_training(
    database_path: str | Path,
    analysis_run_id: int,
    *,
    project_root: str | Path | None,
    artifact_root: str | Path,
    training_worker: SynchronousTrainingWorker,
    progress_observer: TrainingProgressObserver | None,
) -> tuple[int, int]:
    repository = JobRepository(database_path)
    job_id = repository.create_training_job(
        created_at=_utc_timestamp(),
        request_payload={
            "analysis_run_id": analysis_run_id,
            "model_name": f"Phase 10 model for analysis {analysis_run_id}",
            "random_seed": PHASE10_AUTOMATED_TRAINING_RANDOM_SEED,
            "validation_fraction": PHASE10_AUTOMATED_TRAINING_VALIDATION_FRACTION,
            "run_elkan_challenger": PHASE10_AUTOMATED_TRAINING_RUN_ELKAN_CHALLENGER,
        },
        message="Phase 10 governed model training queued.",
    )
    # This deliberately invokes the worker in-process. Submitting to the shared
    # single-worker pool from its parent Phase 10 worker would deadlock.
    training_worker(
        database_path,
        job_id,
        project_root=project_root,
        artifact_root=artifact_root,
        progress_observer=progress_observer,
    )
    job = repository.fetch_job(job_id)
    if job is None or job.get("status") != "COMPLETED" or not isinstance(
        job.get("model_run_id"), int
    ):
        raise Phase10ModelResolutionError(
            "Governed Phase 10 model training did not complete successfully."
        )
    return job_id, int(job["model_run_id"])


def resolve_or_train_phase10_model(
    database_path: str | Path,
    modeling_context: ModelingContextIdentity | Mapping[str, Any],
    historical_resolution: HistoricalAnalysisResolution,
    *,
    project_root: str | Path | None = None,
    artifact_root: str | Path = DEFAULT_ARTIFACT_ROOT,
    training_worker: SynchronousTrainingWorker = run_model_training_job,
    training_progress_observer: TrainingProgressObserver | None = None,
    build_if_missing: bool = True,
) -> Phase10ModelResolution | None:
    """Reuse an exact model or run governed synchronous training when absent."""

    identity = (
        modeling_context
        if isinstance(modeling_context, ModelingContextIdentity)
        else normalize_modeling_context(modeling_context)
    )
    if historical_resolution.modeling_context_sha256 != identity.modeling_context_sha256:
        raise Phase10ModelResolutionError(
            "Historical resolution does not match the Phase 10 Modeling Context."
        )
    if (
        historical_resolution.status != "READY"
        or historical_resolution.eligibility.status != "ELIGIBLE"
        or historical_resolution.analysis_run_id is None
    ):
        return Phase10ModelResolution(
            status="BLOCKED",
            analysis_run_id=historical_resolution.analysis_run_id,
            model_run_id=None,
            training_job_id=None,
            reused=False,
            trained=False,
            model_compatibility=None,
            compatible_candidates=(),
            rejected_candidates=(),
            business_message=historical_resolution.business_message,
        )

    analysis_run_id = historical_resolution.analysis_run_id
    try:
        current_source = resolve_current_historical_source_provenance(database_path)
        cohort = reconstruct_training_cohort(database_path, analysis_run_id)
        expected_counts = _expected_split_counts(cohort)
    except (HistoricalSourceProvenanceError, TrainingCohortError, ValueError) as exc:
        raise Phase10ModelResolutionError(
            "The exact Historical Analysis could not be reconciled for model reuse."
        ) from exc
    historical_fingerprint = build_historical_compatibility_fingerprint(
        modeling_context=identity,
        resolved_historical_filters=historical_resolution.resolved_filters,
        customer_source_checksum=current_source.customer_source_checksum,
        campaign_sales_source_checksum=current_source.campaign_sales_source_checksum,
    )
    filters_sha256 = _json_sha256(
        historical_resolution.resolved_filters.model_dump(mode="json")
    )
    model_repository = ModelRunRepository(database_path)
    compatible: list[ModelCandidateRecord] = []
    rejected: list[ModelCandidateRejection] = []

    generations = Phase10IntelligenceRepository(
        database_path
    ).list_reusable_model_generations(identity.modeling_context_sha256)
    for generation in generations:
        model_run_id = int(generation["model_run_id"])
        row = model_repository.fetch_run(model_run_id)
        reasons = list(
            _generation_reason_codes(
                generation,
                row,
                analysis_run_id=analysis_run_id,
                historical_filters_sha256=filters_sha256,
                current_source=current_source,
            )
        )
        if row is not None:
            for code in _model_reason_codes(
                database_path,
                row,
                analysis_run_id=analysis_run_id,
                expected_counts=expected_counts,
                project_root=project_root,
            ):
                _append_reason(reasons, code)
        source: ModelDiscoverySource = (
            "PHASE10_CURRENT_GENERATION"
            if generation["lifecycle_state"] == "CURRENT"
            else "PHASE10_REUSABLE_GENERATION"
        )
        record = ModelCandidateRecord(
            model_run_id=model_run_id,
            discovery_source=source,
            generation_id=int(generation["generation_id"]),
        )
        if reasons:
            rejected.append(
                ModelCandidateRejection(**record.__dict__, reason_codes=tuple(reasons))
            )
        else:
            compatible.append(record)
    if compatible:
        selected = compatible[0]
        row = model_repository.fetch_run(selected.model_run_id)
        assert row is not None
        validated = _validated_model(row, historical_fingerprint=historical_fingerprint)
        return Phase10ModelResolution(
            status="READY",
            analysis_run_id=analysis_run_id,
            model_run_id=validated.model_run_id,
            training_job_id=None,
            reused=True,
            trained=False,
            model_compatibility=validated.model_compatibility,
            compatible_candidates=tuple(compatible),
            rejected_candidates=tuple(rejected),
            business_message="A verified model is ready.",
        )

    legacy_compatible: list[ModelCandidateRecord] = []
    for row in model_repository.list_analysis_candidates(analysis_run_id):
        model_run_id = int(row["model_run_id"])
        reasons = _model_reason_codes(
            database_path,
            row,
            analysis_run_id=analysis_run_id,
            expected_counts=expected_counts,
            project_root=project_root,
        )
        record = ModelCandidateRecord(
            model_run_id=model_run_id,
            discovery_source="LEGACY_MODEL_RUN",
            generation_id=None,
        )
        if reasons:
            rejected.append(
                ModelCandidateRejection(**record.__dict__, reason_codes=reasons)
            )
        else:
            legacy_compatible.append(record)
    if legacy_compatible:
        selected = legacy_compatible[0]
        row = model_repository.fetch_run(selected.model_run_id)
        assert row is not None
        validated = _validated_model(row, historical_fingerprint=historical_fingerprint)
        return Phase10ModelResolution(
            status="READY",
            analysis_run_id=analysis_run_id,
            model_run_id=validated.model_run_id,
            training_job_id=None,
            reused=True,
            trained=False,
            model_compatibility=validated.model_compatibility,
            compatible_candidates=tuple(legacy_compatible),
            rejected_candidates=tuple(rejected),
            business_message="A verified model is ready.",
        )

    if not build_if_missing:
        return None

    job_id, model_run_id = _run_synchronous_training(
        database_path,
        analysis_run_id,
        project_root=project_root,
        artifact_root=artifact_root,
        training_worker=training_worker,
        progress_observer=training_progress_observer,
    )
    validated = validate_phase10_model_before_scoring(
        database_path,
        model_run_id,
        analysis_run_id=analysis_run_id,
        historical_fingerprint=historical_fingerprint,
        project_root=project_root,
    )
    return Phase10ModelResolution(
        status="READY",
        analysis_run_id=analysis_run_id,
        model_run_id=model_run_id,
        training_job_id=job_id,
        reused=False,
        trained=True,
        model_compatibility=validated.model_compatibility,
        compatible_candidates=(),
        rejected_candidates=tuple(rejected),
        business_message="A verified model is ready.",
    )


def find_reusable_phase10_model(
    database_path: str | Path,
    modeling_context: ModelingContextIdentity | Mapping[str, Any],
    historical_resolution: HistoricalAnalysisResolution,
    *,
    project_root: str | Path | None = None,
) -> Phase10ModelResolution | None:
    """Resolve an exact model candidate without starting training."""

    return resolve_or_train_phase10_model(
        database_path,
        modeling_context,
        historical_resolution,
        project_root=project_root,
        build_if_missing=False,
    )


__all__ = (
    "ModelCandidateRecord",
    "ModelCandidateRejection",
    "Phase10ModelResolution",
    "Phase10ModelResolutionError",
    "Phase10ModelValidationError",
    "ValidatedPhase10Model",
    "find_reusable_phase10_model",
    "resolve_or_train_phase10_model",
    "validate_phase10_model_before_scoring",
)
