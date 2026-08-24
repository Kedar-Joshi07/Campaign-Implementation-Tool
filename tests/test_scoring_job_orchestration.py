from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.jobs.prospect_scoring_worker import run_prospect_scoring_job
from app.repositories.job_repository import JobRepository
from app.repositories.scoring_repository import ScoringRepository
from app.services.model_job_service import (
    ACTIVE_JOB_CONFLICT_MESSAGE,
    ModelJobConflictError,
    STALE_JOB_INTERRUPTION_MESSAGE,
    STALE_SCORING_INTERRUPTION_MESSAGE,
    reconcile_stale_model_training_jobs,
    submit_model_training_job_request,
)
from app.services.scoring_job_service import (
    ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE,
    EXISTING_SCORING_RUN_CONFLICT_MESSAGE,
    ScoringJobConflictError,
    ScoringJobSubmissionError,
    submit_prospect_scoring_job_request,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "scoring-job-orchestration.db"
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
                "Scoring orchestration fixture",
                "2026-08-27T00:00:00Z",
                "2026-08-27T00:00:04Z",
                "COMPLETED",
                "ATTRIBUTED_PURCHASE",
                "{}",
                "{}",
                25,
                10,
                4,
                6,
                0.4,
            ),
        )
        return int(cursor.lastrowid)


def _insert_model_run(database_path: Path, analysis_run_id: int, *, status: str = "COMPLETED") -> int:
    completed_at = "2026-08-27T00:10:30Z" if status == "COMPLETED" else None
    with get_connection(database_path, write=True) as connection:
        cursor = connection.execute(
            """
            INSERT INTO model_runs (
                analysis_run_id,
                model_name,
                created_at,
                completed_at,
                status,
                random_seed,
                validation_fraction,
                selected_candidate,
                artifact_sha256,
                metrics_json,
                feature_contract_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_run_id,
                "Scoring orchestration model",
                "2026-08-27T00:10:00Z",
                completed_at,
                status,
                42,
                0.2,
                "BAGGING_PU",
                "a" * 64,
                "{}",
                "{}",
            ),
        )
        return int(cursor.lastrowid)


def _mark_training_job_completed(repository: JobRepository, *, job_id: int, model_run_id: int) -> None:
    repository.mark_running(
        job_id=job_id,
        started_at="2026-08-27T01:00:01Z",
        stage="STARTING",
        progress_percent=1,
    )
    repository.mark_completed(
        job_id=job_id,
        finished_at="2026-08-27T01:00:05Z",
        model_run_id=model_run_id,
        message="done",
        result_payload={
            "selected_candidate": "BAGGING_PU",
            "selection_policy": "PRIMARY_ROLE_GOVERNED",
            "quality_flags": ["OBSERVED_LABEL_METRICS_ONLY"],
            "challenger_advisory_flags": [],
            "artifact_sha256": "a" * 64,
            "model_role_policy_version": "2",
            "evaluation_contract_version": "2",
        },
    )


def test_submit_scoring_creates_queued_job_and_returns_immediately(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    submitted: list[tuple[Path, int]] = []

    monkeypatch.setattr(
        "app.services.scoring_job_service.validate_scoreable_model",
        lambda *_args, **_kwargs: object(),
    )

    def fake_submitter(path: str | Path, job_id: int) -> None:
        submitted.append((Path(path), job_id))

    job = submit_prospect_scoring_job_request(
        database_path,
        {"model_run_id": model_run_id},
        submitter=fake_submitter,
    )

    assert job["job_type"] == "PROSPECT_SCORING"
    assert job["status"] == "QUEUED"
    assert job["progress_percent"] == 0
    assert job["stage"] == "QUEUED"
    assert job["analysis_run_id"] is None
    assert job["model_run_id"] == model_run_id
    assert len(submitted) == 1
    assert submitted[0][0] == database_path
    assert submitted[0][1] == int(job["job_id"])

    request_payload = json.loads(job["request_json"])
    assert request_payload == {"model_run_id": model_run_id}


def test_scoring_active_job_blocks_second_scoring_and_training_submissions(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)

    monkeypatch.setattr(
        "app.services.scoring_job_service.validate_scoreable_model",
        lambda *_args, **_kwargs: object(),
    )

    submit_prospect_scoring_job_request(
        database_path,
        {"model_run_id": model_run_id},
        submitter=lambda *_: None,
    )

    with pytest.raises(ScoringJobConflictError, match=ACTIVE_COMPUTE_JOB_CONFLICT_MESSAGE):
        submit_prospect_scoring_job_request(
            database_path,
            {"model_run_id": model_run_id},
            submitter=lambda *_: None,
        )

    with pytest.raises(ModelJobConflictError, match=ACTIVE_JOB_CONFLICT_MESSAGE):
        submit_model_training_job_request(
            database_path,
            {"analysis_run_id": analysis_run_id},
            submitter=lambda *_: None,
        )


def test_scoring_submit_rejects_when_completed_canonical_run_exists(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    job_repository = JobRepository(database_path)
    scoring_repository = ScoringRepository(database_path)

    monkeypatch.setattr(
        "app.services.scoring_job_service.validate_scoreable_model",
        lambda *_args, **_kwargs: object(),
    )

    seed_job_id = job_repository.create_scoring_job(
        created_at="2026-08-27T01:00:00Z",
        request_payload={"model_run_id": model_run_id},
    )
    scoring_run_id = scoring_repository.create_scoring_run(
        job_id=seed_job_id,
        model_run_id=model_run_id,
        created_at="2026-08-27T01:00:01Z",
        demographic_snapshot_count=1,
        demographic_min_person_id="PER_000001",
        demographic_max_person_id="PER_000001",
        chunk_size=1000,
        selected_candidate="BAGGING_PU",
        model_role_policy_version="2",
        feature_contract_version="1",
        feature_contract_sha256="a" * 64,
        artifact_sha256="a" * 64,
    )
    scoring_repository.update_counters(
        scoring_run_id=scoring_run_id,
        scored_person_count=1,
        last_person_id="PER_000001",
        score_min=0.5,
        score_max=0.5,
        score_mean=0.5,
    )
    scoring_repository.mark_completed(
        scoring_run_id=scoring_run_id,
        completed_at="2026-08-27T01:00:03Z",
        scored_person_count=1,
        score_min=0.5,
        score_max=0.5,
        score_mean=0.5,
        summary_payload={"seed": True},
    )

    with pytest.raises(ScoringJobConflictError, match=EXISTING_SCORING_RUN_CONFLICT_MESSAGE):
        submit_prospect_scoring_job_request(
            database_path,
            {"model_run_id": model_run_id},
            submitter=lambda *_: None,
        )


def test_scoring_submit_failure_marks_queued_job_failed(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)

    monkeypatch.setattr(
        "app.services.scoring_job_service.validate_scoreable_model",
        lambda *_args, **_kwargs: object(),
    )

    def failing_submitter(_path: str | Path, _job_id: int) -> None:
        raise RuntimeError("submission exploded")

    with pytest.raises(ScoringJobSubmissionError):
        submit_prospect_scoring_job_request(
            database_path,
            {"model_run_id": model_run_id},
            submitter=failing_submitter,
        )

    with get_connection(database_path) as connection:
        row = connection.execute("SELECT * FROM jobs ORDER BY job_id DESC LIMIT 1").fetchone()

    assert row is not None
    assert row["status"] == "FAILED"
    assert row["stage"] == "FAILED"
    assert row["result_json"] is None


def test_scoring_worker_success_marks_completed_with_bounded_result(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    repository = JobRepository(database_path)
    job_id = repository.create_scoring_job(
        created_at="2026-08-27T02:00:00Z",
        request_payload={"model_run_id": model_run_id},
    )

    def fake_run_chunked(
        _database_path: str | Path,
        *,
        model_run_id: int,
        job_id: int,
        chunk_size: int = 25_000,
        project_root: str | Path | None = None,
        progress_callback: Any = None,
    ) -> dict[str, Any]:
        assert model_run_id > 0
        assert job_id > 0
        if progress_callback is not None:
            progress_callback("VALIDATING_MODEL", 5, "validating", 11)
            progress_callback("PREPARING_SCORING_RUN", 10, "preparing", 11)
            progress_callback("SCORING_PROSPECTS", 85, "scoring", 11)
            progress_callback("VERIFYING_COMPLETENESS", 98, "verifying", 11)
            progress_callback("COMPLETED", 100, "done", 11)
        return {
            "scoring_run_id": 11,
            "scored_person_count": 123,
            "score_min": 0.01,
            "score_max": 0.97,
            "score_mean": 0.45,
            "summary": {
                "total_seconds": 2.5,
                "rows_per_second": 49.2,
                "chunk_size": 25000,
                "chunk_count": 3,
                "largest_chunk_rows": 50,
                "largest_transformed_matrix_bytes": 2048,
                "selected_candidate": "BAGGING_PU",
                "model_role_policy_version": "2",
                "feature_contract_version": "1",
                "feature_contract_sha256": "a" * 64,
                "artifact_sha256": "a" * 64,
                "person_ids": ["PER_000001"],
            },
        }

    monkeypatch.setattr(
        "app.jobs.prospect_scoring_worker.run_chunked_prospect_scoring",
        fake_run_chunked,
    )

    run_prospect_scoring_job(database_path, job_id)

    row = repository.fetch_job(job_id)
    assert row is not None
    assert row["status"] == "COMPLETED"
    assert row["stage"] == "COMPLETED"
    assert row["progress_percent"] == 100

    result_payload = json.loads(row["result_json"])
    assert set(result_payload) == {
        "scoring_run_id",
        "model_run_id",
        "scored_person_count",
        "score_min",
        "score_max",
        "score_mean",
        "total_seconds",
        "rows_per_second",
        "chunk_size",
        "chunk_count",
        "largest_chunk_rows",
        "largest_transformed_matrix_bytes",
        "selected_candidate",
        "model_role_policy_version",
        "feature_contract_version",
        "feature_contract_sha256",
        "artifact_sha256",
    }


def test_scoring_worker_failure_and_invalid_result_mark_job_failed(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    repository = JobRepository(database_path)

    failing_job_id = repository.create_scoring_job(
        created_at="2026-08-27T02:10:00Z",
        request_payload={"model_run_id": model_run_id},
    )

    monkeypatch.setattr(
        "app.jobs.prospect_scoring_worker.run_chunked_prospect_scoring",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("scoring failed")),
    )
    run_prospect_scoring_job(database_path, failing_job_id)

    failed_row = repository.fetch_job(failing_job_id)
    assert failed_row is not None
    assert failed_row["status"] == "FAILED"
    assert failed_row["stage"] == "FAILED"
    assert failed_row["result_json"] is None

    invalid_payload_job_id = repository.create_scoring_job(
        created_at="2026-08-27T02:10:10Z",
        request_payload={"model_run_id": model_run_id},
    )

    def invalid_result(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "scoring_run_id": 19,
            "scored_person_count": 20,
            "score_min": 0.1,
            "score_max": 0.9,
            "score_mean": 0.3,
            "summary": {
                "total_seconds": 1.0,
                "rows_per_second": 20.0,
                "chunk_size": 25000,
                "chunk_count": 1,
                "largest_chunk_rows": 20,
                "largest_transformed_matrix_bytes": 512,
                "selected_candidate": "BAGGING_PU",
                "model_role_policy_version": "2",
                "feature_contract_version": "1",
                "feature_contract_sha256": "a" * 64,
                "artifact_sha256": "not-a-valid-sha",
            },
        }

    monkeypatch.setattr(
        "app.jobs.prospect_scoring_worker.run_chunked_prospect_scoring",
        invalid_result,
    )
    run_prospect_scoring_job(database_path, invalid_payload_job_id)

    invalid_row = repository.fetch_job(invalid_payload_job_id)
    assert invalid_row is not None
    assert invalid_row["status"] == "FAILED"
    assert invalid_row["stage"] == "FAILED"
    assert invalid_row["result_json"] is None


def test_startup_reconciliation_fails_stale_scoring_jobs_and_running_scoring_runs(
    database_path: Path,
) -> None:
    analysis_run_id = _insert_completed_analysis(database_path)
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    repository = JobRepository(database_path)
    scoring_repository = ScoringRepository(database_path)

    completed_training_job_id = repository.create_training_job(
        created_at="2026-08-27T03:00:00Z",
        request_payload={"analysis_run_id": analysis_run_id},
    )
    _mark_training_job_completed(
        repository,
        job_id=completed_training_job_id,
        model_run_id=model_run_id,
    )

    queued_scoring_job_id = repository.create_scoring_job(
        created_at="2026-08-27T03:00:10Z",
        request_payload={"model_run_id": model_run_id},
    )

    associated_run_id = scoring_repository.create_scoring_run(
        job_id=queued_scoring_job_id,
        model_run_id=model_run_id,
        created_at="2026-08-27T03:00:11Z",
        demographic_snapshot_count=0,
        demographic_min_person_id=None,
        demographic_max_person_id=None,
        chunk_size=1000,
        selected_candidate="BAGGING_PU",
        model_role_policy_version="2",
        feature_contract_version="1",
        feature_contract_sha256="a" * 64,
        artifact_sha256="a" * 64,
    )
    orphan_run_id = scoring_repository.create_scoring_run(
        job_id=completed_training_job_id,
        model_run_id=model_run_id,
        created_at="2026-08-27T03:00:12Z",
        demographic_snapshot_count=0,
        demographic_min_person_id=None,
        demographic_max_person_id=None,
        chunk_size=1000,
        selected_candidate="BAGGING_PU",
        model_role_policy_version="2",
        feature_contract_version="1",
        feature_contract_sha256="a" * 64,
        artifact_sha256="a" * 64,
    )

    stale_failed = reconcile_stale_model_training_jobs(database_path)
    assert stale_failed == 1

    completed_training_job = repository.fetch_job(completed_training_job_id)
    queued_scoring_job = repository.fetch_job(queued_scoring_job_id)
    assert completed_training_job is not None
    assert completed_training_job["status"] == "COMPLETED"
    assert queued_scoring_job is not None
    assert queued_scoring_job["status"] == "FAILED"
    assert queued_scoring_job["error_message"] == STALE_JOB_INTERRUPTION_MESSAGE

    associated = scoring_repository.fetch_scoring_run(associated_run_id)
    orphan = scoring_repository.fetch_scoring_run(orphan_run_id)
    assert associated is not None
    assert associated["status"] == "FAILED"
    assert associated["error_message"] == STALE_SCORING_INTERRUPTION_MESSAGE
    assert orphan is not None
    assert orphan["status"] == "FAILED"
    assert orphan["error_message"] == STALE_SCORING_INTERRUPTION_MESSAGE
