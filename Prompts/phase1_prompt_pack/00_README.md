# Campaign Implementation POC — Phase 1 Prompt Pack

This pack is designed to be given to GitHub Copilot, OpenAI Codex, or another coding agent in controlled steps.

## Phase 1 objective
Build the foundation of a functional Campaign Implementation POC using:
- Frontend: HTML5, CSS3, Vanilla JavaScript
- Backend: Python + FastAPI
- Database: SQLite
- Charts later: Chart.js is allowed, but Phase 1 does not require analytics charts
- ML later: PU-learning pipeline is explicitly out of Phase 1

Phase 1 must create a clean, runnable application skeleton, load the three datasets into SQLite, expose health/data-summary APIs, and render the initial application shell/navigation from FastAPI.

## Data expected
1. `customer_master_125000.csv.gz` — approximately 125,000 rows, 22 columns
2. `campaign_sales_570000.csv.gz` — approximately 570,000 rows, 38 columns
3. Existing USA demographic universe — approximately 5,000,000 rows, 28 columns, possibly split into compressed CSV parts

The demographic universe is independent from customer/campaign history. It must not share `customer_id` or any row-level linkage with historical customer data.

## Recommended usage order
1. Read `01_PHASE_1_FREEZE_AND_BOUNDARIES.md`
2. Read `02_AGENT_OPERATING_INSTRUCTIONS.md`
3. Execute step prompts in order from `03_STEP_01_PROJECT_BOOTSTRAP.md` through `09_STEP_07_PHASE1_HARDENING.md`
4. After every step, update `11_PROGRESS_TRACKER.md`
5. Validate the complete phase with `10_PHASE_1_ACCEPTANCE_CHECKLIST.md`

Do not skip steps. Do not begin Phase 2 work during Phase 1.
