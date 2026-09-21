# Step 3 — Implement Runtime Coordinator & Real app.main Composition

Implement the coordinator and connect it in the FastAPI lifespan.

At startup:
1. create the ResultSnapshotMaterializer;
2. create/start the Phase11 coordinator;
3. connect the submission-service executor seam to coordinator.submit;
4. prove `/options` now reports workflow_available=true.

Avoid fragile global mutation if a cleaner explicit configuration function can be introduced safely.
If retaining `PHASE11_SEARCH_EXECUTOR`, provide a production configuration function and reset it on shutdown.

Submission requirements:
- HTTP request persists the run;
- schedules coordinator work;
- returns promptly;
- does not wait for a full 5M build;
- does not spawn unbounded threads.

Coordinator requirements:
- active set/future map keyed by search_run_id;
- same run ID cannot schedule twice concurrently;
- terminal run is ignored safely;
- completion cleans active registry.

Add focused unit tests.

Create:
`docs/evidence/phase11_runtime_closure/03_RUNTIME_COMPOSITION.md`

STOP.
