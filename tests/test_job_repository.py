from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.repositories.job_repository import (
    ActiveTrainingJobConflictError,
    JOB_STAGE_COMPLETED,
    JOB_STAGE_FAILED,
    JOB_STAGE_PREPROCESSING,
    JOB_STAGE_QUEUED,
    JOB_STAGE_STARTING,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    JOB_TYPE_MODEL_TRAINING,
    JobRepository,
    JobStateTransitionError,
    JobValidationError,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "jobs-repository.db"
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
                "Job repository fixture",
                "2026-08-21T00:00:00Z",
                "2026-08-21T00:00:02Z",
                "COMPLETED",
                "ATTRIBUTED_PURCHASE",
                "{}",
                "{}",
                10,
                3,
                1,
                2,
                0.333333,
            ),
        )
        return int(cursor.lastrowid)


def _insert_running_model_run(database_path: Path, analysis_run_id: int) -> int:
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
                "Model run fixture",
                "2026-08-21T00:10:00Z",
                "RUNNING",
                42,
                0.2,
            ),
        )
        return int(cursor.lastrowid)


def test_create_and_fetch_training_job_persists_canonical_request(database_path: Path) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    repository = JobRepository(database_path)

    job_id = repository.create_training_job(
        created_at="2026-08-21T01:00:00Z",
        request_payload={
            "analysis_run_id": analysis_run_id,
            "model_name": "  Phase 4 Candidate  ",
            "random_seed": 7,
            "validation_fraction": 0.25,
            "run_elkan_challenger": False,
        },
        message="  queued for execution  ",
    )
    row = repository.fetch_job(job_id)

    assert row is not None
    assert row["job_type"] == JOB_TYPE_MODEL_TRAINING
    assert row["status"] == JOB_STATUS_QUEUED
    assert row["progress_percent"] == 0
    assert row["stage"] == JOB_STAGE_QUEUED
    assert row["analysis_run_id"] == analysis_run_id
    assert row["model_run_id"] is None
    assert row["message"] == "queued for execution"
    assert row["started_at"] is None
    assert row["finished_at"] is None
    assert row["result_json"] is None
    assert row["error_message"] is None

    request_payload = json.loads(row["request_json"])
    assert request_payload == {
        "analysis_run_id": analysis_run_id,
        "model_name": "Phase 4 Candidate",
        "random_seed": 7,
        "run_elkan_challenger": False,
        "validation_fraction": 0.25,
    }


def test_one_active_job_rule_and_active_detection(database_path: Path) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    repository = JobRepository(database_path)

    job_id = repository.create_training_job(
        created_at="2026-08-21T01:00:00Z",
        request_payload={"analysis_run_id": analysis_run_id},
    )
    active = repository.find_active_training_job()
    assert active is not None
    assert active["job_id"] == job_id
    assert active["status"] == JOB_STATUS_QUEUED

    with pytest.raises(ActiveTrainingJobConflictError):
        repository.create_training_job(
            created_at="2026-08-21T01:00:01Z",
            request_payload={"analysis_run_id": analysis_run_id},
        )

    repository.mark_failed(
        job_id=job_id,
        finished_at="2026-08-21T01:00:10Z",
        error_message="stopped for fixture reset",
    )

    next_job_id = repository.create_training_job(
        created_at="2026-08-21T01:00:11Z",
        request_payload={"analysis_run_id": analysis_run_id},
    )
    repository.mark_running(
        job_id=next_job_id,
        started_at="2026-08-21T01:00:12Z",
        stage=JOB_STAGE_STARTING,
        progress_percent=1,
    )
    active_running = repository.find_active_training_job()
    assert active_running is not None
    assert active_running["job_id"] == next_job_id
    assert active_running["status"] == JOB_STATUS_RUNNING


def test_find_active_job_returns_newest_when_multiple_exist(database_path: Path) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    repository = JobRepository(database_path)

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO jobs (
                job_type, status, progress_percent, stage,
                analysis_run_id, created_at, request_json
            ) VALUES (?, 'QUEUED', 0, 'QUEUED', ?, ?, ?)
            """,
            (
                JOB_TYPE_MODEL_TRAINING,
                analysis_run_id,
                "2026-08-21T01:00:00Z",
                '{"analysis_run_id":1,"model_name":null,"random_seed":42,'
                '"run_elkan_challenger":true,"validation_fraction":0.2}',
            ),
        )
        connection.execute(
            """
            INSERT INTO jobs (
                job_type, status, progress_percent, stage,
                analysis_run_id, created_at, request_json
            ) VALUES (?, 'RUNNING', 25, 'PREPROCESSING', ?, ?, ?)
            """,
            (
                JOB_TYPE_MODEL_TRAINING,
                analysis_run_id,
                "2026-08-21T01:00:01Z",
                '{"analysis_run_id":1,"model_name":null,"random_seed":42,'
                '"run_elkan_challenger":true,"validation_fraction":0.2}',
            ),
        )

    active = repository.find_active_training_job()
    assert active is not None
    assert active["status"] == JOB_STATUS_RUNNING
    assert active["created_at"] == "2026-08-21T01:00:01Z"


def test_guarded_progress_and_terminal_state_transitions(database_path: Path) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    repository = JobRepository(database_path)
    job_id = repository.create_training_job(
        created_at="2026-08-21T01:00:00Z",
        request_payload={"analysis_run_id": analysis_run_id},
    )

    with pytest.raises(JobStateTransitionError):
        repository.update_progress(
            job_id=job_id,
            progress_percent=5,
            stage=JOB_STAGE_PREPROCESSING,
        )

    repository.mark_running(
        job_id=job_id,
        started_at="2026-08-21T01:00:01Z",
        stage=JOB_STAGE_STARTING,
        progress_percent=1,
    )
    repository.update_progress(
        job_id=job_id,
        progress_percent=40,
        stage=JOB_STAGE_PREPROCESSING,
        message="preprocessor fit complete",
    )

    with pytest.raises(JobStateTransitionError):
        repository.update_progress(
            job_id=job_id,
            progress_percent=39,
            stage=JOB_STAGE_PREPROCESSING,
        )

    with pytest.raises(JobValidationError):
        repository.update_progress(
            job_id=job_id,
            progress_percent=100,
            stage=JOB_STAGE_PREPROCESSING,
        )

    model_run_id = _insert_running_model_run(database_path, analysis_run_id)
    repository.mark_completed(
        job_id=job_id,
        finished_at="2026-08-21T01:00:05Z",
        model_run_id=model_run_id,
        message="done",
        result_payload={
            "selected_candidate": "BAGGING_PU",
            "selection_policy": "PRIMARY_ROLE_GOVERNED",
            "quality_flags": ["OBSERVED_LABEL_METRICS_ONLY"],
            "challenger_advisory_flags": ["CHALLENGER_OUTPERFORMED_PRIMARY"],
            "artifact_sha256": "a" * 64,
            "model_role_policy_version": "2",
            "evaluation_contract_version": "2",
        },
    )

    completed = repository.fetch_job(job_id)
    assert completed is not None
    assert completed["status"] == JOB_STATUS_COMPLETED
    assert completed["progress_percent"] == 100
    assert completed["stage"] == JOB_STAGE_COMPLETED
    assert completed["message"] == "done"
    assert completed["finished_at"] == "2026-08-21T01:00:05Z"
    assert completed["error_message"] is None
    result_payload = json.loads(completed["result_json"])
    assert result_payload["model_run_id"] == model_run_id
    assert result_payload["selected_candidate"] == "BAGGING_PU"

    with pytest.raises(JobStateTransitionError):
        repository.mark_running(
            job_id=job_id,
            started_at="2026-08-21T01:00:06Z",
            stage=JOB_STAGE_STARTING,
            progress_percent=1,
        )
    with pytest.raises(JobStateTransitionError):
        repository.update_progress(
            job_id=job_id,
            progress_percent=80,
            stage=JOB_STAGE_PREPROCESSING,
        )
    with pytest.raises(JobStateTransitionError):
        repository.mark_failed(
            job_id=job_id,
            finished_at="2026-08-21T01:00:07Z",
            error_message="cannot fail a terminal job",
        )


def test_mark_failed_and_fail_stale_active_jobs(database_path: Path) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    repository = JobRepository(database_path)

    queued_job_id = repository.create_training_job(
        created_at="2026-08-21T01:00:00Z",
        request_payload={"analysis_run_id": analysis_run_id},
    )
    repository.mark_failed(
        job_id=queued_job_id,
        finished_at="2026-08-21T01:00:01Z",
        error_message="validation failed",
    )

    queued_failed = repository.fetch_job(queued_job_id)
    assert queued_failed is not None
    assert queued_failed["status"] == JOB_STATUS_FAILED
    assert queued_failed["progress_percent"] == 0
    assert queued_failed["stage"] == JOB_STAGE_FAILED
    assert queued_failed["error_message"] == "validation failed"

    running_job_id = repository.create_training_job(
        created_at="2026-08-21T01:00:02Z",
        request_payload={"analysis_run_id": analysis_run_id},
    )
    repository.mark_running(
        job_id=running_job_id,
        started_at="2026-08-21T01:00:03Z",
        stage=JOB_STAGE_STARTING,
        progress_percent=1,
    )
    repository.update_progress(
        job_id=running_job_id,
        progress_percent=65,
        stage=JOB_STAGE_PREPROCESSING,
    )

    stale_failed = repository.fail_stale_active_jobs(
        finished_at="2026-08-21T01:00:05Z",
        error_message="interrupted by app restart",
    )
    assert stale_failed == 1
    stale_failed_again = repository.fail_stale_active_jobs(
        finished_at="2026-08-21T01:00:06Z",
        error_message="interrupted by app restart",
    )
    assert stale_failed_again == 0

    running_failed = repository.fetch_job(running_job_id)
    assert running_failed is not None
    assert running_failed["status"] == JOB_STATUS_FAILED
    assert running_failed["progress_percent"] == 65
    assert running_failed["stage"] == JOB_STAGE_FAILED
    assert running_failed["error_message"] == "interrupted by app restart"


def test_payload_validation_rejects_invalid_and_forbidden_content(database_path: Path) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    repository = JobRepository(database_path)

    with pytest.raises(JobValidationError, match="unsupported fields"):
        repository.create_training_job(
            created_at="2026-08-21T01:00:00Z",
            request_payload={
                "analysis_run_id": analysis_run_id,
                "customer_id": "CUS_001",
            },
        )

    with pytest.raises(JobValidationError, match="between 0 and 1"):
        repository.create_training_job(
            created_at="2026-08-21T01:00:00Z",
            request_payload={
                "analysis_run_id": analysis_run_id,
                "validation_fraction": float("nan"),
            },
        )

    job_id = repository.create_training_job(
        created_at="2026-08-21T01:01:00Z",
        request_payload={"analysis_run_id": analysis_run_id},
    )
    repository.mark_running(
        job_id=job_id,
        started_at="2026-08-21T01:01:01Z",
        stage=JOB_STAGE_STARTING,
        progress_percent=1,
    )
    model_run_id = _insert_running_model_run(database_path, analysis_run_id)

    with pytest.raises(JobValidationError, match="unsupported fields"):
        repository.mark_completed(
            job_id=job_id,
            finished_at="2026-08-21T01:01:05Z",
            model_run_id=model_run_id,
            result_payload={
                "selected_candidate": "BAGGING_PU",
                "selection_policy": "PRIMARY_ROLE_GOVERNED",
                "quality_flags": ["OBSERVED_LABEL_METRICS_ONLY"],
                "artifact_sha256": "a" * 64,
                "validation_scores": [0.1, 0.2],
            },
        )