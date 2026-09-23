"""Durable Phase 11 lifecycle, truthful progress, ETA, and issue contracts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from app.database.connection import get_connection
from app.services.phase11_result_contracts import (
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
        run, runtime, now=started + timedelta(seconds=100)
    )
    assert projected["estimated_seconds_remaining_low"] == 65
    assert projected["estimated_seconds_remaining_high"] == 175
    assert projected["estimate_confidence"] == "MEDIUM"
    assert projected["estimate_basis"] == "CURRENT_RUN_OBSERVED_RATE"

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
