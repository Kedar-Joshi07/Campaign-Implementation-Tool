# Phase 11 Real-App Runtime Gap Reproduction

## Scope and baseline

- Prompt: `01_STEP_01_REPRODUCE_RUNTIME_GAP_ON_REAL_APP.md`
- Date: 2026-09-20 (Asia/Calcutta)
- Branch: `main`
- Baseline and tested HEAD: `9009e23b750000d3f3d29e09204281f3d301e640`
- Runtime command: `python -m uvicorn app.main:app`
- Database: the normal configured `data/campaign_poc.db`
- Executor injection or monkeypatching: none
- Result: **runtime gap reproduced**

This step intentionally makes no application-code fix.

## Normal-runtime startup evidence

The normal application completed startup successfully. Its relevant log sequence was:

```text
Application starting | name=Campaign Implementation Intelligence version=0.1.0 environment=development
SQLite schema initialized or verified | path=data\campaign_poc.db version=18
Compute startup reconciliation completed | failed_stale_jobs=0
Phase 10 startup reconciliation completed | resumed_orchestrations=0
Campaign export startup reconciliation completed | reconciled_stale_exports=0
Result export startup reconciliation completed | reconciled_stale_exports=0
Application startup complete.
Uvicorn running on http://127.0.0.1:8000
```

There was no Phase 11 executor configuration, coordinator startup, materializer composition, or Phase 11 search-resume log entry.

The application was stopped normally after the reproduction. Its lifespan shutdown completed without an error.

## Options endpoint

Request:

```http
GET /api/potential-customer-search/options
```

Observed:

- HTTP status: `200`
- `workflow_available`: `false`
- export profiles returned: 10
- available export profiles: 10
- response was produced by the normal `app.main` runtime

The canonical 5M-backed options request took approximately 45 seconds. This is recorded as an observation only; it is not changed or diagnosed in Step 1.

## Valid submission and durable status

A valid EMAIL request was submitted using values returned by the live options endpoint, including product `PRD001`, campaign type `Retention`, campaign category `Retention Offer`, offer type `Loyalty Reward`, and export profile `EMAIL_CONTACT_V1`.

Request:

```http
POST /api/potential-customer-search/runs
```

Observed response:

```json
{
  "search_run_id": 11,
  "campaign_name": "Runtime gap reproduction 2026-09-20",
  "status": "BLOCKED",
  "created_at": "2026-09-20T15:08:32Z",
  "completed_at": "2026-09-20T15:08:32Z",
  "selected_count": null,
  "delivery_channel": "EMAIL",
  "export_profile": "EMAIL_CONTACT_V1",
  "safe_message": "Your search is saved. Targeting intelligence preparation is not connected in this release yet."
}
```

- HTTP status: `201`
- The submission created durable search run `11`.
- The run became `BLOCKED` immediately.
- The safe message explicitly reports that targeting-intelligence preparation is not connected.

A separate durable-status request confirmed the same result:

```http
GET /api/potential-customer-search/runs/11/status
```

- HTTP status: `200`
- status: `BLOCKED`
- selected count: `null`
- completed timestamp: `2026-09-20T15:08:32Z`

One earlier client attempt contained malformed JSON because PowerShell stripped curl quoting. It returned `422` before domain submission and did not create a search run. The valid request above is the reproduction result.

## Static wiring inspection

### `app/main.py`

The normal lifespan currently performs:

1. stale model-training reconciliation;
2. Phase 10 orchestration reconciliation;
3. stale campaign-export reconciliation;
4. stale Phase 11 result-export reconciliation;
5. model-training executor shutdown.

It does **not**:

- create a `ResultSnapshotMaterializer`;
- configure `PHASE11_SEARCH_EXECUTOR`;
- create a Phase 11 coordinator;
- call `resume_phase11_searches`;
- reset a Phase 11 executor during shutdown.

### `potential_customer_search_submission_service.py`

The production composition seam is declared as:

```python
PHASE11_SEARCH_EXECUTOR: SearchExecutor | None = None
```

`search_form_options` derives `workflow_available` directly from whether that variable is non-null. During submission, when it is `None`, the newly persisted run is immediately passed to `fail_search_run(..., blocked=True)`. `project_search_status` then returns the observed safe "not connected" message.

This exactly explains both the `workflow_available=false` options response and the immediate `BLOCKED` search run.

### `phase11_search_orchestration_service.py`

The existing domain engine is present:

- `execute_phase11_search` advances one bounded durable pass;
- `execute_phase11_search_safely` fails closed;
- `resume_phase11_searches` reads `PROCESSING` and `QUEUED` runs and advances them.

Repository-wide call inspection found `resume_phase11_searches` only in its definition and a unit test. It is not invoked by `app.main` or another production startup path.

The engine can wait on Phase 10, perform exact-result reuse, request result materialization, validate the snapshot, and complete a run. The missing part is normal-runtime composition and bounded scheduling, not the core orchestration logic.

## Normal app versus special certification servers

| Concern | Normal `app.main` | Step 19 certification server | Step 20 certification server |
|---|---|---|---|
| Runtime entry point | Direct `app.main:app` | Wrapper configures dependencies, then runs `app.main:app` | Wrapper configures dependencies, then runs `app.main:app` |
| Phase 11 executor | Remains `None` | Assigns a special `controlled_executor` | Assigns a special `real_executor` |
| Result materializer | Not composed | Supplied indirectly by the clean-room `_Executor` | Explicit `ResultSnapshotMaterializer(PROJECT_ROOT)` |
| Search processing | Valid submissions become `BLOCKED` | Per-search certification thread calls bounded fixture executor | Per-search certification thread polls the real orchestration service |
| Startup resume | None | None in the server wrapper | Explicitly lists and submits `PROCESSING`/`QUEUED` runs |
| Intended role | Documented normal application | Isolated bounded browser-certification utility | Full-5M certification utility |

The special servers demonstrate that Phase 11 can run when an executor and materializer are injected before importing/running the application. They do not prove that the documented normal runtime is composed correctly.

## Step 1 conclusion

**PASS - defect reproduced and bounded.**

At the exact required baseline, the documented normal runtime starts successfully but reports `workflow_available=false`. A valid user submission is persisted and immediately becomes `BLOCKED` solely because `PHASE11_SEARCH_EXECUTOR` remains `None`. `ResultSnapshotMaterializer` and `resume_phase11_searches` are not composed into normal startup, while the Step 19/20 certification wrappers install special execution wiring.

No fix was implemented in this step. Step 2 may now design the bounded production coordinator.
