# Agent Operating Instructions — Use Before Every Phase 2 Step

You are implementing Phase 2: Historical Campaign Analysis for the Campaign Implementation Tool POC.

## Before changing code

1. Read `01_PHASE_2_FREEZE_AND_BOUNDARIES.md` completely.
2. Read the current step file completely.
3. Read `11_PROGRESS_TRACKER.md`.
4. Inspect the current repository and relevant tests.
5. Confirm the current HEAD and worktree state.
6. Preserve working Phase 1 behavior and unrelated user changes.
7. Work only on the current step.

## Mandatory boundaries

- Keep HTML/CSS/Vanilla JS, FastAPI/Python, and SQLite via `sqlite3`.
- Do not implement PU learning, model training, scoring, Audience Explorer, campaign creation, or export.
- Do not create any `customer_id` ↔ `person_id` linkage.
- Do not query the demographic population for historical analysis except unchanged Phase 1 behavior.
- Do not treat unlabeled customers as confirmed negatives.
- Do not count campaign rows as unique customers.
- Do not expose raw customer rows, names, addresses, phones, emails, SQL, paths, stack traces, or internal database messages through APIs.
- Do not hard-code business KPIs in the frontend.
- Do not load large datasets into Python or browser memory.
- Do not modify Git LFS datasets, samples, masters, summaries, generators, `.gitattributes`, or their hashes.
- Do not silently change frozen Phase 1 schemas or APIs.
- Do not add dependencies or architecture components without a demonstrated requirement.

## Implementation expectations

- Use additive, idempotent migrations.
- Use repository/service/router/schema separation consistent with Phase 1.
- Use explicit, parameterized SQLite SQL.
- Assemble dynamic WHERE clauses only from fixed code-owned fragments.
- Bound list inputs and response breakdowns.
- Use deterministic ordering for aggregates and JSON.
- Keep one authoritative implementation of cohort semantics.
- Make age calculation deterministic using the analysis end date.
- Keep user-facing errors stable and sanitized; log internal detail.
- Reuse existing CSS components and JavaScript utilities before creating new ones.
- Render untrusted/data-derived text with `textContent`, not `innerHTML`.
- Keep the POC understandable and locally runnable.

## Tests required in every step

At minimum:

1. Add tests for behavior introduced by the step.
2. Run the focused tests for the step.
3. Run the full suite before marking the step complete.
4. Run `python -m compileall -q app scripts tests`.
5. Run `git diff --check`.
6. Record commands, results, and measured timings in `11_PROGRESS_TRACKER.md`.

Use small synthetic SQLite fixtures in automated tests. Do not require downloading or rebuilding the full Git LFS data to run unit/integration tests.

## End-of-step response

After each step, report:

1. Base and resulting HEAD.
2. Files changed.
3. Behavior implemented.
4. Tests/checks run and exact results.
5. Schema/API/UI contract changes.
6. Known limitations or risks.
7. Confirmation that later-phase functionality was not added.
8. The exact next step, but do not begin it.

Update `11_PROGRESS_TRACKER.md` before responding.

Do not stage, commit, push, create a branch, or open a pull request unless the user explicitly authorizes that specific action.
