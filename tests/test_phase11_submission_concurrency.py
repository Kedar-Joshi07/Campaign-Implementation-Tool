"""Step 5: intentional submissions and same-run concurrency safety."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event, Lock
import time

from app.database.connection import get_connection
from app.jobs.phase11_search_coordinator import Phase11SearchCoordinator
from app.services.phase11_result_snapshot_service import ResultSnapshotMaterializer
from app.services.phase11_search_orchestration_service import (
    SearchOrchestrationOutcome,
    execute_phase11_search_safely,
)
from tests.test_phase11_search_result_registry import _search, case
from tests.test_phase11_smart_reuse_engine import (
    fixed_membership_source,
    fixed_reader,
    generation,
    ready_response,
    table_counts,
)


def _wait_until(predicate, *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition was not reached within the bounded timeout")


def _coordinator(
    case,
    runner,
    *,
    materializer=None,
    workers: int = 2,
) -> Phase11SearchCoordinator:
    return Phase11SearchCoordinator(
        case[0],
        materializer=materializer or (lambda *_args, **_kwargs: 1),
        project_root=case[0].parent,
        max_workers=workers,
        poll_interval_seconds=0.01,
        max_tracked_runs=8,
        runner=runner,
    )


def _real_reuse_runner(case, membership_source, calls):
    current_generation = generation(case)
    response = ready_response(current_generation)

    def run(database_path, search_run_id, **kwargs):
        with calls["lock"]:
            calls["ids"].append(search_run_id)
        return execute_phase11_search_safely(
            database_path,
            search_run_id,
            phase10_reader=fixed_reader(response),
            membership_source=membership_source,
            **kwargs,
        )

    return run


def test_startup_resume_racing_request_submit_starts_one_loop(case) -> None:
    repository = case[3]
    search_run_id = _search(case)
    race = Barrier(2)
    started = Event()
    release = Event()
    calls: list[int] = []

    def runner(_path, identifier, **_kwargs):
        calls.append(identifier)
        started.set()
        assert release.wait(2.0)
        repository.fail_search_run(identifier, blocked=True)
        return SearchOrchestrationOutcome(identifier, "BLOCKED")

    coordinator = _coordinator(case, runner, workers=1)
    try:
        def request_submit():
            race.wait(timeout=2.0)
            return coordinator.submit(case[0], search_run_id)

        def startup_resume():
            race.wait(timeout=2.0)
            return coordinator.resume_durable_searches()

        with ThreadPoolExecutor(max_workers=2) as executor:
            direct = executor.submit(request_submit)
            resumed = executor.submit(startup_resume)
            direct_result = direct.result(timeout=2.0)
            resumed_count = resumed.result(timeout=2.0)

        assert int(direct_result) + resumed_count == 1
        assert started.wait(1.0)
        assert coordinator.active_search_ids == {search_run_id}
        # Repeated request/status-side reconciliation cannot create another loop.
        assert coordinator.submit(case[0], search_run_id) is False
        assert coordinator.resume_durable_searches() == 0
        release.set()
        _wait_until(
            lambda: repository.fetch_search_run(search_run_id)["status"]
            == "BLOCKED"
        )
        _wait_until(lambda: not coordinator.active_search_ids)
        assert calls == [search_run_id]
    finally:
        release.set()
        coordinator.shutdown()


def test_concurrent_identical_intentional_searches_publish_one_snapshot(case) -> None:
    path, _ids, _values, repository = case
    first_id = _search(case, campaign_name="First intentional submission")
    second_id = _search(case, campaign_name="Second intentional submission")
    publication_race = Barrier(2)
    calls = {"ids": [], "lock": Lock()}
    before_heavy = table_counts(path)

    def synchronized_members(*_args):
        publication_race.wait(timeout=3.0)
        return fixed_membership_source()

    coordinator = _coordinator(
        case,
        _real_reuse_runner(case, synchronized_members, calls),
        materializer=ResultSnapshotMaterializer(path.parent),
    )
    try:
        assert coordinator.submit(path, first_id) is True
        assert coordinator.submit(path, second_id) is True
        _wait_until(
            lambda: all(
                repository.fetch_search_run(identifier)["status"] == "COMPLETED"
                for identifier in (first_id, second_id)
            )
        )
        _wait_until(lambda: not coordinator.active_search_ids)

        first = repository.fetch_search_run(first_id)
        second = repository.fetch_search_run(second_id)
        assert first_id != second_id
        assert first["result_snapshot_id"] == second["result_snapshot_id"]
        assert first["generation_id"] == second["generation_id"]
        with get_connection(path) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM campaign_result_snapshots"
            ).fetchone()[0] == 1
        assert sorted(calls["ids"]) == sorted([first_id, second_id])
        assert table_counts(path) == before_heavy

        # A later intentional identical POST remains a separate history row and
        # now takes the explicit exact-result reuse path.
        third_id = _search(case, campaign_name="Third intentional submission")
        assert coordinator.submit(path, third_id) is True
        _wait_until(
            lambda: repository.fetch_search_run(third_id)["status"] == "COMPLETED"
        )
        third = repository.fetch_search_run(third_id)
        assert third["result_source"] == "EXACT_RESULT_REUSE"
        assert third["result_snapshot_id"] == first["result_snapshot_id"]
        with get_connection(path) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM campaign_result_snapshots"
            ).fetchone()[0] == 1
        assert table_counts(path) == before_heavy
    finally:
        coordinator.shutdown()


def test_different_searches_share_generation_without_duplicate_scoring(case) -> None:
    path, _ids, _values, repository = case
    ohio_id = _search(
        case,
        campaign_name="Ohio audience",
        targeting_criteria={"states": ["Ohio"]},
        filter_branches=[{"state": ["Ohio"]}],
    )
    texas_id = _search(
        case,
        campaign_name="Texas audience",
        targeting_criteria={"states": ["Texas"]},
        filter_branches=[{"state": ["Texas"]}],
    )
    publication_race = Barrier(2)
    calls = {"ids": [], "lock": Lock()}
    before_heavy = table_counts(path)

    def synchronized_members(*_args):
        publication_race.wait(timeout=3.0)
        return fixed_membership_source()

    coordinator = _coordinator(
        case,
        _real_reuse_runner(case, synchronized_members, calls),
        materializer=ResultSnapshotMaterializer(path.parent),
    )
    try:
        assert coordinator.submit(path, ohio_id) is True
        assert coordinator.submit(path, texas_id) is True
        _wait_until(
            lambda: all(
                repository.fetch_search_run(identifier)["status"] == "COMPLETED"
                for identifier in (ohio_id, texas_id)
            )
        )
        ohio = repository.fetch_search_run(ohio_id)
        texas = repository.fetch_search_run(texas_id)
        assert ohio["generation_id"] == texas["generation_id"]
        assert ohio["scoring_run_id"] == texas["scoring_run_id"]
        assert ohio["result_snapshot_id"] != texas["result_snapshot_id"]
        with get_connection(path) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM campaign_result_snapshots"
            ).fetchone()[0] == 2
        assert table_counts(path) == before_heavy
        assert sorted(calls["ids"]) == sorted([ohio_id, texas_id])
    finally:
        coordinator.shutdown()
