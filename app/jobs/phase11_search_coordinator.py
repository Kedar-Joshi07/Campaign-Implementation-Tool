"""Bounded production coordination for durable Phase 11 searches."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
import logging
import math
import secrets
from pathlib import Path
from threading import Event, Lock, Thread, current_thread
from typing import Any
from app.database.connection import get_connection

from app.repositories.campaign_result_registry_repository import (
    AttemptExecutionFence,
    CampaignResultRegistryRepository,
)
from app.services.phase11_result_contracts import Phase11RegistryStateError
from app.selection_contracts import BUYER_SIMILARITY_SELECTION_CONTRACT_VERSION
from app.services.phase11_search_orchestration_service import (
    SearchOrchestrationOutcome,
    SnapshotMaterializer,
    execute_phase11_search_safely,
)
from app.services.buyer_similarity_search_orchestration_service import (
    execute_similarity_search_safely,
)


logger = logging.getLogger(__name__)

PHASE11_COORDINATOR_MAX_WORKERS = 2
PHASE11_COORDINATOR_POLL_INTERVAL_SECONDS = 5.0
PHASE11_COORDINATOR_MAX_TRACKED_RUNS = 100
PHASE11_COORDINATOR_QUERY_PAGE_SIZE = 100

_TERMINAL_STATUSES = frozenset({"COMPLETED", "BLOCKED", "FAILED"})
_WAITING_STATUSES = frozenset({"PHASE10_INTELLIGENCE", "SIMILARITY_DEPENDENCY", "CANCELLED"})

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
        self._lease_owner = f"phase11-coordinator-{secrets.token_hex(12)}"
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
        self._recovery_thread: Thread | None = None

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

        from app.qa_guard import assert_qa_runtime
        assert_qa_runtime(database_path, project_root=self.project_root,
                          operation="phase11_search_dispatch", record_admission=True)

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
        version = str(run.get("selection_contract_version") or "1")
        if version not in {"1", "2", BUYER_SIMILARITY_SELECTION_CONTRACT_VERSION}:
            raise Phase11RegistryStateError("Unsupported search selection contract.")
        if str(run["status"]) in _TERMINAL_STATUSES:
            return False
        if version == BUYER_SIMILARITY_SELECTION_CONTRACT_VERSION:
            # A migrated/fixture database can have campaign rows without the
            # governed import provenance needed to train a buyer profile. Keep
            # its durable request queued until imports have been registered.
            with get_connection(self.database_path) as connection:
                sources = connection.execute(
                    "SELECT COUNT(DISTINCT dataset_name) FROM data_import_runs "
                    "WHERE status='COMPLETED' AND dataset_name IN "
                    "('customers','campaign_sales','demographics')"
                ).fetchone()[0]
            if sources != 3:
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
            fence = self._repository.claim_search_attempt(
                identifier, lease_owner=self._lease_owner
            )
            future = self._executor.submit(self._run_search, identifier, fence)
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

    def _run_search(
        self,
        search_run_id: int,
        fence: AttemptExecutionFence,
    ) -> None:
        try:
            while not self._shutdown_event.is_set():
                run = self._repository.fetch_search_run(search_run_id)
                if run is None:
                    raise Phase11RegistryStateError("Search was not found.")
                if str(run.get("selection_contract_version") or "1") == BUYER_SIMILARITY_SELECTION_CONTRACT_VERSION:
                    outcome = execute_similarity_search_safely(
                        self.database_path, search_run_id, **fence.as_kwargs(),
                        project_root=self.project_root,
                        cancellation_check=self._shutdown_event.is_set,
                    )
                else:
                    outcome = self._runner(
                        self.database_path,
                        search_run_id,
                        **fence.as_kwargs(),
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
            self._fail_active_search_safely(search_run_id, fence)
        finally:
            if self._shutdown_event.is_set():
                current = self._repository.fetch_search_run(search_run_id)
                if current is not None and current["status"] in {"QUEUED", "PROCESSING"}:
                    try:
                        self._repository.release_search_attempt_claim(
                            search_run_id, **fence.as_kwargs()
                        )
                    except Phase11RegistryStateError:
                        logger.info(
                            "Phase 11 shutdown claim was already released or fenced | "
                            "search_run_id=%s",
                            search_run_id,
                        )
            with self._lock:
                self._active_search_ids.discard(search_run_id)
                self._futures.pop(search_run_id, None)
                refill = self._accepting and not self._shutdown_event.is_set()
            if refill:
                self._refill_from_durable_state()

    def _fail_active_search_safely(
        self,
        search_run_id: int,
        fence: AttemptExecutionFence,
    ) -> None:
        try:
            current = self._repository.fetch_search_run(search_run_id)
            if current is not None and current["status"] in {"QUEUED", "PROCESSING"}:
                self._repository.fail_search_run(
                    search_run_id, **fence.as_kwargs()
                )
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
                        except Phase11RegistryStateError as exc:
                            if str(exc) == "Search attempt is already owned by a live worker.":
                                # A prior process can have exited without releasing
                                # its fenced lease. Revisit it after the stale window;
                                # never steal a genuinely live worker's token.
                                logger.debug(
                                    "Phase 11 recovery awaits lease expiry | search_run_id=%s",
                                    run.get("search_run_id"),
                                )
                            else:
                                logger.exception(
                                    "Phase 11 durable search scheduling failed | search_run_id=%s",
                                    run.get("search_run_id"),
                                )
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

        scheduled = self._refill_from_durable_state()
        with self._lock:
            if self._accepting and self._recovery_thread is None:
                self._recovery_thread = Thread(
                    target=self._monitor_durable_searches,
                    name="phase11-durable-recovery",
                    daemon=True,
                )
                self._recovery_thread.start()
        return scheduled

    def _monitor_durable_searches(self) -> None:
        # An abruptly stopped process leaves a valid lease until its heartbeat
        # goes stale. Startup's one-shot refill alone cannot recover that run.
        interval = max(0.05, min(self.poll_interval_seconds * 3.0, 15.0))
        while not self._shutdown_event.wait(interval):
            try:
                self._refill_from_durable_state()
            except Exception:
                logger.exception("Phase 11 durable recovery sweep failed")

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
        recovery_thread = self._recovery_thread
        if recovery_thread is not None and recovery_thread is not current_thread():
            recovery_thread.join(timeout=min(self.poll_interval_seconds, 15.0) + 1.0)
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
