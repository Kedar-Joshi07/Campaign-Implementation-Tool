"""Scoreability checks and preflight for Phase 5 prospect scoring."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.ml.evaluation import EVALUATION_CONTRACT_VERSION
from app.ml.feature_contract import (
    FEATURE_CONTRACT,
    FEATURE_CONTRACT_SHA256,
    FEATURE_CONTRACT_VERSION,
    ORDERED_FEATURES,
    FeatureContractError,
    validate_and_normalize_feature_frame,
)
from app.ml.model_roles import (
    CHALLENGER_1_MODEL_NAME,
    DIAGNOSTIC_CONTROL_NAME,
    MODEL_ROLE_POLICY_VERSION,
    PRIMARY_MODEL_NAME,
    PRIMARY_ROLE_GOVERNED_SELECTION,
)
from app.ml.pu_estimators import positive_class_scores
from app.repositories.model_run_repository import ModelRunRepository
from app.repositories.prospect_scoring_repository import ProspectScoringRepository
from app.repositories.prospect_scoring_repository import MAX_SCORING_CHUNK_LIMIT
from app.services.model_training_service import load_verified_model_artifact


class ModelScoringCompatibilityError(RuntimeError):
    """Base class for scoreability validation failures."""


class ModelScoreabilityValidationError(ModelScoringCompatibilityError):
    """Raised when a model cannot be used for prospect scoring."""


@dataclass(frozen=True)
class ScoreableModelContext:
    model_run_id: int
    selected_candidate: str
    model_role_policy_version: str
    evaluation_contract_version: str
    feature_contract_version: str
    feature_contract_sha256: str
    artifact_sha256: str
    artifact_payload: dict[str, Any]


@dataclass(frozen=True)
class ScoringPreflightResult:
    model_run_id: int
    demographic_snapshot_count: int
    demographic_min_person_id: str | None
    demographic_max_person_id: str | None
    preflight_row_count: int
    preflight_first_person_id: str
    preflight_last_person_id: str
    preflight_score_min: float
    preflight_score_max: float
    preflight_score_mean: float


def _decode_json_object(raw: Any, *, field_name: str) -> dict[str, Any]:
    if raw is None:
        raise ModelScoreabilityValidationError(f"{field_name} metadata is required.")
    if not isinstance(raw, str):
        raise ModelScoreabilityValidationError(f"{field_name} metadata is invalid.")
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ModelScoreabilityValidationError(f"{field_name} metadata is invalid.") from exc
    if not isinstance(decoded, dict):
        raise ModelScoreabilityValidationError(f"{field_name} metadata is invalid.")
    return decoded


def _assert_scoreable_status_and_candidate(row: dict[str, Any]) -> None:
    if row["status"] != "COMPLETED":
        raise ModelScoreabilityValidationError(
            "Only a completed model run can be scored against prospects."
        )
    selected_candidate = row.get("selected_candidate")
    if selected_candidate != PRIMARY_MODEL_NAME:
        raise ModelScoreabilityValidationError(
            "Only the governed BAGGING_PU primary candidate is scoreable."
        )


def _assert_governance(metrics: dict[str, Any]) -> None:
    if metrics.get("model_role_policy_version") != MODEL_ROLE_POLICY_VERSION:
        raise ModelScoreabilityValidationError(
            "The model role policy version is incompatible with prospect scoring."
        )
    if metrics.get("evaluation_contract_version") != EVALUATION_CONTRACT_VERSION:
        raise ModelScoreabilityValidationError(
            "The model evaluation contract version is incompatible with prospect scoring."
        )
    if metrics.get("selection_policy") != PRIMARY_ROLE_GOVERNED_SELECTION:
        raise ModelScoreabilityValidationError(
            "The model selection policy is incompatible with prospect scoring."
        )
    if metrics.get("selected_candidate") != PRIMARY_MODEL_NAME:
        raise ModelScoreabilityValidationError(
            "The selected model candidate is incompatible with prospect scoring."
        )
    if metrics.get("primary_candidate") != PRIMARY_MODEL_NAME:
        raise ModelScoreabilityValidationError(
            "The model primary candidate metadata is incompatible."
        )
    if metrics.get("challenger_candidates") != [CHALLENGER_1_MODEL_NAME]:
        raise ModelScoreabilityValidationError(
            "The challenger metadata is incompatible with prospect scoring."
        )
    if metrics.get("diagnostic_controls") != [DIAGNOSTIC_CONTROL_NAME]:
        raise ModelScoreabilityValidationError(
            "The diagnostic metadata is incompatible with prospect scoring."
        )


def _assert_feature_contract(feature_contract: dict[str, Any]) -> None:
    if feature_contract != FEATURE_CONTRACT:
        raise ModelScoreabilityValidationError(
            "The persisted feature contract does not match the frozen scoring contract."
        )
    if feature_contract.get("version") != FEATURE_CONTRACT_VERSION:
        raise ModelScoreabilityValidationError(
            "The persisted feature-contract version is incompatible."
        )
    if feature_contract.get("ordered_features") != list(ORDERED_FEATURES):
        raise ModelScoreabilityValidationError(
            "The persisted feature order is incompatible with prospect scoring."
        )


def validate_scoreable_model(
    database_path: str | Path,
    model_run_id: int,
    *,
    project_root: str | Path | None = None,
) -> ScoreableModelContext:
    if isinstance(model_run_id, bool) or not isinstance(model_run_id, int) or model_run_id <= 0:
        raise ModelScoreabilityValidationError("model_run_id must be a positive integer.")

    row = ModelRunRepository(database_path).fetch_run(model_run_id)
    if row is None:
        raise ModelScoreabilityValidationError("Model run was not found.")

    _assert_scoreable_status_and_candidate(row)
    metrics = _decode_json_object(row.get("metrics_json"), field_name="metrics_json")
    _assert_governance(metrics)
    feature_contract = _decode_json_object(
        row.get("feature_contract_json"),
        field_name="feature_contract_json",
    )
    _assert_feature_contract(feature_contract)

    try:
        artifact_payload = load_verified_model_artifact(
            database_path,
            model_run_id,
            project_root=project_root,
        )
    except Exception as exc:
        raise ModelScoreabilityValidationError(
            "The model artifact could not be verified for scoring."
        ) from exc

    if artifact_payload.get("selected_candidate") != PRIMARY_MODEL_NAME:
        raise ModelScoreabilityValidationError(
            "The artifact selected candidate does not match BAGGING_PU metadata."
        )
    if artifact_payload.get("feature_contract_version") != FEATURE_CONTRACT_VERSION:
        raise ModelScoreabilityValidationError(
            "The artifact feature-contract version is incompatible."
        )
    if artifact_payload.get("feature_contract_sha256") != FEATURE_CONTRACT_SHA256:
        raise ModelScoreabilityValidationError(
            "The artifact feature-contract checksum is incompatible."
        )

    return ScoreableModelContext(
        model_run_id=model_run_id,
        selected_candidate=PRIMARY_MODEL_NAME,
        model_role_policy_version=MODEL_ROLE_POLICY_VERSION,
        evaluation_contract_version=EVALUATION_CONTRACT_VERSION,
        feature_contract_version=FEATURE_CONTRACT_VERSION,
        feature_contract_sha256=FEATURE_CONTRACT_SHA256,
        artifact_sha256=str(row["artifact_sha256"]),
        artifact_payload=artifact_payload,
    )


def transform_and_score_prospect_chunk(
    *,
    artifact_payload: dict[str, Any],
    raw_features: pd.DataFrame,
) -> np.ndarray:
    normalized = validate_and_normalize_feature_frame(raw_features)
    matrix = artifact_payload["preprocessor"].transform(normalized)
    return positive_class_scores(
        artifact_payload["estimator"],
        matrix,
        require_unit_interval=True,
    )


def run_scoring_preflight(
    database_path: str | Path,
    model_run_id: int,
    *,
    chunk_limit: int = 1000,
    project_root: str | Path | None = None,
) -> ScoringPreflightResult:
    if isinstance(chunk_limit, bool) or not isinstance(chunk_limit, int) or chunk_limit <= 0:
        raise ModelScoreabilityValidationError("chunk_limit must be a positive integer.")
    if chunk_limit > MAX_SCORING_CHUNK_LIMIT:
        raise ModelScoreabilityValidationError(
            f"chunk_limit must not exceed {MAX_SCORING_CHUNK_LIMIT}."
        )

    context = validate_scoreable_model(
        database_path,
        model_run_id,
        project_root=project_root,
    )
    repository = ProspectScoringRepository(database_path)
    snapshot = repository.fetch_prospect_snapshot()
    if snapshot.demographic_snapshot_count <= 0:
        raise ModelScoreabilityValidationError(
            "Prospect scoring requires at least one demographic row."
        )

    person_ids, raw_features = repository.fetch_scoring_chunk(
        after_person_id=None,
        limit=chunk_limit,
    )
    if not person_ids:
        raise ModelScoreabilityValidationError(
            "Prospect scoring preflight found no demographic rows to score."
        )

    try:
        scores = transform_and_score_prospect_chunk(
            artifact_payload=context.artifact_payload,
            raw_features=raw_features,
        )
    except (FeatureContractError, ValueError, TypeError) as exc:
        raise ModelScoreabilityValidationError(
            "Scoring preflight failed frozen feature compatibility checks."
        ) from exc
    if scores.shape[0] != len(person_ids):
        raise ModelScoreabilityValidationError(
            "Scoring preflight returned an unexpected score count."
        )

    return ScoringPreflightResult(
        model_run_id=context.model_run_id,
        demographic_snapshot_count=snapshot.demographic_snapshot_count,
        demographic_min_person_id=snapshot.demographic_min_person_id,
        demographic_max_person_id=snapshot.demographic_max_person_id,
        preflight_row_count=len(person_ids),
        preflight_first_person_id=person_ids[0],
        preflight_last_person_id=person_ids[-1],
        preflight_score_min=float(np.min(scores)),
        preflight_score_max=float(np.max(scores)),
        preflight_score_mean=float(np.mean(scores)),
    )


__all__ = (
    "ModelScoringCompatibilityError",
    "ModelScoreabilityValidationError",
    "ScoreableModelContext",
    "ScoringPreflightResult",
    "run_scoring_preflight",
    "transform_and_score_prospect_chunk",
    "validate_scoreable_model",
)
