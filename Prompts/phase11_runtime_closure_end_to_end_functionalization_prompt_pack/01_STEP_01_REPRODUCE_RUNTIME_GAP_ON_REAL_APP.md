# Step 1 — Reproduce the Runtime Gap on the Real App

Start from the exact baseline SHA.

Use the documented normal command:
`python -m uvicorn app.main:app`

Do NOT inject or monkeypatch a Phase 11 executor.

Verify and record:
- `/api/potential-customer-search/options`
- `workflow_available`
- a valid POST search submission
- resulting search-run status
- whether the run becomes BLOCKED because `PHASE11_SEARCH_EXECUTOR` is None
- startup logs
- whether `resume_phase11_searches` is invoked anywhere
- whether ResultSnapshotMaterializer is composed into the real runtime

Also inspect:
- `app/main.py`
- `potential_customer_search_submission_service.py`
- `phase11_search_orchestration_service.py`
- Step19/20 certification server wiring

Create:
`docs/evidence/phase11_runtime_closure/01_REAL_APP_GAP_REPRODUCTION.md`

The report must explicitly contrast:
- normal `app.main`
- special certification server composition.

No fix yet. STOP.
