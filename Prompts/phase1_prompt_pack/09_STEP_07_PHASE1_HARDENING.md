# STEP 7 — Phase 1 Integration, Hardening, and Documentation

## Objective
Run the complete Phase 1 flow, eliminate integration defects, and leave the repository ready for Phase 2.

## Prompt to coding agent
Implement only Step 7 of Phase 1. Do not start Phase 2.

### 1. Full clean-run validation
From a fresh/clean local state, verify the documented sequence:

1. create virtual environment
2. install requirements
3. initialize database
4. import customers
5. import campaign sales
6. import demographic parts
7. validate/reconcile data
8. start FastAPI
9. open UI
10. verify Overview/Data Status values

Use one project virtual environment for the application, tests, importers, and
data generators. Install only the root `requirements.txt`, which must include
`-r data_generation_scripts/requirements_campaign_data.txt` as established in
Step 1. Do not create or configure a separate generator environment.

Where full 5M source files are not available in the development environment, execute the full sequence with fixtures and document the exact command for the real dataset. If the actual files are available, perform the real import and record timings/counts.

### 2. Idempotency and restart behavior
Verify:
- DB init can run repeatedly
- import cannot accidentally duplicate data
- explicit replace modes work as documented
- failed import records FAILED metadata
- application can restart against existing DB without mutation

### 3. Error-path validation
Check:
- missing source file
- wrong CSV schema
- invalid campaign foreign key
- malformed date
- demographics family arithmetic error
- corrupted gzip handling where practical
- database unavailable/locked scenario gives useful error

### 4. Performance sanity
For loaded test or real data:
- application startup should not scan 5M rows unnecessarily
- `/api/health` should be fast
- `/api/data/summary` should be reasonably responsive
- states/reference endpoints should be indexed/aggregated efficiently

If summary aggregation over 5M is slow, consider a small cached metadata/summary table only if it remains simple and automatically refreshed after imports. Do not introduce Redis or external cache.

### 5. Logging
Ensure logs cover:
- startup
- DB initialization
- imports start/end/failure
- reconciliation result
- API-level unexpected exceptions

Avoid logging every row.

### 6. README finalization
README must include:
- project purpose
- Phase 1 scope
- architecture summary
- folder structure
- exact setup commands
- exact DB init command
- exact import commands
- expected source schemas
- validation command
- run command
- API docs URL
- UI URL
- troubleshooting section
- explicit Phase 1 exclusions
- pointer to next phase, without implementing it

### 7. Add `docs/PHASE_1_IMPLEMENTATION_SUMMARY.md`
Include:
- what was implemented
- architecture decisions
- DB schema summary
- API list
- import behavior
- test coverage
- known limitations
- measured import/query timings if available
- Phase 2 readiness notes

### 8. Test suite
Run entire test suite.
No known failing tests are acceptable at Phase 1 completion unless clearly external/environmental and documented.

### 9. Final self-review
Check for:
- accidental Phase 2 code
- hard-coded file paths
- hard-coded KPI counts
- duplicated configuration
- unused dependencies
- giant modules
- unparameterized SQL
- hidden demographic/customer linkage

Remove/fix issues found.

### Step completion criteria
All items in `10_PHASE_1_ACCEPTANCE_CHECKLIST.md` are satisfied or explicitly marked with evidence-based limitation.

Update `11_PROGRESS_TRACKER.md` with final Phase 1 status and stop.
