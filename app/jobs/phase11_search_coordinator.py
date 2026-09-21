"""Bounded production coordination for durable Phase 11 searches."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
import logging
import math
from pathlib import Path
from threading import Event, Lock
from typing import Any

from app.repositories.campaign_result_registry_repository import (
    CampaignResultRegistryRepository,
)
from app.services.phase11_result_contracts import Phase11RegistryStateError
from app.services.phase11_search_orchestration_service import (
    SearchOrchestrationOutcome,
    SnapshotMaterializer,
    execute_phase11_search_safely,
)


logger = logging.getLogger(__name__)

PHASE11_COORDINATOR_MAX_WORKERS = 2
PHASE11_COORDINATOR_POLL_INTERVAL_SECONDS = 5.0
PHASE11_COORDINATOR_MAX_TRACKED_RUNS = 100
PHASE11_COORDINATOR_QUERY_PAGE_SIZE = 100

_TERMINAL_STATUSES = frozenset({"COMPLETED", "BLOCKED", "FAILED"})
_WAITING_STATUSES = frozenset({"PHASE10_INTELLIGENCE"})

SearchRunner = Callable[..., SearchOrchestrationOutcome]


def _positive_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return value


class Phase11SearchCoordinator:
    """Run a bounded, deduplicated orchestration loop per durable search."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        materializer: SnapshotMaterializer,
        project_root: str | Path,
        max_workers: int = PHASE11_COORDINATOR_MAX_WORKERS,
        poll_interval_seconds: float = PHASE11_COORDINATOR_POLL_INTERVAL_SECONDS,
        max_tracked_runs: int = PHASE11_COORDINATOR_MAX_TRACKED_RUNS,
        runner: SearchRunner = execute_phase11_search_safely,
    ) -> None:
        workers = _positive_integer(max_workers, "max_workers")
        tracked = _positive_integer(max_tracked_runs, "max_tracked_runs")
        if tracked < workers:
            raise ValueError("max_tracked_runs must be at least max_workers.")
        if (
            isinstance(poll_interval_seconds, bool)
            or not isinstance(poll_interval_seconds, (int, float))
            or not math.isfinite(float(poll_interval_seconds))
            or float(poll_interval_seconds) <= 0
        ):
            raise ValueError("poll_interval_seconds must be a positive finite number.")
        if not callable(materializer):
            raise TypeError("materializer must be callable.")
        if not callable(runner):
            raise TypeError("runner must be callable.")

        self.database_path = Path(database_path).resolve()
        self.project_root = Path(project_root).resolve()
        self.materializer = materializer
        self.max_workers = workers
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.max_tracked_runs = tracked
        self._runner = runner
        self._repository = CampaignResultRegistryRepository(self.database_path)
        self._executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="phase11-search",
        )
        self._lock = Lock()
        self._shutdown_event = Event()
        self._accepting = True
        self._refilling = False
        self._active_search_ids: set[int] = set()
        self._futures: dict[int, Future[None]] = {}

    @property
    def active_search_ids(self) -> frozenset[int]:
        """Return a stable diagnostic snapshot of tracked search IDs."""

        with self._lock:
            return frozenset(self._active_search_ids)

    @property
    def is_accepting(self) -> bool:
        with self._lock:
            return self._accepting

    def _validate_submission(
        self, database_path: str | Path, search_run_id: int
    ) -> int:
        identifier = _positive_integer(search_run_id, "search_run_id")
        if Path(database_path).resolve() != self.database_path:
            raise ValueError("Search database does not match the configured coordinator.")
        return identifier

    def submit(self, database_path: str | Path, search_run_id: int) -> bool:
        """Schedule one durable search without waiting for its orchestration."""

        identifier = self._validate_submission(database_path, search_run_id)
        with self._lock:
            if not self._accepting:
                raise RuntimeError("Phase 11 search coordinator is shutting down.")
            if identifier in self._active_search_ids:
                return False
            if len(self._active_search_ids) >= self.max_tracked_runs:
                return False

        run = self._repository.fetch_search_run(identifier)
        if run is None:
            raise Phase11RegistryStateError("Search was not found.")
        if str(run["status"]) in _TERMINAL_STATUSES:
            return False

        with self._lock:
            if not self._accepting:
                raise RuntimeError("Phase 11 search coordinator is shutting down.")
            if identifier in self._active_search_ids:
                return False
            if len(self._active_search_ids) >= self.max_tracked_runs:
                return False
            # Reserve before executor submission so a racing request cannot
            # schedule the same durable run while its future is being created.
            self._active_search_ids.add(identifier)

        try:
            future = self._executor.submit(self._run_search, identifier)
        except Exception:
            with self._lock:
                self._active_search_ids.discard(identifier)
            raise

        with self._lock:
            # A very fast worker may already have completed and removed its
            # reservation. Never reintroduce a stale future in that race.
            if identifier in self._active_search_ids:
                self._futures[identifier] = future
        return True

    def _run_search(self, search_run_id: int) -> None:
        try:
            while not self._shutdown_event.is_set():
                outcome = self._runner(
                    self.database_path,
                    search_run_id,
                    materializer=self.materializer,
                    project_root=self.project_root,
                )
                if outcome.status in _TERMINAL_STATUSES:
                    return
                if (
                    outcome.status != "PROCESSING"
                    or outcome.waiting_on not in _WAITING_STATUSES
                ):
                    raise RuntimeError(
                        "Phase 11 search returned an unsupported non-terminal state."
                    )
                if self._shutdown_event.wait(self.poll_interval_seconds):
                    return
        except Exception as exc:
            logger.exception(
                "Phase 11 coordinator worker failed | search_run_id=%s exception_type=%s",
                search_run_id,
                type(exc).__name__,
            )
            self._fail_active_search_safely(search_run_id)
        finally:
            with self._lock:
                self._active_search_ids.discard(search_run_id)
                self._futures.pop(search_run_id, None)
                refill = self._accepting and not self._shutdown_event.is_set()
            if refill:
                self._refill_from_durable_state()

    def _fail_active_search_safely(self, search_run_id: int) -> None:
        try:
            current = self._repository.fetch_search_run(search_run_id)
            if current is not None and current["status"] in {"QUEUED", "PROCESSING"}:
                self._repository.fail_search_run(search_run_id)
        except Exception:
            logger.exception(
                "Phase 11 coordinator could not persist safe failure | search_run_id=%s",
                search_run_id,
            )

    def _refill_from_durable_state(self) -> int:
        with self._lock:
            if (
                not self._accepting
                or self._shutdown_event.is_set()
                or self._refilling
            ):
                return 0
            self._refilling = True

        scheduled = 0
        try:
            for status in ("PROCESSING", "QUEUED"):
                before_search_run_id: int | None = None
                while True:
                    with self._lock:
                        capacity = self.max_tracked_runs - len(
                            self._active_search_ids
                        )
                        if capacity <= 0 or not self._accepting:
                            return scheduled
                    page = self._repository.list_search_runs(
                        status=status,
                        limit=PHASE11_COORDINATOR_QUERY_PAGE_SIZE,
                        before_search_run_id=before_search_run_id,
                    )
                    if not page:
                        break
                    for run in page:
                        try:
                            if self.submit(
                                self.database_path, int(run["search_run_id"])
                            ):
                                scheduled += 1
                        except Exception:
                            logger.exception(
                                "Phase 11 durable search scheduling failed | search_run_id=%s",
                                run.get("search_run_id"),
                            )
                        with self._lock:
                            if len(self._active_search_ids) >= self.max_tracked_runs:
                                return scheduled
                    if len(page) < PHASE11_COORDINATOR_QUERY_PAGE_SIZE:
                        break
                    before_search_run_id = int(page[-1]["search_run_id"])
            return scheduled
        finally:
            with self._lock:
                self._refilling = False

    def resume_durable_searches(self) -> int:
        """Boundedly schedule durable PROCESSING and QUEUED searches."""

        return self._refill_from_durable_state()

    def shutdown(self, *, wait: bool = True) -> None:
        """Stop accepting work, wake pollers, and close the bounded pool."""

        with self._lock:
            if not self._accepting:
                return
            self._accepting = False
            self._shutdown_event.set()
            futures = tuple(self._futures.values())
        for future in futures:
            if not future.running():
                future.cancel()
        self._executor.shutdown(wait=wait, cancel_futures=True)
        with self._lock:
            for identifier, future in tuple(self._futures.items()):
                if future.done() or future.cancelled():
                    self._futures.pop(identifier, None)
                    self._active_search_ids.discard(identifier)


__all__ = (
    "PHASE11_COORDINATOR_MAX_TRACKED_RUNS",
    "PHASE11_COORDINATOR_MAX_WORKERS",
    "PHASE11_COORDINATOR_POLL_INTERVAL_SECONDS",
    "Phase11SearchCoordinator",
)
