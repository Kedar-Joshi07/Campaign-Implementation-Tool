from __future__ import annotations

from pathlib import Path
from threading import Event
import time

import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.database.schema import initialize_database
from app.dependencies import get_database_path
from app.jobs.phase11_search_coordinator import Phase11SearchCoordinator
from app.main import app
from app.services import potential_customer_search_submission_service as submission
from app.services.phase11_search_orchestration_service import (
    SearchOrchestrationOutcome,
    execute_phase11_search_safely,
)
from tests.test_phase11_search_result_registry import (
    _complete,
    _search,
    _snapshot,
    case,
)
from tests.test_phase11_smart_reuse_engine import (
    DeterministicMaterializer,
    fixed_membership_source,
    fixed_reader,
    generation,
    ready_response,
)


def _wait_until(predicate, *, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition was not reached within the bounded timeout")


def _coordinator(case, runner, *, materializer=None, poll=0.01):
    path = case[0]
    return Phase11SearchCoordinator(
        path,
        materializer=materializer or (lambda *_args, **_kwargs: 1),
        project_root=path.parent,
        max_workers=1,
        poll_interval_seconds=poll,
        max_tracked_runs=10,
        runner=runner,
    )


def test_queued_search_is_scheduled_without_processing_inside_startup(case) -> None:
    repository = case[3]
    search_run_id = _search(case)
    started = Event()
    release = Event()

    def runner(_path, identifier, **_kwargs):
        started.set()
        assert release.wait(2.0)
        repository.fail_search_run(identifier, blocked=True)
        return SearchOrchestrationOutcome(identifier, "BLOCKED")

    coordinator = _coordinator(case, runner)
    try:
        scheduled = coordinator.resume_durable_searches()
        assert scheduled == 1
        assert started.wait(1.0)
        # The scheduling call returned while the worker was deliberately
        # blocked, proving startup did not run orchestration synchronously.
        assert release.is_set() is False
        assert coordinator.active_search_ids == {search_run_id}
        release.set()
        _wait_until(
            lambda: repository.fetch_search_run(search_run_id)["status"]
            == "BLOCKED"
        )
    finally:
        release.set()
        coordinator.shutdown()


def test_processing_search_survives_shutdown_and_resumes_once_after_restart(case) -> None:
    repository = case[3]
    search_run_id = _search(case)
    first_pass = Event()

    def waiting_runner(_path, identifier, **_kwargs):
        if repository.fetch_search_run(identifier)["status"] == "QUEUED":
            repository.mark_processing(identifier)
        first_pass.set()
        return SearchOrchestrationOutcome(
            identifier,
            "PROCESSING",
            waiting_on="PHASE10_INTELLIGENCE",
        )

    app_a = _coordinator(case, waiting_runner, poll=30.0)
    assert app_a.resume_durable_searches() == 1
    assert first_pass.wait(1.0)
    app_a.shutdown(wait=True)
    assert repository.fetch_search_run(search_run_id)["status"] == "PROCESSING"

    resumed = Event()
    release = Event()
    calls: list[int] = []

    def resumed_runner(_path, identifier, **_kwargs):
        calls.append(identifier)
        resumed.set()
        assert release.wait(2.0)
        repository.fail_search_run(identifier, blocked=True)
        return SearchOrchestrationOutcome(identifier, "BLOCKED")

    app_b = _coordinator(case, resumed_runner)
    try:
        assert app_b.resume_durable_searches() == 1
        assert resumed.wait(1.0)
        # A second startup/request race attaches to the active ID rather than
        # creating a duplicate coordinator loop.
        assert app_b.resume_durable_searches() == 0
        release.set()
        _wait_until(
            lambda: repository.fetch_search_run(search_run_id)["status"]
            == "BLOCKED"
        )
        assert calls == [search_run_id]
    finally:
        release.set()
        app_b.shutdown()


def test_processing_search_retries_snapshot_publication_once_and_completes(case) -> None:
    path, _, _, repository = case
    search_run_id = _search(case)
    repository.mark_processing(search_run_id)
    current_generation = generation(case)
    materializer = DeterministicMaterializer(path.parent, repository)

    def real_runner(database_path, identifier, **kwargs):
        return execute_phase11_search_safely(
            database_path,
            identifier,
            phase10_reader=fixed_reader(ready_response(current_generation)),
            membership_source=fixed_membership_source,
            **kwargs,
        )

    coordinator = _coordinator(
        case,
        real_runner,
        materializer=materializer,
    )
    try:
        assert coordinator.resume_durable_searches() == 1
        _wait_until(
            lambda: repository.fetch_search_run(search_run_id)["status"]
            == "COMPLETED"
        )
        _wait_until(lambda: not coordinator.active_search_ids)
        completed = repository.fetch_search_run(search_run_id)
        assert completed["result_snapshot_id"] is not None
        assert len(materializer.calls) == 1
        with get_connection(path) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM campaign_result_snapshots"
            ).fetchone()[0] == 1
        # Reconciliation is idempotent after the terminal transition.
        assert coordinator.resume_durable_searches() == 0
        assert len(materializer.calls) == 1
    finally:
        coordinator.shutdown()


def test_completed_blocked_and_failed_searches_are_not_resubmitted(case) -> None:
    repository = case[3]
    completed = _search(case)
    snapshot_id = _snapshot(case, completed)
    _complete(case, completed, snapshot_id)
    blocked = _search(case)
    repository.fail_search_run(blocked, blocked=True)
    failed = _search(case)
    repository.fail_search_run(failed)
    calls: list[int] = []

    def forbidden_runner(_path, identifier, **_kwargs):
        calls.append(identifier)
        raise AssertionError("terminal search must not be resumed")

    coordinator = _coordinator(case, forbidden_runner)
    try:
        assert coordinator.resume_durable_searches() == 0
        assert coordinator.active_search_ids == frozenset()
        assert calls == []
        assert repository.fetch_search_run(completed)["status"] == "COMPLETED"
        assert repository.fetch_search_run(blocked)["status"] == "BLOCKED"
        assert repository.fetch_search_run(failed)["status"] == "FAILED"
    finally:
        coordinator.shutdown()


def test_real_lifespan_orders_phase11_resume_after_phase10_before_exports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = initialize_database(tmp_path / "startup-order.db")
    events: list[str] = []

    class FakeCoordinator:
        max_workers = 2
        poll_interval_seconds = 5.0

        def __init__(self, *_args, **_kwargs):
            events.append("coordinator")

        def submit(self, *_args, **_kwargs):
            return True

        def resume_durable_searches(self):
            events.append("phase11")
            return 2

        def shutdown(self, *, wait):
            assert wait is True
            events.append("shutdown")

    monkeypatch.setattr("app.main.DATABASE_PATH", database_path)
    monkeypatch.setattr("app.main.ResultSnapshotMaterializer", lambda _root: object())
    monkeypatch.setattr("app.main.Phase11SearchCoordinator", FakeCoordinator)
    monkeypatch.setattr(
        "app.main.reconcile_stale_model_training_jobs",
        lambda _path: events.append("models") or 0,
    )
    monkeypatch.setattr(
        "app.main.reconcile_phase10_orchestrations",
        lambda *_args, **_kwargs: events.append("phase10") or 1,
    )
    monkeypatch.setattr(
        "app.main.reconcile_stale_campaign_export_events",
        lambda _path: events.append("campaign_exports") or 0,
    )
    monkeypatch.setattr(
        "app.main.reconcile_stale_result_export_events",
        lambda _path: events.append("result_exports") or 0,
    )
    monkeypatch.setattr(
        "app.main.shutdown_model_training_executor",
        lambda **_kwargs: events.append("phase10_shutdown"),
    )
    app.dependency_overrides[get_database_path] = lambda: database_path
    submission.reset_phase11_search_executor()
    try:
        with TestClient(app):
            assert submission.PHASE11_SEARCH_EXECUTOR is not None
        assert events.index("coordinator") < events.index("phase10")
        assert events.index("phase10") < events.index("phase11")
        assert events.index("phase11") < events.index("campaign_exports")
        assert events.index("phase11") < events.index("result_exports")
        assert events[-2:] == ["shutdown", "phase10_shutdown"]
        assert submission.PHASE11_SEARCH_EXECUTOR is None
    finally:
        app.dependency_overrides.clear()
        submission.reset_phase11_search_executor()
