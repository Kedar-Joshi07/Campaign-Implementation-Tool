from __future__ import annotations

from threading import Event
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.jobs.phase11_search_coordinator import (
    PHASE11_COORDINATOR_MAX_TRACKED_RUNS,
    PHASE11_COORDINATOR_MAX_WORKERS,
    PHASE11_COORDINATOR_POLL_INTERVAL_SECONDS,
    Phase11SearchCoordinator,
)
from app.main import app
from app.services import potential_customer_search_submission_service as submission
from app.services.phase11_search_orchestration_service import (
    SearchOrchestrationOutcome,
)
from tests.test_phase11_search_result_registry import _search, case


def _wait_until(predicate, *, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition was not reached within the bounded timeout")


def _coordinator(case, runner, **overrides) -> Phase11SearchCoordinator:
    path = case[0]
    options = {
        "materializer": lambda *_args, **_kwargs: 1,
        "project_root": path.parent,
        "max_workers": 1,
        "poll_interval_seconds": 0.01,
        "max_tracked_runs": 4,
        "runner": runner,
    }
    options.update(overrides)
    return Phase11SearchCoordinator(path, **options)


def test_production_coordinator_defaults_are_frozen() -> None:
    assert PHASE11_COORDINATOR_MAX_WORKERS == 2
    assert PHASE11_COORDINATOR_POLL_INTERVAL_SECONDS == 5.0
    assert PHASE11_COORDINATOR_MAX_TRACKED_RUNS == 100


@pytest.mark.parametrize(
    "overrides",
    (
        {"max_workers": 0},
        {"max_workers": True},
        {"poll_interval_seconds": 0},
        {"poll_interval_seconds": float("nan")},
        {"max_workers": 2, "max_tracked_runs": 1},
    ),
)
def test_coordinator_rejects_unbounded_or_invalid_configuration(
    case, overrides
) -> None:
    with pytest.raises(ValueError):
        _coordinator(case, lambda *_args, **_kwargs: None, **overrides)


def test_submit_deduplicates_one_active_search_and_cleans_registry(case) -> None:
    repository = case[3]
    search_run_id = _search(case)
    started = Event()
    release = Event()
    calls: list[int] = []

    def runner(_path, identifier, **_kwargs):
        calls.append(identifier)
        started.set()
        assert release.wait(1.0)
        repository.fail_search_run(identifier, blocked=True)
        return SearchOrchestrationOutcome(identifier, "BLOCKED")

    coordinator = _coordinator(case, runner)
    try:
        assert coordinator.submit(case[0], search_run_id) is True
        assert started.wait(1.0)
        assert coordinator.submit(case[0], search_run_id) is False
        assert coordinator.active_search_ids == {search_run_id}
        release.set()
        _wait_until(lambda: not coordinator.active_search_ids)
        assert calls == [search_run_id]
        assert repository.fetch_search_run(search_run_id)["status"] == "BLOCKED"
    finally:
        release.set()
        coordinator.shutdown()


def test_terminal_search_is_ignored_without_creating_a_future(case) -> None:
    repository = case[3]
    search_run_id = _search(case)
    repository.fail_search_run(search_run_id, blocked=True)
    called = False

    def runner(*_args, **_kwargs):
        nonlocal called
        called = True
        return SearchOrchestrationOutcome(search_run_id, "BLOCKED")

    coordinator = _coordinator(case, runner)
    try:
        assert coordinator.submit(case[0], search_run_id) is False
        assert coordinator.active_search_ids == frozenset()
        assert called is False
    finally:
        coordinator.shutdown()


def test_worker_polls_phase10_then_reaches_terminal_state(case) -> None:
    repository = case[3]
    search_run_id = _search(case)
    calls = 0

    def runner(_path, identifier, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            repository.mark_processing(identifier)
            return SearchOrchestrationOutcome(
                identifier, "PROCESSING", waiting_on="PHASE10_INTELLIGENCE"
            )
        repository.fail_search_run(identifier)
        return SearchOrchestrationOutcome(identifier, "FAILED")

    coordinator = _coordinator(case, runner)
    try:
        assert coordinator.submit(case[0], search_run_id) is True
        _wait_until(lambda: repository.fetch_search_run(search_run_id)["status"] == "FAILED")
        _wait_until(lambda: not coordinator.active_search_ids)
        assert calls == 2
    finally:
        coordinator.shutdown()


def test_unexpected_runner_exception_fails_safely_and_cleans_registry(case) -> None:
    repository = case[3]
    search_run_id = _search(case)

    def runner(*_args, **_kwargs):
        raise RuntimeError("private@example.test must not be persisted")

    coordinator = _coordinator(case, runner)
    try:
        assert coordinator.submit(case[0], search_run_id) is True
        _wait_until(lambda: repository.fetch_search_run(search_run_id)["status"] == "FAILED")
        _wait_until(lambda: not coordinator.active_search_ids)
        row = repository.fetch_search_run(search_run_id)
        assert "private@" not in str(row)
        assert row["safe_error_message"] == "The search could not be completed. Please try again."
    finally:
        coordinator.shutdown()


def test_shutdown_wakes_poller_preserves_durable_state_and_rejects_submit(case) -> None:
    repository = case[3]
    search_run_id = _search(case)
    waiting = Event()

    def runner(_path, identifier, **_kwargs):
        repository.mark_processing(identifier)
        waiting.set()
        return SearchOrchestrationOutcome(
            identifier, "PROCESSING", waiting_on="PHASE10_INTELLIGENCE"
        )

    coordinator = _coordinator(
        case,
        runner,
        poll_interval_seconds=30.0,
    )
    assert coordinator.submit(case[0], search_run_id) is True
    assert waiting.wait(1.0)
    started = time.monotonic()
    coordinator.shutdown(wait=True)
    assert time.monotonic() - started < 1.0
    assert repository.fetch_search_run(search_run_id)["status"] == "PROCESSING"
    assert coordinator.active_search_ids == frozenset()
    with pytest.raises(RuntimeError, match="shutting down"):
        coordinator.submit(case[0], search_run_id)


def test_coordinator_rejects_a_different_database(case, tmp_path: Path) -> None:
    search_run_id = _search(case)
    coordinator = _coordinator(
        case,
        lambda *_args, **_kwargs: SearchOrchestrationOutcome(
            search_run_id, "BLOCKED"
        ),
    )
    try:
        with pytest.raises(ValueError, match="does not match"):
            coordinator.submit(tmp_path / "other.db", search_run_id)
    finally:
        coordinator.shutdown()


def test_real_application_lifespan_configures_and_resets_executor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = initialize_database(tmp_path / "runtime-composition.db")
    monkeypatch.setattr("app.main.DATABASE_PATH", database_path)
    app.dependency_overrides[get_database_path] = lambda: database_path
    submission.reset_phase11_search_executor()
    try:
        with TestClient(app) as client:
            assert submission.PHASE11_SEARCH_EXECUTOR is not None
            response = client.get("/api/potential-customer-search/options")
            assert response.status_code == 200
            assert response.json()["workflow_available"] is True
        assert submission.PHASE11_SEARCH_EXECUTOR is None
    finally:
        app.dependency_overrides.clear()
        submission.reset_phase11_search_executor()
