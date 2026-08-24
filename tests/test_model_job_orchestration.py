from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.jobs.model_training_worker import run_model_training_job
from app.repositories.job_repository import JobRepository
from app.services import model_job_service as model_job_service_module
from app.services.model_job_service import (
    ACTIVE_JOB_CONFLICT_MESSAGE,
    ANALYSIS_NOT_AVAILABLE_MESSAGE,
    ModelJobConflictError,
    ModelJobSubmissionError,
    ModelJobValidationError,
    STALE_JOB_INTERRUPTION_MESSAGE,
    submit_model_training_job_request,
)
from app.services.model_training_service import ModelTrainingExecutionError
from app.services.model_training_service import ModelTrainingServiceError


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "model-job-orchestration.db"
    initialize_database(path)
    return path


def _insert_analysis_run(database_path: Path, *, status: str) -> int:
    completed_at = "2026-08-21T00:00:02Z" if status != "RUNNING" else None
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
                f"Analysis {status}",
                "2026-08-21T00:00:00Z",
                completed_at,
                status,
                "ATTRIBUTED_PURCHASE",
                "{}",
                "{}" if status != "RUNNING" else None,
                25,
                10,
                4,
                6,
                0.4,
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
                "Model run fixture",
                "2026-08-21T00:10:00Z",
                "RUNNING",
                42,
                0.2,
            ),
        )
        return int(cursor.lastrowid)


def test_submit_creates_queued_job_and_returns_immediately(database_path: Path) -> None:
    analysis_run_id = _insert_analysis_run(database_path, status="COMPLETED")
    submitted: list[tuple[Path, int]] = []

    def fake_submitter(path: str | Path, job_id: int) -> None:
        submitted.append((Path(path), job_id))

    job = submit_model_training_job_request(
        database_path,
        {
            "analysis_run_id": analysis_run_id,
            "model_name": " Phase 4 async run ",
            "random_seed": 7,
            "validation_fraction": 0.25,
            "run_elkan_challenger": False,
        },
        submitter=fake_submitter,
    )

    assert job["status"] == "QUEUED"
    assert job["progress_percent"] == 0
    assert job["stage"] == "QUEUED"
    assert job["analysis_run_id"] == analysis_run_id
    assert len(submitted) == 1
    assert submitted[0][0] == database_path
    assert submitted[0][1] == job["job_id"]


def test_submit_enforces_one_active_job_rule(database_path: Path) -> None:
    analysis_run_id = _insert_analysis_run(database_path, status="COMPLETED")

    submit_model_training_job_request(
        database_path,
        {"analysis_run_id": analysis_run_id},
        submitter=lambda *_: None,
    )

    with pytest.raises(ModelJobConflictError, match=ACTIVE_JOB_CONFLICT_MESSAGE):
        submit_model_training_job_request(
            database_path,
            {"analysis_run_id": analysis_run_id},
            submitter=lambda *_: None,
        )


def test_submit_rejects_missing_or_not_completed_analysis(database_path: Path) -> None:
    running_id = _insert_analysis_run(database_path, status="RUNNING")
    failed_id = _insert_analysis_run(database_path, status="FAILED")

    for analysis_run_id in (running_id, failed_id, 999999):
        with pytest.raises(ModelJobValidationError, match=ANALYSIS_NOT_AVAILABLE_MESSAGE):
            submit_model_training_job_request(
                database_path,
                {"analysis_run_id": analysis_run_id},
                submitter=lambda *_: None,
            )


def test_submit_failure_marks_queued_job_failed(database_path: Path) -> None:
    analysis_run_id = _insert_analysis_run(database_path, status="COMPLETED")

    def failing_submitter(_path: str | Path, _job_id: int) -> None:
        raise RuntimeError("submission exploded")

    with pytest.raises(ModelJobSubmissionError):
        submit_model_training_job_request(
            database_path,
            {"analysis_run_id": analysis_run_id},
            submitter=failing_submitter,
        )

    with get_connection(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM jobs ORDER BY job_id DESC LIMIT 1"
        ).fetchone()

    assert row is not None
    assert row["status"] == "FAILED"
    assert row["stage"] == "FAILED"
    assert row["progress_percent"] == 0
    assert row["finished_at"] is not None
    assert row["result_json"] is None


def test_worker_success_path_persists_progress_and_completion(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_analysis_run(database_path, status="COMPLETED")
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    repository = JobRepository(database_path)
    job_id = repository.create_training_job(
        created_at="2026-08-21T00:20:00Z",
        request_payload={"analysis_run_id": analysis_run_id},
    )

    def fake_train_and_persist_model(*args: Any, **kwargs: Any) -> dict[str, Any]:
        callback = kwargs.get("progress_callback")
        if callback is not None:
            callback("RECONSTRUCTING_COHORT", 15, "cohort done", model_run_id)
            callback("SPLITTING_DATA", 25, "split done", model_run_id)
            callback("PREPROCESSING", 35, "prep done", model_run_id)
            callback("TRAINING_PRIMARY", 50, "primary done", model_run_id)
            callback("TRAINING_CHALLENGER", 62, "challenger skipped", model_run_id)
            callback("TRAINING_DIAGNOSTIC", 70, "diagnostic done", model_run_id)
            callback("EVALUATING", 80, "evaluation done", model_run_id)
            callback("PERSISTING_ARTIFACT", 90, "persist done", model_run_id)
            callback("VERIFYING_ARTIFACT", 95, "verify done", model_run_id)
        return {
            "model_run_id": model_run_id,
            "selected_candidate": "BAGGING_PU",
            "selection_policy": "PRIMARY_ROLE_GOVERNED",
            "quality_flags": ["OBSERVED_LABEL_METRICS_ONLY"],
            "challenger_advisory_flags": [],
            "artifact_sha256": "a" * 64,
            "model_role_policy_version": "2",
            "evaluation_contract_version": "2",
        }

    monkeypatch.setattr(
        "app.jobs.model_training_worker.train_and_persist_model",
        fake_train_and_persist_model,
    )

    run_model_training_job(database_path, job_id)
    row = repository.fetch_job(job_id)
    assert row is not None
    assert row["status"] == "COMPLETED"
    assert row["progress_percent"] == 100
    assert row["stage"] == "COMPLETED"
    assert row["model_run_id"] == model_run_id
    assert row["finished_at"] is not None

    result_payload = json.loads(row["result_json"])
    assert result_payload["model_run_id"] == model_run_id
    assert result_payload["selected_candidate"] == "BAGGING_PU"
    assert result_payload["selection_policy"] == "PRIMARY_ROLE_GOVERNED"


def test_worker_failure_attaches_model_run_and_marks_failed(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_analysis_run(database_path, status="COMPLETED")
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    repository = JobRepository(database_path)
    job_id = repository.create_training_job(
        created_at="2026-08-21T00:20:00Z",
        request_payload={"analysis_run_id": analysis_run_id},
    )

    def failing_train(*args: Any, **kwargs: Any) -> dict[str, Any]:
        callback = kwargs.get("progress_callback")
        if callback is not None:
            callback("PREPROCESSING", 35, "prep in progress", model_run_id)
        raise ModelTrainingExecutionError(
            "forced primary failure",
            model_run_id=model_run_id,
        )

    monkeypatch.setattr("app.jobs.model_training_worker.train_and_persist_model", failing_train)

    run_model_training_job(database_path, job_id)
    row = repository.fetch_job(job_id)
    assert row is not None
    assert row["status"] == "FAILED"
    assert row["stage"] == "FAILED"
    assert row["model_run_id"] == model_run_id
    assert row["progress_percent"] == 35


def test_worker_marks_failed_when_progress_becomes_non_monotonic(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_analysis_run(database_path, status="COMPLETED")
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    repository = JobRepository(database_path)
    job_id = repository.create_training_job(
        created_at="2026-08-21T00:20:00Z",
        request_payload={"analysis_run_id": analysis_run_id},
    )

    def non_monotonic_train(*args: Any, **kwargs: Any) -> dict[str, Any]:
        callback = kwargs.get("progress_callback")
        if callback is not None:
            callback("PREPROCESSING", 35, "prep done", model_run_id)
            callback("SPLITTING_DATA", 25, "regressed", model_run_id)
        return {}

    monkeypatch.setattr(
        "app.jobs.model_training_worker.train_and_persist_model",
        non_monotonic_train,
    )

    run_model_training_job(database_path, job_id)
    row = repository.fetch_job(job_id)
    assert row is not None
    assert row["status"] == "FAILED"
    assert row["stage"] == "FAILED"
    assert "Job progress must be monotonic" in row["error_message"]


def test_startup_reconciliation_fails_stale_jobs_only(database_path: Path) -> None:
    analysis_run_id = _insert_analysis_run(database_path, status="COMPLETED")
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    repository = JobRepository(database_path)
    queued_job_id = repository.create_training_job(
        created_at="2026-08-21T00:30:00Z",
        request_payload={"analysis_run_id": analysis_run_id},
    )
    completed_result_json = json.dumps(
        {
            "model_run_id": model_run_id,
            "selected_candidate": "BAGGING_PU",
            "selection_policy": "PRIMARY_ROLE_GOVERNED",
            "quality_flags": [],
            "challenger_advisory_flags": [],
            "artifact_sha256": "a" * 64,
            "model_role_policy_version": "2",
            "evaluation_contract_version": "2",
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO jobs (
                job_type, status, progress_percent, stage, message,
                analysis_run_id, model_run_id, created_at, started_at,
                request_json
            ) VALUES (?, 'RUNNING', 60, 'PREPROCESSING', ?, ?, ?, ?, ?, ?)
            """,
            (
                "MODEL_TRAINING",
                "running fixture",
                analysis_run_id,
                model_run_id,
                "2026-08-21T00:31:00Z",
                "2026-08-21T00:31:01Z",
                '{"analysis_run_id":1,"model_name":null,"random_seed":42,'
                '"run_elkan_challenger":true,"validation_fraction":0.2}',
            ),
        )
        connection.execute(
            """
            INSERT INTO jobs (
                job_type, status, progress_percent, stage, message,
                analysis_run_id, model_run_id, created_at, started_at,
                finished_at, request_json, result_json
            ) VALUES (?, 'COMPLETED', 100, 'COMPLETED', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "MODEL_TRAINING",
                "completed fixture",
                analysis_run_id,
                model_run_id,
                "2026-08-21T00:32:00Z",
                "2026-08-21T00:32:01Z",
                "2026-08-21T00:32:05Z",
                '{"analysis_run_id":1,"model_name":null,"random_seed":42,'
                '"run_elkan_challenger":true,"validation_fraction":0.2}',
                completed_result_json,
            ),
        )

    stale_failed = model_job_service_module.reconcile_stale_model_training_jobs(database_path)
    assert stale_failed == 2

    with get_connection(database_path) as connection:
        rows = connection.execute(
            "SELECT job_id, status, stage, error_message FROM jobs ORDER BY job_id"
        ).fetchall()

    by_id = {int(row["job_id"]): dict(row) for row in rows}
    assert by_id[queued_job_id]["status"] == "FAILED"
    assert by_id[queued_job_id]["stage"] == "FAILED"
    assert by_id[queued_job_id]["error_message"] == STALE_JOB_INTERRUPTION_MESSAGE
    completed_rows = [row for row in rows if row["status"] == "COMPLETED"]
    assert len(completed_rows) == 1


def test_startup_reconciliation_preserves_failed_and_completed_rows(
    database_path: Path,
) -> None:
    analysis_run_id = _insert_analysis_run(database_path, status="COMPLETED")
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    repository = JobRepository(database_path)

    queued_job_id = repository.create_training_job(
        created_at="2026-08-21T05:30:00Z",
        request_payload={"analysis_run_id": analysis_run_id},
    )

    failed_result_json = json.dumps(
        {
            "model_run_id": model_run_id,
            "selected_candidate": "BAGGING_PU",
            "selection_policy": "PRIMARY_ROLE_GOVERNED",
            "quality_flags": ["OBSERVED_LABEL_METRICS_ONLY"],
            "challenger_advisory_flags": [],
            "artifact_sha256": "a" * 64,
            "model_role_policy_version": "2",
            "evaluation_contract_version": "2",
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            """
            INSERT INTO jobs (
                job_type, status, progress_percent, stage, message,
                analysis_run_id, model_run_id, created_at, started_at,
                finished_at, request_json, result_json, error_message
            ) VALUES (?, 'FAILED', 70, 'FAILED', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "MODEL_TRAINING",
                "failed fixture",
                analysis_run_id,
                model_run_id,
                "2026-08-21T05:31:00Z",
                "2026-08-21T05:31:01Z",
                "2026-08-21T05:31:02Z",
                '{"analysis_run_id":1,"model_name":null,"random_seed":42,'
                '"run_elkan_challenger":true,"validation_fraction":0.2}',
                failed_result_json,
                "existing failure",
            ),
        )

    stale_failed = model_job_service_module.reconcile_stale_model_training_jobs(database_path)
    assert stale_failed == 1

    queued = repository.fetch_job(queued_job_id)
    assert queued is not None
    assert queued["status"] == "FAILED"
    assert queued["error_message"] == STALE_JOB_INTERRUPTION_MESSAGE

    with get_connection(database_path) as connection:
        failed_row = connection.execute(
            "SELECT status, stage, error_message FROM jobs WHERE message = ?",
            ("failed fixture",),
        ).fetchone()
        assert failed_row is not None
        assert tuple(failed_row) == ("FAILED", "FAILED", "existing failure")


def test_concurrent_submit_allows_only_one_active_job(database_path: Path) -> None:
    analysis_run_id = _insert_analysis_run(database_path, status="COMPLETED")
    release_submitter = threading.Event()

    def blocking_submitter(_path: str | Path, _job_id: int) -> None:
        release_submitter.wait(timeout=2)

    def submit_once() -> tuple[str, int | str]:
        try:
            job = submit_model_training_job_request(
                database_path,
                {"analysis_run_id": analysis_run_id},
                submitter=blocking_submitter,
            )
            return ("accepted", int(job["job_id"]))
        except ModelJobConflictError as exc:
            return ("conflict", str(exc))

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(submit_once)
        second = executor.submit(submit_once)
        outcomes = [first.result(), second.result()]

    release_submitter.set()

    accepted = [item for item in outcomes if item[0] == "accepted"]
    conflicts = [item for item in outcomes if item[0] == "conflict"]
    assert len(accepted) == 1
    assert len(conflicts) == 1
    assert conflicts[0][1] == ACTIVE_JOB_CONFLICT_MESSAGE

    with get_connection(database_path) as connection:
        rows = connection.execute(
            "SELECT status FROM jobs ORDER BY job_id"
        ).fetchall()
    assert [row["status"] for row in rows] == ["QUEUED"]


def test_worker_service_failure_before_model_run_id_marks_failed(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_analysis_run(database_path, status="COMPLETED")
    repository = JobRepository(database_path)
    job_id = repository.create_training_job(
        created_at="2026-08-21T05:40:00Z",
        request_payload={"analysis_run_id": analysis_run_id},
    )

    def failing_train(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ModelTrainingServiceError("forced pre-model-run failure")

    monkeypatch.setattr("app.jobs.model_training_worker.train_and_persist_model", failing_train)

    run_model_training_job(database_path, job_id)
    row = repository.fetch_job(job_id)
    assert row is not None
    assert row["status"] == "FAILED"
    assert row["stage"] == "FAILED"
    assert row["model_run_id"] is None


def test_worker_unexpected_crash_marks_failed_without_fake_success(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_analysis_run(database_path, status="COMPLETED")
    repository = JobRepository(database_path)
    job_id = repository.create_training_job(
        created_at="2026-08-21T05:45:00Z",
        request_payload={"analysis_run_id": analysis_run_id},
    )

    def crashing_train(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("worker crash")

    monkeypatch.setattr("app.jobs.model_training_worker.train_and_persist_model", crashing_train)

    run_model_training_job(database_path, job_id)
    row = repository.fetch_job(job_id)
    assert row is not None
    assert row["status"] == "FAILED"
    assert row["stage"] == "FAILED"
    assert row["result_json"] is None


def test_worker_artifact_completion_failure_cannot_fake_success(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_run_id = _insert_analysis_run(database_path, status="COMPLETED")
    model_run_id = _insert_model_run(database_path, analysis_run_id)
    repository = JobRepository(database_path)
    job_id = repository.create_training_job(
        created_at="2026-08-21T05:50:00Z",
        request_payload={"analysis_run_id": analysis_run_id},
    )

    def invalid_completion_summary(*args: Any, **kwargs: Any) -> dict[str, Any]:
        callback = kwargs.get("progress_callback")
        if callback is not None:
            callback("VERIFYING_ARTIFACT", 95, "verifying", model_run_id)
        return {
            "model_run_id": model_run_id,
            "selected_candidate": "BAGGING_PU",
            "selection_policy": "PRIMARY_ROLE_GOVERNED",
            "quality_flags": ["OBSERVED_LABEL_METRICS_ONLY"],
            "challenger_advisory_flags": [],
            "artifact_sha256": "bad-sha",
            "model_role_policy_version": "2",
            "evaluation_contract_version": "2",
        }

    monkeypatch.setattr(
        "app.jobs.model_training_worker.train_and_persist_model",
        invalid_completion_summary,
    )

    run_model_training_job(database_path, job_id)
    row = repository.fetch_job(job_id)
    assert row is not None
    assert row["status"] == "FAILED"
    assert row["stage"] == "FAILED"
    assert row["result_json"] is None


def test_phase4_worker_and_service_do_not_use_fastapi_backgroundtasks() -> None:
    root = Path(__file__).resolve().parents[1]
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            root / "app" / "jobs" / "executor.py",
            root / "app" / "jobs" / "model_training_worker.py",
            root / "app" / "services" / "model_job_service.py",
            root / "app" / "jobs" / "prospect_scoring_worker.py",
            root / "app" / "services" / "scoring_job_service.py",
        )
    )
    assert "BackgroundTasks" not in sources