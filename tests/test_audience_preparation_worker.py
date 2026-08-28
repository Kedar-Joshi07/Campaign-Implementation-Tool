from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.jobs.audience_preparation_worker import run_audience_preparation_job
from app.repositories.job_repository import JobRepository


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "audience-preparation-worker.db"
    initialize_database(path)
    return path


def _insert_queued_audience_job(database_path: Path) -> int:
    repository = JobRepository(database_path)
    return repository.create_audience_preparation_job(
        created_at="2026-09-03T00:00:00Z",
        request_payload={"scoring_run_id": 5, "rank_contract_version": "1"},
    )


def test_worker_marks_completed_with_sanitized_result(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = JobRepository(database_path)
    job_id = _insert_queued_audience_job(database_path)

    def fake_prepare(
        _database_path: str | Path,
        *,
        scoring_run_id: int,
        rank_contract_version: str,
        chunk_size: int = 100_000,
    ) -> dict[str, Any]:
        assert scoring_run_id == 5
        assert rank_contract_version == "1"
        _ = chunk_size
        return {
            "scoring_run_id": 5,
            "model_run_id": 12,
            "rank_contract_version": "1",
            "boundary_count": 100,
            "total_population": 200,
            "boundary_person_ids": ["PER_000001"],
        }

    monkeypatch.setattr(
        "app.jobs.audience_preparation_worker.run_audience_rank_preparation",
        fake_prepare,
    )

    run_audience_preparation_job(database_path, job_id)

    row = repository.fetch_job(job_id)
    assert row is not None
    assert row["status"] == "COMPLETED"
    assert row["stage"] == "COMPLETED"
    assert row["progress_percent"] == 100

    payload = json.loads(row["result_json"])
    assert set(payload) == {
        "scoring_run_id",
        "total_population",
        "rank_contract_version",
        "boundary_count",
    }


def test_worker_marks_failed_on_preparation_error(
    database_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = JobRepository(database_path)
    job_id = _insert_queued_audience_job(database_path)

    monkeypatch.setattr(
        "app.jobs.audience_preparation_worker.run_audience_rank_preparation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("forced failure")),
    )

    run_audience_preparation_job(database_path, job_id)

    row = repository.fetch_job(job_id)
    assert row is not None
    assert row["status"] == "FAILED"
    assert row["stage"] == "FAILED"
    assert row["result_json"] is None


def test_worker_ignores_non_queued_or_wrong_job_type(database_path: Path) -> None:
    repository = JobRepository(database_path)
    queued_job_id = _insert_queued_audience_job(database_path)

    with get_connection(database_path, write=True) as connection:
        connection.execute(
            (
                "UPDATE jobs "
                "SET status = 'FAILED', stage = 'FAILED', progress_percent = 0, "
                "finished_at = ?, error_message = ? WHERE job_id = ?"
            ),
            ("2026-09-03T00:00:05Z", "fixture failure", queued_job_id),
        )

    run_audience_preparation_job(database_path, queued_job_id)
    row = repository.fetch_job(queued_job_id)
    assert row is not None
    assert row["status"] == "FAILED"


def test_worker_ignores_wrong_job_type(database_path: Path) -> None:
    repository = JobRepository(database_path)
    with get_connection(database_path, write=True) as connection:
        analysis_run_id = int(
            connection.execute(
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
                    "Worker wrong type fixture",
                    "2026-09-03T00:10:00Z",
                    "2026-09-03T00:10:10Z",
                    "COMPLETED",
                    "ATTRIBUTED_PURCHASE",
                    "{}",
                    "{}",
                    1,
                    1,
                    1,
                    0,
                    1.0,
                ),
            ).lastrowid
        )
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
                request_json
            ) VALUES (?, 'QUEUED', 0, 'QUEUED', ?, NULL, ?, ?)
            """,
            (
                "MODEL_TRAINING",
                analysis_run_id,
                "2026-09-03T00:10:20Z",
                json.dumps(
                    {
                        "analysis_run_id": analysis_run_id,
                        "model_name": None,
                        "random_seed": 42,
                        "validation_fraction": 0.2,
                        "run_elkan_challenger": True,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        )
        wrong_job_id = int(cursor.lastrowid)

    run_audience_preparation_job(database_path, wrong_job_id)
    row = repository.fetch_job(wrong_job_id)
    assert row is not None
    assert row["status"] == "QUEUED"
