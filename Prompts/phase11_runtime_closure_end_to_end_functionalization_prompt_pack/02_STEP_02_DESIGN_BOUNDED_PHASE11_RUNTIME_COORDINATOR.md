# Step 2 — Design the Bounded Phase 11 Runtime Coordinator

Implement a focused coordinator design before wiring it into app.main.

Recommended module:
`app/jobs/phase11_search_coordinator.py`

Freeze:
- worker count
- poll interval
- active-run deduplication behavior
- startup resume behavior
- shutdown behavior
- exception behavior

The coordinator must call existing:
`execute_phase11_search_safely(...)`

with a real:
`ResultSnapshotMaterializer(PROJECT_ROOT)`.

Do not move smart-reuse logic into the coordinator.

Prove executor ownership:
- Phase11 coordinator handles light orchestration/polling/materialization.
- Phase10 retains model/scoring heavy work.
- existing single-worker ProcessPool is not recursively awaited by Phase11 coordinator.

Add design notes for SQLite contention and justify worker count.

Create:
`docs/evidence/phase11_runtime_closure/02_RUNTIME_COORDINATOR_DESIGN.md`

STOP.
