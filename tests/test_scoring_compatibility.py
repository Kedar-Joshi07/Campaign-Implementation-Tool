from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.ml.feature_contract import (
    FEATURE_CONTRACT_JSON,
    FEATURE_CONTRACT_SHA256,
    FEATURE_CONTRACT_VERSION,
    ORDERED_FEATURES,
    FeatureContractError,
)
from app.ml.model_roles import PRIMARY_MODEL_NAME
from app.ml.preprocessing import build_feature_preprocessor
from app.ml.pu_estimators import ELKAN_NOTO_NAME
from app.services import model_scoring_compatibility as compatibility
from app.services.model_scoring_compatibility import ModelScoreabilityValidationError


class _DeterministicEstimator:
    classes_ = np.array([0, 1], dtype=np.int64)

    def predict_proba(self, matrix: Any) -> np.ndarray:
        row_count = int(matrix.shape[0])
        positive = np.linspace(0.2, 0.8, row_count, dtype=np.float64)
        return np.column_stack((1.0 - positive, positive))


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "scoring-compatibility.db"
    initialize_database(path)
    return path


def _insert_completed_analysis(database_path: Path) -> int:
    with get_connection(database_path, write=True) as connection:
        cursor = connection.execute(
            """
            INSERT INTO historical_analysis_runs (
                analysis_name, created_at, completed_at, status,
                conversion_definition, filters_json, results_json,
                observation_count, selected_customer_count,
                positive_customer_count, unlabeled_customer_count,
                positive_customer_rate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Scoring compatibility fixture",
                "2026-08-26T00:00:00Z",
                "2026-08-26T00:00:03Z",
                "COMPLETED",
                "ATTRIBUTED_PURCHASE",
                "{}",
                "{}",
                100,
                20,
                5,
                15,
                0.25,
            ),
        )
        return int(cursor.lastrowid)


def _v2_metrics(selected_candidate: str) -> dict[str, Any]:
    return {
        "evaluation_contract_version": "2",
        "model_role_policy_version": "2",
        "primary_candidate": "BAGGING_PU",
        "challenger_candidates": ["ELKAN_NOTO_LOGISTIC"],
        "diagnostic_controls": ["NAIVE_PU_LABEL_BASELINE"],
        "selection_policy": "PRIMARY_ROLE_GOVERNED",
        "selected_candidate": selected_candidate,
        "quality_flags": ["OBSERVED_LABEL_METRICS_ONLY"],
        "candidate_results": {
            "BAGGING_PU": {
                "name": "BAGGING_PU",
                "candidate_role": "PRIMARY",
                "status": "FITTED",
                "is_genuine_pu": True,
                "top_slice_metrics": {
                    "top_10_percent": {
                        "known_positive_lift_at_k": 1.4,
                        "known_positive_recall_at_k": 0.3,
                    }
                },
                "runtime": {"fit_seconds": 0.2, "scoring_seconds": 0.02},
                "quality_flags": [],
            },
            "ELKAN_NOTO_LOGISTIC": {
                "name": "ELKAN_NOTO_LOGISTIC",
                "candidate_role": "CHALLENGER_1",
                "status": "FITTED",
                "is_genuine_pu": True,
                "top_slice_metrics": {
                    "top_10_percent": {
                        "known_positive_lift_at_k": 1.25,
                        "known_positive_recall_at_k": 0.2,
                    }
                },
                "runtime": {"fit_seconds": 0.1, "scoring_seconds": 0.01},
                "quality_flags": [],
            },
            "NAIVE_PU_LABEL_BASELINE": {
                "name": "NAIVE_PU_LABEL_BASELINE",
                "candidate_role": "DIAGNOSTIC_CONTROL",
                "status": "FITTED",
                "is_genuine_pu": False,
                "top_slice_metrics": {
                    "top_10_percent": {
                        "known_positive_lift_at_k": 1.1,
                        "known_positive_recall_at_k": 0.2,
                    }
                },
                "runtime": {"fit_seconds": 0.05, "scoring_seconds": 0.01},
                "quality_flags": [],
            },
        },
    }


def _insert_model_run(
    database_path: Path,
    *,
    analysis_run_id: int,
    status: str,
    selected_candidate: str | None,
    metrics_json: str | None,
    feature_contract_json: str,
) -> int:
    completed_at = "2026-08-26T00:20:00Z" if status == "COMPLETED" else None
    with get_connection(database_path, write=True) as connection:
        cursor = connection.execute(
            """
            INSERT INTO model_runs (
                analysis_run_id,
                model_name,
                created_at,
                completed_at,
                status,
                algorithm,
                selected_candidate,
                random_seed,
                validation_fraction,
                reconstructed_observation_count,
                selected_customer_count,
                positive_customer_count,
                unlabeled_customer_count,
                train_customer_count,
                validation_customer_count,
                train_positive_count,
                validation_positive_count,
                feature_contract_json,
                preprocessing_json,
                hyperparameters_json,
                metrics_json,
                library_versions_json,
                artifact_path,
                artifact_sha256,
                error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_run_id,
                "Compatibility fixture model",
                "2026-08-26T00:10:00Z",
                completed_at,
                status,
                "pulearn.BaggingPuClassifier" if status == "COMPLETED" else None,
                selected_candidate,
                42,
                0.2,
                100 if status == "COMPLETED" else 0,
                20 if status == "COMPLETED" else 0,
                5 if status == "COMPLETED" else 0,
                15 if status == "COMPLETED" else 0,
                16 if status == "COMPLETED" else 0,
                4 if status == "COMPLETED" else 0,
                4 if status == "COMPLETED" else 0,
                1 if status == "COMPLETED" else 0,
                feature_contract_json,
                "{}" if status == "COMPLETED" else None,
                "{}" if status == "COMPLETED" else None,
                metrics_json,
                "{}" if status == "COMPLETED" else None,
                "artifacts/models/model_run_000123/pu_model.joblib"
                if status == "COMPLETED"
                else None,
                "a" * 64 if status == "COMPLETED" else None,
                None,
            ),
        )
        return int(cursor.lastrowid)


def _insert_demographic_row(database_path: Path, *, person_id: str) -> None:
    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO demographics (
                person_id,
                age,
                gender,
                state,
                individual_yearly_income,
                marital_status,
                education,
                employment_status,
                resident_status,
                resident_type,
                family_member_count,
                number_of_children_in_family,
                number_of_adults_in_family,
                type_of_employment,
                family_yearly_income
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                person_id,
                36,
                "Female",
                "Ohio",
                72_000,
                "Single",
                "Bachelors",
                "Employed",
                "Citizen",
                "Owner",
                2,
                0,
                2,
                "Salaried",
                98_000,
            ),
        )


def _artifact_payload() -> dict[str, Any]:
    training = pd.DataFrame(
        [
            {
                "age": 35,
                "gender": "Female",
                "state": "Ohio",
                "individual_yearly_income": 70_000.0,
                "marital_status": "Single",
                "education": "Bachelors",
                "employment_status": "Employed",
                "resident_status": "Citizen",
                "resident_type": "Owner",
                "family_member_count": 2,
                "type_of_employment": "Salaried",
            },
            {
                "age": 44,
                "gender": "Male",
                "state": "Texas",
                "individual_yearly_income": 95_000.0,
                "marital_status": "Married",
                "education": "Masters",
                "employment_status": "Employed",
                "resident_status": "Citizen",
                "resident_type": "Renter",
                "family_member_count": 3,
                "type_of_employment": "Hourly",
            },
        ],
        columns=ORDERED_FEATURES,
    )
    preprocessor = build_feature_preprocessor()
    preprocessor.fit(training, np.array([1, 0], dtype=np.int8))
    return {
        "artifact_version": "1",
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "feature_contract_sha256": FEATURE_CONTRACT_SHA256,
        "raw_feature_order": list(ORDERED_FEATURES),
        "preprocessor": preprocessor,
        "estimator": _DeterministicEstimator(),
        "selected_candidate": PRIMARY_MODEL_NAME,
    }


def test_scoreable_bagging_model_passes_preflight(database_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    model_run_id = _insert_model_run(
        database_path,
        analysis_run_id=analysis_run_id,
        status="COMPLETED",
        selected_candidate=PRIMARY_MODEL_NAME,
        metrics_json=json.dumps(_v2_metrics(PRIMARY_MODEL_NAME), sort_keys=True),
        feature_contract_json=FEATURE_CONTRACT_JSON,
    )
    _insert_demographic_row(database_path, person_id="PER_001")
    _insert_demographic_row(database_path, person_id="PER_002")
    _insert_demographic_row(database_path, person_id="PER_003")

    monkeypatch.setattr(
        compatibility,
        "load_verified_model_artifact",
        lambda *_args, **_kwargs: _artifact_payload(),
    )

    result = compatibility.run_scoring_preflight(
        database_path,
        model_run_id,
        chunk_limit=2,
    )

    assert result.model_run_id == model_run_id
    assert result.demographic_snapshot_count == 3
    assert result.preflight_row_count == 2
    assert result.preflight_first_person_id == "PER_001"
    assert result.preflight_last_person_id == "PER_002"
    assert 0.0 <= result.preflight_score_min <= result.preflight_score_max <= 1.0


def test_non_scoreable_models_fail_before_snapshot_scan(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)

    def _expect_no_scan(run_id: int) -> None:
        scanned = False

        def _snapshot_unexpected(_self: Any) -> Any:
            nonlocal scanned
            scanned = True
            raise AssertionError("snapshot scan should not happen")

        monkeypatch.setattr(
            compatibility.ProspectScoringRepository,
            "fetch_prospect_snapshot",
            _snapshot_unexpected,
        )
        with pytest.raises(ModelScoreabilityValidationError):
            compatibility.run_scoring_preflight(database_path, run_id)
        assert scanned is False

    running_model = _insert_model_run(
        database_path,
        analysis_run_id=analysis_run_id,
        status="RUNNING",
        selected_candidate=None,
        metrics_json=None,
        feature_contract_json=FEATURE_CONTRACT_JSON,
    )
    _expect_no_scan(running_model)

    legacy_model = _insert_model_run(
        database_path,
        analysis_run_id=analysis_run_id,
        status="COMPLETED",
        selected_candidate=PRIMARY_MODEL_NAME,
        metrics_json=json.dumps({"selected_candidate": PRIMARY_MODEL_NAME}, sort_keys=True),
        feature_contract_json=FEATURE_CONTRACT_JSON,
    )
    monkeypatch.setattr(
        compatibility,
        "load_verified_model_artifact",
        lambda *_args, **_kwargs: _artifact_payload(),
    )
    _expect_no_scan(legacy_model)

    wrong_candidate_model = _insert_model_run(
        database_path,
        analysis_run_id=analysis_run_id,
        status="COMPLETED",
        selected_candidate=ELKAN_NOTO_NAME,
        metrics_json=json.dumps(_v2_metrics(ELKAN_NOTO_NAME), sort_keys=True),
        feature_contract_json=FEATURE_CONTRACT_JSON,
    )
    _expect_no_scan(wrong_candidate_model)

    contract_mismatch_model = _insert_model_run(
        database_path,
        analysis_run_id=analysis_run_id,
        status="COMPLETED",
        selected_candidate=PRIMARY_MODEL_NAME,
        metrics_json=json.dumps(_v2_metrics(PRIMARY_MODEL_NAME), sort_keys=True),
        feature_contract_json=json.dumps({"version": "legacy"}, sort_keys=True),
    )
    _expect_no_scan(contract_mismatch_model)

    artifact_failure_model = _insert_model_run(
        database_path,
        analysis_run_id=analysis_run_id,
        status="COMPLETED",
        selected_candidate=PRIMARY_MODEL_NAME,
        metrics_json=json.dumps(_v2_metrics(PRIMARY_MODEL_NAME), sort_keys=True),
        feature_contract_json=FEATURE_CONTRACT_JSON,
    )
    monkeypatch.setattr(
        compatibility,
        "load_verified_model_artifact",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("artifact failed")),
    )
    _expect_no_scan(artifact_failure_model)


def test_preflight_fails_when_demographic_population_is_empty(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    model_run_id = _insert_model_run(
        database_path,
        analysis_run_id=analysis_run_id,
        status="COMPLETED",
        selected_candidate=PRIMARY_MODEL_NAME,
        metrics_json=json.dumps(_v2_metrics(PRIMARY_MODEL_NAME), sort_keys=True),
        feature_contract_json=FEATURE_CONTRACT_JSON,
    )
    monkeypatch.setattr(
        compatibility,
        "load_verified_model_artifact",
        lambda *_args, **_kwargs: _artifact_payload(),
    )

    with pytest.raises(ModelScoreabilityValidationError, match="at least one demographic row"):
        compatibility.run_scoring_preflight(database_path, model_run_id)


@pytest.mark.parametrize(
    ("column", "value"),
    (
        ("age", 17),
        ("individual_yearly_income", -1.0),
        ("family_member_count", 0),
    ),
)
def test_transform_and_score_rejects_invalid_frozen_numeric_values(
    column: str,
    value: int | float,
) -> None:
    frame = pd.DataFrame(
        [
            {
                "age": 35,
                "gender": "Female",
                "state": "Ohio",
                "individual_yearly_income": 70_000.0,
                "marital_status": "Single",
                "education": "Bachelors",
                "employment_status": "Employed",
                "resident_status": "Citizen",
                "resident_type": "Owner",
                "family_member_count": 2,
                "type_of_employment": "Salaried",
            }
        ],
        columns=ORDERED_FEATURES,
    )
    frame.loc[0, column] = value

    with pytest.raises(FeatureContractError):
        compatibility.transform_and_score_prospect_chunk(
            artifact_payload=_artifact_payload(),
            raw_features=frame,
        )


def test_transform_and_score_supports_unknown_categories() -> None:
    frame = pd.DataFrame(
        [
            {
                "age": 41,
                "gender": "Non-Binary",
                "state": "Atlantis",
                "individual_yearly_income": 88_000.0,
                "marital_status": "Complicated",
                "education": "Doctorate",
                "employment_status": "Contractor",
                "resident_status": "Unknown",
                "resident_type": "Floating",
                "family_member_count": 3,
                "type_of_employment": "Gig",
            }
        ],
        columns=ORDERED_FEATURES,
    )

    scores = compatibility.transform_and_score_prospect_chunk(
        artifact_payload=_artifact_payload(),
        raw_features=frame,
    )

    assert scores.shape == (1,)
    assert float(scores[0]) == pytest.approx(0.2)
