# Single Master Phase 1 Prompt — Reference Only

Use this only when an agent can reliably follow staged execution. The preferred method is still to submit the individual step prompts one at a time.

You are building Phase 1 of a Campaign Implementation POC.

Before doing anything, read and treat as authoritative:
1. `01_PHASE_1_FREEZE_AND_BOUNDARIES.md`
2. `02_AGENT_OPERATING_INSTRUCTIONS.md`
3. `11_PROGRESS_TRACKER.md`
4. `10_PHASE_1_ACCEPTANCE_CHECKLIST.md`

The frozen stack is:
- HTML5
- CSS3
- Vanilla JavaScript
- Python
- FastAPI
- SQLite via Python `sqlite3`

The product is a POC. It must work end-to-end for the Phase 1 scope but must not become an enterprise architecture exercise.

Execute the following steps in exact order, stopping after each step for tests and progress-log update:

1. Project bootstrap and application shell
   - Follow `03_STEP_01_PROJECT_BOOTSTRAP.md`

2. SQLite schema and connection layer
   - Follow `04_STEP_02_SQLITE_SCHEMA.md`

3. Streaming/chunked import pipeline
   - Follow `05_STEP_03_DATA_IMPORT_PIPELINE.md`

4. Indexing and reconciliation
   - Follow `06_STEP_04_INDEXING_AND_RECONCILIATION.md`

5. Summary/status/reference APIs
   - Follow `07_STEP_05_DATA_APIS.md`

6. Overview and Data Status UI
   - Follow `08_STEP_06_PHASE1_UI.md`

7. Integration/hardening/documentation
   - Follow `09_STEP_07_PHASE1_HARDENING.md`

After Step 7, validate every item in `10_PHASE_1_ACCEPTANCE_CHECKLIST.md`.

Critical non-negotiable rules:
- Do not implement PU learning.
- Do not implement propensity scoring.
- Do not implement audience selection.
- Do not implement campaign activation.
- Do not create a mapping between demographics and historical customers.
- Do not hard-code data KPIs in the UI.
- Do not load 5M rows into browser memory.
- Do not load 5M rows into Python memory during import.
- Do not introduce React/Vue/Angular/TypeScript.
- Do not introduce PostgreSQL/SQLAlchemy/Redis/Celery/Kafka/microservices/cloud infrastructure.
- Use parameterized SQL.
- Preserve explicit import and reconciliation metadata.
- Keep the project straightforward enough for a developer to understand quickly.

At the end, produce a Phase 1 completion report containing:
- implemented features
- file/folder structure
- SQLite schema summary
- import process
- API endpoints
- UI pages
- tests executed and results
- dataset row reconciliation
- measured timings if available
- known limitations
- confirmation that Phase 2 functionality was not implemented
