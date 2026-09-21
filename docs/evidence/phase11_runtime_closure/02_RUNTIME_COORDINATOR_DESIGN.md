# Phase 11 Bounded Runtime Coordinator Design

## Scope and status

- Prompt: `02_STEP_02_DESIGN_BOUNDED_PHASE11_RUNTIME_COORDINATOR.md`
- Baseline: `9009e23b750000d3f3d29e09204281f3d301e640`
- Design status: **FROZEN FOR IMPLEMENTATION**
- Production module: `app/jobs/phase11_search_coordinator.py`
- Application wiring: deferred to Step 3

This document freezes the runtime design. Step 2 does not modify `app.main` or enable the Phase 11 workflow.

## Frozen configuration

| Setting | Frozen value | Reason |
|---|---:|---|
| Worker implementation | `ThreadPoolExecutor` | Phase 11 performs coordination, bounded polling, SQLite state transitions, and result materialization rather than model/scoring CPU work. |
| Worker count | `2` | One worker could sleep while waiting on Phase 10 and stall an unrelated exact-reuse/materialization run. More than two would add avoidable SQLite writer and snapshot-I/O contention. |
| Poll interval | `5.0` seconds | Keeps durable status reasonably current without tight-loop database polling. |
| Tracked work limit | `100` search runs | Bounds the executor backlog and in-memory active/future registry. Additional durable runs remain discoverable in SQLite and are refilled as capacity opens. |
| Startup query page size | `100` | Matches the repository's bounded history-query contract. |
| Terminal statuses | `COMPLETED`, `BLOCKED`, `FAILED` | These states are never advanced or resubmitted automatically. |
| Materializer | One `ResultSnapshotMaterializer(PROJECT_ROOT)` instance per application lifespan | Uses the real project root and existing immutable snapshot contract. |

The values are production defaults, not environment-driven tuning knobs in the first implementation. Tests may inject smaller intervals and fake collaborators through constructor arguments without changing production composition.

## Coordinator boundary

The coordinator owns only:

1. bounded worker execution;
2. one orchestration loop per durable `search_run_id`;
3. active-run deduplication;
4. bounded polling while Phase 10 is preparing intelligence;
5. supplying the real snapshot materializer;
6. startup discovery and scheduling of durable work;
7. safe cleanup and shutdown.

It does not own or reimplement:

- Modeling Context identity;
- historical compatibility;
- smart-reuse decisions;
- model training;
- full-universe scoring or ranking;
- result cache keys;
- membership filtering;
- snapshot validation/publication rules;
- omnichannel export contracts.

Those responsibilities remain in the existing Phase 10 and Phase 11 services.

## Proposed production interface

```python
class Phase11SearchCoordinator:
    def __init__(
        self,
        database_path: str | Path,
        *,
        materializer: SnapshotMaterializer,
        project_root: str | Path,
        max_workers: int = 2,
        poll_interval_seconds: float = 5.0,
        max_tracked_runs: int = 100,
        runner: SearchRunner = execute_phase11_search_safely,
    ) -> None: ...

    def submit(self, database_path: str | Path, search_run_id: int) -> bool: ...
    def resume_durable_searches(self) -> int: ...
    def shutdown(self, *, wait: bool = True) -> None: ...
```

`submit` retains the existing `Callable[[Path, int], None]` compatibility required by the submission service; its Boolean return value is optional information for direct callers and is ignored safely by the existing seam.

Constructor validation must reject Boolean/non-positive IDs or limits, non-finite/non-positive polling intervals, and a submitted database path that does not resolve to the coordinator's configured database.

## One-run execution loop

For each accepted `search_run_id`, a worker performs:

1. Exit before work if coordinator shutdown was requested.
2. Re-read the durable search through the existing orchestration service.
3. Call `execute_phase11_search_safely` with:
   - the configured database path;
   - the search ID;
   - the lifespan-owned `ResultSnapshotMaterializer(PROJECT_ROOT)`;
   - the real `PROJECT_ROOT`.
4. Stop immediately for `COMPLETED`, `BLOCKED`, or `FAILED`.
5. For a non-terminal `PROCESSING` outcome waiting on Phase 10, call `shutdown_event.wait(5.0)` rather than an unconditional sleep.
6. If the event was not set, repeat from the durable read.
7. In `finally`, remove the search ID from the active/future registry and trigger a bounded durable-queue refill.

No SQLite connection or transaction remains open during the five-second wait.

An unexpected non-terminal outcome without a supported `waiting_on` reason is treated as a coordinator failure, not polled forever.

## Active-run deduplication

The active registry is keyed by `search_run_id` and protected by one process-local `threading.Lock`.

Submission occurs in this order while holding the lock only for registry state:

1. Reject if shutdown has begun.
2. If the search ID is already active or queued in the executor, return `False` without creating another future.
3. Read enough durable state to reject a missing or terminal run.
4. Reserve the ID in the active set before calling `ThreadPoolExecutor.submit`.
5. If executor submission fails, remove the reservation and re-raise.
6. Store the future without allowing a fast worker completion to leave a stale active entry.

The implementation should use an active-set reservation plus a future map, or an equivalent placeholder strategy, to avoid the race where a very fast future completes before it is inserted into the map.

Two distinct intentional submissions have different search IDs and remain distinct history rows. Deduplication applies only to the same durable search ID.

## Bounded backlog and durable refill

`ThreadPoolExecutor` limits running threads but its internal queue is not size-bounded. The coordinator therefore limits its own active-plus-queued registry to 100 runs.

- If a direct submission arrives while the registry is full, the run remains durably `QUEUED` in SQLite and `submit` returns `False` promptly.
- Worker completion performs a bounded refill query, preferring `PROCESSING` and then `QUEUED` runs.
- Refill excludes IDs already present in the active registry.
- Refill adds only enough work to reach the 100-run tracked limit.
- Repeated refill pages allow more than 100 durable runs to drain without unbounded memory or threads.

The HTTP request never waits for queue space and never performs the Phase 11 orchestration loop itself.

## Startup and restart behavior

The required lifespan order is:

1. initialize/verify the database;
2. create `ResultSnapshotMaterializer(PROJECT_ROOT)`;
3. create the Phase 11 coordinator;
4. configure the submission service to use `coordinator.submit`;
5. reconcile stale model jobs;
6. reconcile Phase 10 orchestrations;
7. call `coordinator.resume_durable_searches()`;
8. reconcile campaign and result export events;
9. serve requests.

`resume_durable_searches` does not call the existing synchronous `resume_phase11_searches` loop. It uses repository reads only to discover `PROCESSING` first and then `QUEUED` runs, and schedules them into the bounded coordinator. This prevents application startup from processing a full search or 5M materialization inline.

Durable handling by state:

- `PROCESSING`: resubmit to the coordinator; orchestration re-reads Phase 10 and snapshot state.
- `QUEUED`: submit to the coordinator.
- `COMPLETED`: ignore; never recreate the snapshot.
- `BLOCKED` or `FAILED`: ignore unless a future explicit retry contract creates or resets durable work.

Startup scheduling racing with a new request is safe because both paths enter the same active-ID lock.

## Shutdown behavior

Shutdown is idempotent and ordered:

1. disconnect/reset the submission-service executor seam so new requests cannot enter this coordinator;
2. under the coordinator lock, stop accepting work;
3. set the shutdown event so polling waits wake immediately;
4. cancel futures that have not started;
5. let an already-running orchestration pass finish its atomic/durable work;
6. call executor shutdown with `wait=True` and `cancel_futures=True`;
7. clear only completed/cancelled in-memory registry entries;
8. shut down the existing Phase 10 process executor using its existing application behavior.

Runs whose queued futures are cancelled remain durably `QUEUED`; a later application startup discovers them. A run interrupted between bounded passes remains `PROCESSING` and is also resumed. No status is fabricated merely because the process is stopping.

`submit` after shutdown raises a stable `RuntimeError`; it never silently accepts work into a dead executor.

## Exception behavior

The primary runner is `execute_phase11_search_safely`, which already converts domain blocks to `BLOCKED`, unexpected orchestration/materialization failures to `FAILED`, and persists only safe registry messages.

The coordinator still has an outer exception boundary because executor, callback, or future-management failures can occur outside the service wrapper:

- log search ID and exception type without request payloads, PII, raw paths, or persisted exception text;
- if the run still exists in `QUEUED` or `PROCESSING`, attempt the existing safe `fail_search_run` transition;
- do not change an already-terminal run;
- keep the application and other workers alive;
- always clean the active registry in `finally`.

Failure to schedule from the HTTP seam is allowed to propagate to the existing submission boundary, which already preserves the run and converts an active run to safe `FAILED`. Startup scheduling failures are logged and leave durable state available for retry/restart.

## Phase 10 heavy-work ownership proof

The inspected production path is:

```text
Phase11 coordinator thread
  -> execute_phase11_search_safely
  -> execute_phase11_search
  -> prepare_phase10_targeting_intelligence when needed
  -> prepare_phase10_orchestration
  -> submit_phase10_orchestration_job
  -> existing ProcessPoolExecutor(max_workers=1)
  -> run_phase10_orchestration_job
```

The coordinator does not import or call model-training, prospect-scoring, audience-preparation, or Phase 10 worker functions. It does not call `Future.result()` and does not wait synchronously for the ProcessPool. It observes Phase 10 through durable API/repository state on later five-second passes.

When Phase 10 determines that every component is reusable, its existing service may finalize the reusable orchestration synchronously. That path is metadata/currentness work, not a new 5M model/scoring build.

The single-worker ProcessPool continues to have one owner: Phase 10's existing job executor. Therefore the coordinator cannot create a recursive submit/wait deadlock.

## SQLite contention analysis

Current SQLite behavior provides:

- a new connection per repository operation;
- WAL journal mode;
- foreign-key enforcement;
- a 5,000 ms busy timeout;
- explicit `BEGIN IMMEDIATE` only around bounded registry writes.

Phase 11 passes perform short state reads/writes, but snapshot membership reads and artifact publication may overlap Phase 10 state writes. SQLite still permits only one writer at a time. The Step 1 real options request also demonstrated that canonical 5M scans are materially expensive.

Two coordinator workers are the selected balance:

- better progress than one worker when one search is in a polling wait or materialization pass;
- bounded concurrency for independent reuse/search runs;
- no large fan-out of full-dataset readers;
- limited competition for SQLite's single writer and filesystem snapshot publication.

The coordinator lock is never held during database access, materialization, or polling. It protects only the small in-memory registry. No broad database lock is added.

## Required implementation tests for Step 3+

Focused tests must cover:

- constructor validation and two-worker configuration;
- one accepted run;
- duplicate same-ID submission;
- two different IDs;
- terminal-run ignore;
- tracked-work limit and durable refill;
- Phase 10 waiting followed by completion;
- shutdown waking a polling worker;
- queued-future cancellation with durable state preserved;
- submit after shutdown;
- runner exception and safe cleanup;
- fast-future completion race;
- startup `PROCESSING`/`QUEUED` discovery;
- `COMPLETED`/`BLOCKED`/`FAILED` exclusion;
- proof that no ProcessPool `.result()` or heavy worker call exists in the coordinator.

## Decision

**PASS - bounded production coordinator design is frozen.**

Step 3 may implement this design and compose it into the real FastAPI lifespan. No coordinator or application wiring was implemented in Step 2.
