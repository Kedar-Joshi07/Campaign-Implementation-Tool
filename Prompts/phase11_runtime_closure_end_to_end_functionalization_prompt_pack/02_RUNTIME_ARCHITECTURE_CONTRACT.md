# Runtime Architecture Contract

Target startup:
FastAPI lifespan
→ initialize DB
→ create ResultSnapshotMaterializer
→ create bounded Phase11 Search Coordinator
→ connect submission executor callback
→ reconcile model jobs
→ reconcile Phase10 orchestrations
→ resume Phase11 QUEUED/PROCESSING runs
→ reconcile legacy/result exports
→ serve.

Recommended module:
`app/jobs/phase11_search_coordinator.py`

Coordinator responsibilities:
- bounded ThreadPoolExecutor or equivalent light pool;
- submit one orchestration loop per search_run_id;
- active-search deduplication;
- call `execute_phase11_search_safely`;
- poll boundedly while waiting on Phase10;
- provide real ResultSnapshotMaterializer;
- clean shutdown;
- restart resume.

Domain logic stays in existing services.

Prefer 1 or 2 coordinator workers based on SQLite contention evidence.
Heavy ML/scoring stays under Phase10.

One loop:
1. call execute_phase11_search_safely
2. stop on COMPLETED/BLOCKED/FAILED
3. if waiting on Phase10, sleep configured poll interval
4. repeat.

Duplicate submission of the same search_run_id must attach/ignore safely, never spawn duplicate loops.
