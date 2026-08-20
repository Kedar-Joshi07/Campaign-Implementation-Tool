# Agent Operating Instructions — Use Before Every Phase 1 Step

You are implementing Phase 1 of a Campaign Implementation POC.

Before writing or changing code:
1. Read `01_PHASE_1_FREEZE_AND_BOUNDARIES.md` completely.
2. Read the current `11_PROGRESS_TRACKER.md`.
3. Inspect the existing repository before creating duplicate files or alternate architectures.
4. Preserve all requirements already implemented correctly.
5. Work only on the current step prompt.

## Mandatory behavior
- Do not silently change the frozen stack.
- Do not introduce React, Vue, Angular, TypeScript, SQLAlchemy, PostgreSQL, Redis, Celery, Docker orchestration, or cloud components.
- Do not implement PU learning or later-phase features.
- Do not fake API results.
- Do not hard-code row counts that should come from SQLite.
- Do not create any linkage between demographic `person_id` and historical `customer_id`.
- Do not duplicate customer demographic columns into `campaign_sales` beyond the frozen schema.
- Do not store the full 5M records in browser memory.
- Do not return huge datasets through an API.
- Use parameterized SQLite SQL.
- Use chunked imports.
- Keep implementation POC-sized but maintainable.

## For every step
At the end of the step:
1. Run the relevant tests/checks.
2. Fix failures caused by the step.
3. Summarize files created/modified.
4. Summarize design decisions.
5. State tests executed and their results.
6. Update `11_PROGRESS_TRACKER.md` with:
   - completed work
   - files changed
   - tests run
   - known issues
   - deferred items
   - next step
7. Do not begin the next step unless explicitly asked.

## Coding expectations
- Prefer simple functions and explicit SQL.
- Add docstrings only where they add value.
- Add comments for non-obvious decisions, not for obvious syntax.
- Avoid giant modules.
- Avoid premature generic frameworks.
- Keep configuration centralized.
- Use logging rather than scattered print statements in application code.
- CLI import scripts may print progress, but should also log significant events.

## Error handling
- Database/import errors must be visible and actionable.
- FastAPI endpoints should return appropriate HTTP status codes.
- Frontend should display useful user-facing messages rather than fail silently.
- Never catch broad exceptions and discard them.

## Security basics appropriate for a POC
- Parameterized SQL.
- Do not execute user-supplied SQL.
- Do not expose arbitrary filesystem reads through APIs.
- Do not expose stack traces to the browser in normal mode.
- Synthetic contact data is still to be handled as application data, not echoed unnecessarily in logs.
