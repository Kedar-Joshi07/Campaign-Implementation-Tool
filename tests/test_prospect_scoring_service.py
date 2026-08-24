from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.ml.feature_contract import FEATURE_CONTRACT_SHA256
from app.services import prospect_scoring_service as scoring_service
from app.services.model_scoring_compatibility import ScoreableModelContext
from app.services.model_scoring_compatibility import ModelScoreabilityValidationError
from app.services.prospect_scoring_service import (
    ProspectScoringExecutionError,
    ProspectScoringVerificationError,
)


class _TrackingPreprocessor:
    def __init__(self, *, fail_transform_on_call: int | None = None) -> None:
        self.transform_calls = 0
        self.fit_calls = 0
        self.fit_transform_calls = 0
        self._fail_transform_on_call = fail_transform_on_call

    def fit(self, *_args: Any, **_kwargs: Any) -> _TrackingPreprocessor:
        self.fit_calls += 1
        raise AssertionError("fit should not be called during scoring")

    def fit_transform(self, *_args: Any, **_kwargs: Any) -> Any:
        self.fit_transform_calls += 1
        raise AssertionError("fit_transform should not be called during scoring")

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        self.transform_calls += 1
        if self._fail_transform_on_call == self.transform_calls:
            raise RuntimeError("forced transform failure")
        return frame.loc[:, ["age", "individual_yearly_income", "family_member_count"]].to_numpy(
            dtype=np.float64
        )


class _TrackingEstimator:
    classes_ = np.array([0, 1], dtype=np.int64)

    def __init__(self, *, fail_on_call: int | None = None) -> None:
        self.predict_calls = 0
        self._fail_on_call = fail_on_call

    def predict_proba(self, matrix: Any) -> np.ndarray:
        self.predict_calls += 1
        if self._fail_on_call == self.predict_calls:
            raise RuntimeError("forced estimator failure")
        values = np.asarray(matrix, dtype=np.float64)
        positive = np.clip(values[:, 0] / 100.0, 0.0, 1.0)
        return np.column_stack((1.0 - positive, positive))


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "prospect-scoring-service.db"
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
                "Scoring service fixture",
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


def _insert_model_run(database_path: Path, analysis_run_id: int) -> int:
    with get_connection(database_path, write=True) as connection:
        cursor = connection.execute(
            """
            INSERT INTO model_runs (
                analysis_run_id,
                model_name,
                created_at,
                status,
                random_seed,
                validation_fraction
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_run_id,
                "Prospect scoring fixture model",
                "2026-08-26T00:10:00Z",
                "RUNNING",
                42,
                0.2,
            ),
        )
        return int(cursor.lastrowid)


def _insert_scoring_job(database_path: Path, *, model_run_id: int) -> int:
    with get_connection(database_path, write=True) as connection:
        cursor = connection.execute(
            """
            INSERT INTO jobs (
                job_type,
                status,
                progress_percent,
                stage,
                analysis_run_id,
                model_run_id,
                created_at,
                started_at,
                finished_at,
                request_json,
                result_json,
                error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "PROSPECT_SCORING",
                "RUNNING",
                1,
                "VALIDATING_MODEL",
                None,
                model_run_id,
                "2026-08-26T01:00:00Z",
                "2026-08-26T01:00:00Z",
                None,
                "{}",
                None,
                None,
            ),
        )
        return int(cursor.lastrowid)


def _insert_demographic(
    database_path: Path,
    *,
    person_id: str,
    age: int,
    income: float,
    family_member_count: int,
    state: str,
) -> None:
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
                age,
                "Female",
                state,
                income,
                "Single",
                "Bachelors",
                "Employed",
                "Citizen",
                "Owner",
                family_member_count,
                0,
                max(family_member_count - 1, 1),
                "Salaried",
                float(income * 1.2),
            ),
        )


def _seed_demographics(database_path: Path, count: int) -> None:
    rows: list[tuple[Any, ...]] = []
    for index in range(count):
        person_id = f"PER_{index + 1:06d}"
        age = 21 + (index % 70)
        income = 50_000.0 + (index * 10)
        family_member_count = 1 + (index % 3)
        state = "Ohio" if index % 2 == 0 else "Texas"
        rows.append(
            (
                person_id,
                age,
                "Female",
                state,
                income,
                "Single",
                "Bachelors",
                "Employed",
                "Citizen",
                "Owner",
                family_member_count,
                0,
                max(family_member_count - 1, 1),
                "Salaried",
                float(income * 1.2),
            )
        )

    with get_connection(database_path, write=True) as connection:
        connection.executemany(
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
            rows,
        )


def _scoreable_context(*, model_run_id: int, preprocessor: Any, estimator: Any) -> ScoreableModelContext:
    return ScoreableModelContext(
        model_run_id=model_run_id,
        selected_candidate="BAGGING_PU",
        model_role_policy_version="2",
        evaluation_contract_version="2",
        feature_contract_version="1",
        feature_contract_sha256=FEATURE_CONTRACT_SHA256,
        artifact_sha256="a" * 64,
        artifact_payload={
            "selected_candidate": "BAGGING_PU",
            "preprocessor": preprocessor,
            "estimator": estimator,
        },
    )


def test_chunked_scoring_persists_all_scores_and_completes(database_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    job_id = _insert_scoring_job(database_path, model_run_id=model_run_id)
    _seed_demographics(database_path, 5)

    preprocessor = _TrackingPreprocessor()
    estimator = _TrackingEstimator()
    monkeypatch.setattr(
        scoring_service,
        "validate_scoreable_model",
        lambda *_args, **_kwargs: _scoreable_context(
            model_run_id=model_run_id,
            preprocessor=preprocessor,
            estimator=estimator,
        ),
    )

    events: list[tuple[str, int, int | None]] = []

    def _progress(stage: str, progress: int, _message: str | None, scoring_run_id: int | None) -> None:
        events.append((stage, progress, scoring_run_id))

    result = scoring_service.run_chunked_prospect_scoring(
        database_path,
        model_run_id=model_run_id,
        job_id=job_id,
        chunk_size=2_000,
        progress_callback=_progress,
    )

    assert result["scored_person_count"] == 5
    assert result["summary"]["chunk_count"] == 1
    assert result["summary"]["score_count"] == 5
    assert result["summary"]["score_min"] <= result["summary"]["score_mean"] <= result["summary"]["score_max"]

    with get_connection(database_path) as connection:
        run = connection.execute(
            "SELECT * FROM scoring_runs WHERE scoring_run_id = ?",
            (result["scoring_run_id"],),
        ).fetchone()
        rows = connection.execute(
            "SELECT person_id, propensity_score FROM propensity_scores WHERE scoring_run_id = ? ORDER BY person_id",
            (result["scoring_run_id"],),
        ).fetchall()

    assert run["status"] == "COMPLETED"
    assert run["scored_person_count"] == 5
    assert run["last_person_id"] == "PER_000005"
    assert [row["person_id"] for row in rows] == [
        "PER_000001",
        "PER_000002",
        "PER_000003",
        "PER_000004",
        "PER_000005",
    ]
    assert all(0.0 <= float(row["propensity_score"]) <= 1.0 for row in rows)

    summary_payload = json.loads(run["score_summary_json"])
    assert summary_payload["score_count"] == 5
    assert summary_payload["age_semantics_note"]
    assert "person_id" not in summary_payload
    assert np.isfinite(summary_payload["score_min"])
    assert np.isfinite(summary_payload["score_max"])
    assert np.isfinite(summary_payload["score_mean"])
    assert preprocessor.fit_calls == 0
    assert preprocessor.fit_transform_calls == 0
    assert preprocessor.transform_calls >= 1

    stages = [stage for stage, _progress, _id in events]
    assert stages[0] == "VALIDATING_MODEL"
    assert stages[-1] == "COMPLETED"
    assert len(set((stage, progress) for stage, progress, _id in events)) == len(events)


def test_multiple_chunks_final_partial_and_verification_helper(database_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    job_id = _insert_scoring_job(database_path, model_run_id=model_run_id)
    _seed_demographics(database_path, 2505)

    preprocessor = _TrackingPreprocessor()
    estimator = _TrackingEstimator()
    monkeypatch.setattr(
        scoring_service,
        "validate_scoreable_model",
        lambda *_args, **_kwargs: _scoreable_context(
            model_run_id=model_run_id,
            preprocessor=preprocessor,
            estimator=estimator,
        ),
    )

    result = scoring_service.run_chunked_prospect_scoring(
        database_path,
        model_run_id=model_run_id,
        job_id=job_id,
        chunk_size=1_000,
    )

    summary = result["summary"]
    assert summary["chunk_count"] == 3
    assert summary["largest_chunk_rows"] == 1000
    verification = scoring_service.verify_scoring_run_sample(
        database_path,
        scoring_run_id=result["scoring_run_id"],
        sample_size=3,
    )
    assert verification["verified"] is True
    assert verification["sample_size"] == 3

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            UPDATE propensity_scores
            SET propensity_score = propensity_score + 0.05
            WHERE scoring_run_id = ? AND person_id = ?
            """,
            (result["scoring_run_id"], "PER_000001"),
        )

    with pytest.raises(ProspectScoringVerificationError):
        scoring_service.verify_scoring_run_sample(
            database_path,
            scoring_run_id=result["scoring_run_id"],
            sample_size=3,
        )


@pytest.mark.parametrize(
    "mode",
    ["transform", "estimator", "write"],
)
def test_scoring_failures_mark_run_failed_and_isolate_partial_rows(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    job_id = _insert_scoring_job(database_path, model_run_id=model_run_id)
    _seed_demographics(database_path, 1500)

    preprocessor = _TrackingPreprocessor(fail_transform_on_call=2 if mode == "transform" else None)
    estimator = _TrackingEstimator(fail_on_call=2 if mode == "estimator" else None)
    monkeypatch.setattr(
        scoring_service,
        "validate_scoreable_model",
        lambda *_args, **_kwargs: _scoreable_context(
            model_run_id=model_run_id,
            preprocessor=preprocessor,
            estimator=estimator,
        ),
    )

    if mode == "write":
        original_insert = scoring_service.ScoringRepository.insert_scores_chunk
        call_count = 0

        def _fail_on_second_insert(self: Any, **kwargs: Any) -> int:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("forced write failure")
            return original_insert(self, **kwargs)

        monkeypatch.setattr(
            scoring_service.ScoringRepository,
            "insert_scores_chunk",
            _fail_on_second_insert,
        )

    with pytest.raises(ProspectScoringExecutionError):
        scoring_service.run_chunked_prospect_scoring(
            database_path,
            model_run_id=model_run_id,
            job_id=job_id,
            chunk_size=1_000,
        )

    with get_connection(database_path) as connection:
        run = connection.execute(
            "SELECT * FROM scoring_runs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        persisted_count = connection.execute(
            "SELECT COUNT(*) FROM propensity_scores WHERE scoring_run_id = ?",
            (run["scoring_run_id"],),
        ).fetchone()[0]

    assert run["status"] == "FAILED"
    assert 0 < persisted_count < 1500
    assert run["error_message"] is not None


def test_zero_population_rejected_before_scoring_run_creation(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    job_id = _insert_scoring_job(database_path, model_run_id=model_run_id)

    monkeypatch.setattr(
        scoring_service,
        "validate_scoreable_model",
        lambda *_args, **_kwargs: _scoreable_context(
            model_run_id=model_run_id,
            preprocessor=_TrackingPreprocessor(),
            estimator=_TrackingEstimator(),
        ),
    )

    with pytest.raises(ModelScoreabilityValidationError, match="at least one demographic row"):
        scoring_service.run_chunked_prospect_scoring(
            database_path,
            model_run_id=model_run_id,
            job_id=job_id,
            chunk_size=1_000,
        )

    with get_connection(database_path) as connection:
        row = connection.execute(
            "SELECT 1 FROM scoring_runs WHERE job_id = ?",
            (job_id,),
        ).fetchone()

    assert row is None


def test_snapshot_drift_detected_at_completion(database_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    job_id = _insert_scoring_job(database_path, model_run_id=model_run_id)
    _seed_demographics(database_path, 4)

    preprocessor = _TrackingPreprocessor()
    estimator = _TrackingEstimator()
    monkeypatch.setattr(
        scoring_service,
        "validate_scoreable_model",
        lambda *_args, **_kwargs: _scoreable_context(
            model_run_id=model_run_id,
            preprocessor=preprocessor,
            estimator=estimator,
        ),
    )

    original_snapshot = scoring_service.ProspectScoringRepository.fetch_prospect_snapshot
    call_count = 0

    def _drifting_snapshot(self: Any) -> Any:
        nonlocal call_count
        call_count += 1
        snapshot = original_snapshot(self)
        if call_count >= 2:
            return type(snapshot)(
                demographic_snapshot_count=snapshot.demographic_snapshot_count + 1,
                demographic_min_person_id=snapshot.demographic_min_person_id,
                demographic_max_person_id=snapshot.demographic_max_person_id,
            )
        return snapshot

    monkeypatch.setattr(
        scoring_service.ProspectScoringRepository,
        "fetch_prospect_snapshot",
        _drifting_snapshot,
    )

    with pytest.raises(ProspectScoringExecutionError):
        scoring_service.run_chunked_prospect_scoring(
            database_path,
            model_run_id=model_run_id,
            job_id=job_id,
            chunk_size=1_000,
        )

    with get_connection(database_path) as connection:
        run = connection.execute(
            "SELECT * FROM scoring_runs WHERE job_id = ?",
            (job_id,),
        ).fetchone()

    assert run["status"] == "FAILED"
