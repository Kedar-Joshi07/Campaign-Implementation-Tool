from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories.scoring_repository import (
    SCORING_STATUS_COMPLETED,
    SCORING_STATUS_FAILED,
    SCORING_STATUS_RUNNING,
    ScoringRepository,
    ScoringStateTransitionError,
    ScoringValidationError,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "scoring-repository.db"
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
                "Scoring repository fixture",
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
                "Scoring model fixture",
                "2026-08-26T00:00:05Z",
                "RUNNING",
                42,
                0.2,
            ),
        )
        return int(cursor.lastrowid)


def _insert_scoring_job(database_path: Path, *, model_run_id: int, created_at: str) -> int:
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
                created_at,
                created_at,
                None,
                "{}",
                None,
                None,
            ),
        )
        return int(cursor.lastrowid)


def _insert_demographic(database_path: Path, *, person_id: str) -> None:
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
                70_000.0,
                "Single",
                "Bachelors",
                "Employed",
                "Citizen",
                "Owner",
                2,
                0,
                2,
                "Salaried",
                95_000.0,
            ),
        )


def test_create_fetch_list_and_finders(database_path: Path) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    job_id = _insert_scoring_job(
        database_path,
        model_run_id=model_run_id,
        created_at="2026-08-26T01:00:00Z",
    )

    repository = ScoringRepository(database_path)
    scoring_run_id = repository.create_scoring_run(
        job_id=job_id,
        model_run_id=model_run_id,
        created_at="2026-08-26T01:00:10Z",
        demographic_snapshot_count=5,
        demographic_min_person_id="PER_001",
        demographic_max_person_id="PER_005",
        chunk_size=10_000,
        selected_candidate="BAGGING_PU",
        model_role_policy_version="2",
        feature_contract_version="1",
        feature_contract_sha256="a" * 64,
        artifact_sha256="b" * 64,
    )

    fetched = repository.fetch_scoring_run(scoring_run_id)
    assert fetched is not None
    assert fetched["status"] == SCORING_STATUS_RUNNING
    assert fetched["job_id"] == job_id
    assert fetched["model_run_id"] == model_run_id
    assert fetched["scored_person_count"] == 0
    assert fetched["selected_candidate"] == "BAGGING_PU"

    by_job = repository.fetch_by_job_id(job_id)
    assert by_job is not None
    assert by_job["scoring_run_id"] == scoring_run_id

    runs = repository.list_scoring_runs(limit=10, offset=0)
    assert len(runs) == 1
    assert runs[0]["scoring_run_id"] == scoring_run_id

    running = repository.find_running_run_for_model(model_run_id)
    assert running is not None
    assert running["scoring_run_id"] == scoring_run_id

    completed = repository.find_completed_run_for_model(model_run_id)
    assert completed is None


def test_update_counters_and_mark_completed(database_path: Path) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    job_id = _insert_scoring_job(
        database_path,
        model_run_id=model_run_id,
        created_at="2026-08-26T02:00:00Z",
    )

    repository = ScoringRepository(database_path)
    scoring_run_id = repository.create_scoring_run(
        job_id=job_id,
        model_run_id=model_run_id,
        created_at="2026-08-26T02:00:10Z",
        demographic_snapshot_count=10,
        demographic_min_person_id="PER_001",
        demographic_max_person_id="PER_010",
        chunk_size=10_000,
        selected_candidate="BAGGING_PU",
        model_role_policy_version="2",
        feature_contract_version="1",
        feature_contract_sha256="c" * 64,
        artifact_sha256="d" * 64,
    )

    repository.update_counters(
        scoring_run_id=scoring_run_id,
        scored_person_count=6,
        last_person_id="PER_006",
        score_min=0.10,
        score_max=0.90,
        score_mean=0.45,
    )

    repository.mark_completed(
        scoring_run_id=scoring_run_id,
        completed_at="2026-08-26T02:00:30Z",
        scored_person_count=10,
        score_min=0.10,
        score_max=0.90,
        score_mean=0.50,
        summary_payload={"rows": 10, "checksum": "ok"},
    )

    fetched = repository.fetch_scoring_run(scoring_run_id)
    assert fetched is not None
    assert fetched["status"] == SCORING_STATUS_COMPLETED
    assert fetched["completed_at"] == "2026-08-26T02:00:30Z"
    assert fetched["scored_person_count"] == 10
    assert fetched["error_message"] is None
    assert json.loads(fetched["score_summary_json"]) == {"checksum": "ok", "rows": 10}

    completed = repository.find_completed_run_for_model(model_run_id)
    assert completed is not None
    assert completed["scoring_run_id"] == scoring_run_id


def test_transition_guards_and_validation_errors(database_path: Path) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    job_id = _insert_scoring_job(
        database_path,
        model_run_id=model_run_id,
        created_at="2026-08-26T03:00:00Z",
    )

    repository = ScoringRepository(database_path)
    scoring_run_id = repository.create_scoring_run(
        job_id=job_id,
        model_run_id=model_run_id,
        created_at="2026-08-26T03:00:10Z",
        demographic_snapshot_count=4,
        demographic_min_person_id="PER_001",
        demographic_max_person_id="PER_004",
        chunk_size=10_000,
        selected_candidate="BAGGING_PU",
        model_role_policy_version="2",
        feature_contract_version="1",
        feature_contract_sha256="e" * 64,
        artifact_sha256="f" * 64,
    )

    with pytest.raises(ScoringValidationError):
        repository.create_scoring_run(
            job_id=job_id,
            model_run_id=model_run_id,
            created_at="2026-08-26T03:00:11Z",
            demographic_snapshot_count=4,
            demographic_min_person_id="PER_001",
            demographic_max_person_id="PER_004",
            chunk_size=10_000,
            selected_candidate="BAGGING_PU",
            model_role_policy_version="2",
            feature_contract_version="1",
            feature_contract_sha256="invalid-hash",
            artifact_sha256="f" * 64,
        )

    repository.update_counters(
        scoring_run_id=scoring_run_id,
        scored_person_count=2,
        last_person_id="PER_002",
        score_min=0.20,
        score_max=0.70,
        score_mean=0.40,
    )

    with pytest.raises(ScoringStateTransitionError, match="monotonic"):
        repository.update_counters(
            scoring_run_id=scoring_run_id,
            scored_person_count=1,
            last_person_id="PER_001",
            score_min=0.20,
            score_max=0.70,
            score_mean=0.40,
        )

    repository.mark_failed(
        scoring_run_id=scoring_run_id,
        completed_at="2026-08-26T03:00:30Z",
        error_message="simulated scoring fault",
        summary_payload={"chunk": 1},
    )

    failed = repository.fetch_scoring_run(scoring_run_id)
    assert failed is not None
    assert failed["status"] == SCORING_STATUS_FAILED
    assert failed["error_message"] == "simulated scoring fault"

    with pytest.raises(ScoringStateTransitionError):
        repository.mark_completed(
            scoring_run_id=scoring_run_id,
            completed_at="2026-08-26T03:00:40Z",
            scored_person_count=4,
            score_min=0.20,
            score_max=0.70,
            score_mean=0.40,
            summary_payload={"rows": 4},
        )


def test_mark_completed_requires_non_empty_summary_payload(database_path: Path) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    job_id = _insert_scoring_job(
        database_path,
        model_run_id=model_run_id,
        created_at="2026-08-26T03:30:00Z",
    )

    repository = ScoringRepository(database_path)
    scoring_run_id = repository.create_scoring_run(
        job_id=job_id,
        model_run_id=model_run_id,
        created_at="2026-08-26T03:30:10Z",
        demographic_snapshot_count=1,
        demographic_min_person_id="PER_001",
        demographic_max_person_id="PER_001",
        chunk_size=10_000,
        selected_candidate="BAGGING_PU",
        model_role_policy_version="2",
        feature_contract_version="1",
        feature_contract_sha256="a" * 64,
        artifact_sha256="b" * 64,
    )

    repository.update_counters(
        scoring_run_id=scoring_run_id,
        scored_person_count=1,
        last_person_id="PER_001",
        score_min=0.5,
        score_max=0.5,
        score_mean=0.5,
    )

    with pytest.raises(ScoringValidationError, match="non-empty"):
        repository.mark_completed(
            scoring_run_id=scoring_run_id,
            completed_at="2026-08-26T03:30:20Z",
            scored_person_count=1,
            score_min=0.5,
            score_max=0.5,
            score_mean=0.5,
            summary_payload=None,
        )


def test_insert_scores_chunk_and_fetch_aggregates(database_path: Path) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    job_id = _insert_scoring_job(
        database_path,
        model_run_id=model_run_id,
        created_at="2026-08-26T04:00:00Z",
    )
    _insert_demographic(database_path, person_id="PER_001")
    _insert_demographic(database_path, person_id="PER_002")
    _insert_demographic(database_path, person_id="PER_003")

    repository = ScoringRepository(database_path)
    scoring_run_id = repository.create_scoring_run(
        job_id=job_id,
        model_run_id=model_run_id,
        created_at="2026-08-26T04:00:10Z",
        demographic_snapshot_count=3,
        demographic_min_person_id="PER_001",
        demographic_max_person_id="PER_003",
        chunk_size=10_000,
        selected_candidate="BAGGING_PU",
        model_role_policy_version="2",
        feature_contract_version="1",
        feature_contract_sha256="a" * 64,
        artifact_sha256="b" * 64,
    )

    inserted = repository.insert_scores_chunk(
        scoring_run_id=scoring_run_id,
        model_run_id=model_run_id,
        person_ids=["PER_001", "PER_002"],
        propensity_scores=[0.2, 0.6],
    )
    assert inserted == 2

    repository.insert_scores_chunk(
        scoring_run_id=scoring_run_id,
        model_run_id=model_run_id,
        person_ids=["PER_003"],
        propensity_scores=[0.9],
    )

    aggregates = repository.fetch_score_aggregates(scoring_run_id)
    assert aggregates["score_count"] == 3
    assert aggregates["distinct_person_count"] == 3
    assert aggregates["min_person_id"] == "PER_001"
    assert aggregates["max_person_id"] == "PER_003"
    assert aggregates["score_min"] == pytest.approx(0.2)
    assert aggregates["score_max"] == pytest.approx(0.9)
    assert aggregates["score_mean"] == pytest.approx((0.2 + 0.6 + 0.9) / 3)

    sample = repository.fetch_score_sample(scoring_run_id=scoring_run_id, limit=2)
    assert [row["person_id"] for row in sample] == ["PER_001", "PER_002"]
