"""Durable Phase 11 lifecycle, truthful progress, ETA, and issue contracts."""

# ruff: noqa: F401, F811 - imported pytest fixture is intentionally injected.

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from app.database.connection import get_connection
from app.services.phase11_result_contracts import (
    Phase11RegistryStateError,
    Phase11RegistryValidationError,
)
from app.services.phase11_run_lifecycle_service import (
    project_run_issue,
    project_run_progress,
)
from tests.test_phase11_search_result_registry import _search, case


def test_runtime_progress_is_durable_monotonic_and_terminal(case) -> None:
    repository = case[3]
    search_run_id = _search(
        case,
        selection_mode="TOP_N",
        target_count=100,
    )
    queued = repository.fetch_search_runtime(search_run_id)
    assert queued is not None
    assert queued["lifecycle_status"] == "QUEUED"
    assert queued["progress_percent"] == 0
    assert queued["total_count"] == 100

    repository.mark_processing(search_run_id)
    repository.update_search_progress(
        search_run_id,
        stage_code="MATERIALIZING_RESULT",
        stage_label="Building the result snapshot",
        progress_percent=55,
        status_message="Processed 25 potential customers.",
        processed_count=25,
        total_count=100,
    )
    active = repository.fetch_search_runtime(search_run_id)
    assert active["lifecycle_status"] == "PROCESSING"
    assert active["processing_started_at"] is not None
    assert active["progress_percent"] == 55
    assert active["processed_count"] == 25
    assert active["state_version"] >= 3

    with pytest.raises(Phase11RegistryValidationError, match="cannot decrease"):
        repository.update_search_progress(
            search_run_id,
            stage_code="CHECKING_INTELLIGENCE",
            stage_label="Checking targeting intelligence",
            progress_percent=20,
            status_message="Checking targeting intelligence.",
        )

    repository.fail_search_run(
        search_run_id,
        failure_code="SOURCE_DATA_UNAVAILABLE",
        failure_category="SOURCE_DATA",
        failure_summary="The current source data is not available.",
        resolution_steps=(
            "Confirm the source data import completed successfully.",
            "Submit the search again after data readiness is restored.",
        ),
    )
    failed = repository.fetch_search_runtime(search_run_id)
    assert failed["lifecycle_status"] == "FAILED"
    assert failed["progress_percent"] == 55
    assert project_run_issue(failed) == {
        "code": "SOURCE_DATA_UNAVAILABLE",
        "category": "SOURCE_DATA",
        "summary": "The current source data is not available.",
        "resolution_steps": [
            "Confirm the source data import completed successfully.",
            "Submit the search again after data readiness is restored.",
        ],
        "retryable": True,
        "affected_stage": "MATERIALIZING_RESULT",
        "technical_reference": "SOURCE_DATA_UNAVAILABLE",
        "user_action_required": False,
    }


def test_future_control_states_have_a_guarded_durable_transition_contract(case) -> None:
    search_run_id = _search(case)
    repository = case[3]
    repository.mark_processing(search_run_id)
    with get_connection(case[0], write=True) as connection:
        connection.execute(
            "UPDATE campaign_search_run_runtime SET lifecycle_status='PAUSE_REQUESTED' WHERE search_run_id=?",
            (search_run_id,),
        )
        connection.execute(
            "UPDATE campaign_search_run_runtime SET lifecycle_status='PAUSED' WHERE search_run_id=?",
            (search_run_id,),
        )
    assert repository.fetch_search_runtime(search_run_id)["lifecycle_status"] == "PAUSED"
    with pytest.raises(sqlite3.IntegrityError, match="invalid search runtime transition"):
        with get_connection(case[0], write=True) as connection:
            connection.execute(
                "UPDATE campaign_search_run_runtime SET lifecycle_status='COMPLETED', progress_percent=100 WHERE search_run_id=?",
                (search_run_id,),
            )


def test_retry_keeps_visible_run_and_creates_idempotent_immutable_attempt(case) -> None:
    repository = case[3]
    search_run_id = _search(case)
    repository.fail_search_run(
        search_run_id,
        blocked=True,
        failure_code="CALIBRATION_NOT_READY",
        failure_category="CALIBRATION",
        timestamp="2026-09-13T10:00:10Z",
    )

    retried = repository.retry_search_run(
        search_run_id,
        idempotency_key="retry-contract-0001",
        timestamp="2026-09-13T10:00:20Z",
    )
    repeated = repository.retry_search_run(
        search_run_id,
        idempotency_key="retry-contract-0001",
        timestamp="2026-09-13T10:00:21Z",
    )

    assert retried["search_run_id"] == repeated["search_run_id"] == search_run_id
    assert retried["current_attempt_number"] == repeated["current_attempt_number"] == 2
    with get_connection(case[0]) as connection:
        attempts = connection.execute(
            """SELECT attempt_number,status,failure_code,idempotency_key
               FROM campaign_search_attempts WHERE search_run_id=?
               ORDER BY attempt_number""",
            (search_run_id,),
        ).fetchall()
    assert [tuple(row) for row in attempts] == [
        (1, "BLOCKED", "CALIBRATION_NOT_READY", None),
        (2, "QUEUED", None, "retry-contract-0001"),
    ]


def test_permanent_failure_is_not_retryable(case) -> None:
    repository = case[3]
    search_run_id = _search(case)
    repository.fail_search_run(
        search_run_id,
        failure_code="INVALID_IMMUTABLE_CONTRACT",
        failure_category="PERMANENT_CONTRACT_FAILURE",
        failure_summary="The saved search contract is permanently invalid.",
        retryable=False,
    )

    issue = project_run_issue(repository.fetch_search_runtime(search_run_id))
    assert issue is not None
    assert issue["retryable"] is False
    with pytest.raises(Phase11RegistryStateError, match="not eligible for retry"):
        repository.retry_search_run(
            search_run_id,
            idempotency_key="permanent-failure-retry",
        )
    assert repository.fetch_search_run(search_run_id)["current_attempt_number"] == 1


def test_concurrent_retry_clicks_create_exactly_one_next_attempt(case) -> None:
    repository = case[3]
    search_run_id = _search(case)
    repository.fail_search_run(
        search_run_id,
        blocked=True,
        failure_code="CALIBRATION_NOT_READY",
        failure_category="CALIBRATION",
        timestamp="2026-09-13T10:00:10Z",
    )

    def retry(_index: int) -> int:
        row = repository.retry_search_run(
            search_run_id,
            idempotency_key="concurrent-retry-0001",
            timestamp="2026-09-13T10:00:20Z",
        )
        return int(row["current_attempt_number"])

    with ThreadPoolExecutor(max_workers=8) as executor:
        attempts = list(executor.map(retry, range(8)))

    assert attempts == [2] * 8
    with get_connection(case[0]) as connection:
        rows = connection.execute(
            """SELECT attempt_number,status,idempotency_key
               FROM campaign_search_attempts WHERE search_run_id=?
               ORDER BY attempt_number""",
            (search_run_id,),
        ).fetchall()
    assert [tuple(row) for row in rows] == [
        (1, "BLOCKED", None),
        (2, "QUEUED", "concurrent-retry-0001"),
    ]


def test_bulk_queue_positions_are_fifo_and_ignore_terminal_runs(case) -> None:
    repository = case[3]
    first = _search(case, campaign_name="First queued")
    second = _search(case, campaign_name="Second queued")
    third = _search(case, campaign_name="Third terminal")
    repository.fail_search_run(
        third,
        blocked=True,
        failure_code="NO_HISTORY",
        failure_category="HISTORY",
        timestamp="2026-09-13T10:00:10Z",
    )

    assert repository.queue_positions([second, third, first, second]) == {
        first: 1,
        second: 2,
    }


def test_stale_processing_attempt_is_recoverable_but_live_attempt_is_not(case) -> None:
    repository = case[3]
    search_run_id = _search(case)
    repository.mark_processing(search_run_id)
    with get_connection(case[0], write=True) as connection:
        connection.execute(
            """UPDATE campaign_search_run_runtime
               SET heartbeat_at='2026-09-13T10:00:00Z',updated_at='2026-09-13T10:00:00Z'
               WHERE search_run_id=?""",
            (search_run_id,),
        )
    with pytest.raises(Phase11RegistryStateError, match="still active"):
        repository.retry_search_run(
            search_run_id,
            idempotency_key="retry-live-0001",
            timestamp="2026-09-13T10:00:20Z",
        )

    stale_issue = project_run_issue(
        repository.fetch_search_runtime(search_run_id),
        now=datetime(2026, 9, 13, 10, 3, tzinfo=timezone.utc),
    )
    assert stale_issue is not None
    assert stale_issue["code"] == "STALE_PROCESSING_ATTEMPT"
    assert stale_issue["retryable"] is True

    recovered = repository.retry_search_run(
        search_run_id,
        idempotency_key="retry-stale-0001",
        timestamp="2026-09-13T10:03:00Z",
    )
    assert recovered["status"] == "QUEUED"
    assert recovered["current_attempt_number"] == 2
    with get_connection(case[0]) as connection:
        first = connection.execute(
            """SELECT status,failure_code,failure_stage_code,retryable
               FROM campaign_search_attempts
               WHERE search_run_id=? AND attempt_number=1""",
            (search_run_id,),
        ).fetchone()
    assert tuple(first) == (
        "FAILED", "STALE_PROCESSING_ATTEMPT", "CHECKING_INTELLIGENCE", 1,
    )


def test_eta_is_bounded_qualified_and_never_fabricated_for_queued_work() -> None:
    started = datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc)
    run = {
        "status": "PROCESSING",
        "created_at": started.isoformat(),
        "started_at": started.isoformat(),
        "completed_at": None,
        "selected_count": None,
    }
    runtime = {
        "lifecycle_status": "PROCESSING",
        "processing_started_at": started.isoformat(),
        "stage_code": "SCORING_POTENTIAL_CUSTOMERS",
        "stage_label": "Matching the potential-customer universe",
        "progress_percent": 50,
        "processed_count": 2_500_000,
        "total_count": 5_000_000,
        "progress_unit": "potential customers",
        "status_message": "Matching the full potential-customer universe.",
        "updated_at": started.isoformat(),
        "heartbeat_at": started.isoformat(),
        "state_version": 4,
    }
    projected = project_run_progress(
        run,
        runtime | {"stage_started_at": started.isoformat()},
        now=started + timedelta(seconds=100),
        stage_duration_samples=[150, 180, 220, 275],
    )
    assert projected["estimated_seconds_remaining_low"] == 100
    assert projected["estimated_seconds_remaining_high"] == 175
    assert projected["estimate_confidence"] == "MEDIUM"
    assert projected["estimate_basis"] == "HISTORICAL_STAGE_P50_P90"

    estimating = project_run_progress(
        run,
        runtime | {"stage_started_at": started.isoformat()},
        now=started + timedelta(seconds=100),
    )
    assert estimating["estimated_seconds_remaining_low"] is None
    assert estimating["estimate_basis"] == "INSUFFICIENT_STAGE_HISTORY"

    queued = project_run_progress(
        run | {"status": "QUEUED"},
        runtime | {
            "lifecycle_status": "QUEUED",
            "progress_percent": 0,
        },
        now=started,
    )
    assert queued["estimated_seconds_remaining_low"] is None
    assert queued["estimated_completion_at"] is None
    assert queued["estimate_confidence"] == "UNAVAILABLE"
    assert queued["estimate_basis"] == "WAITING_FOR_CAPACITY"
