# Single Master Phase 2 Prompt — Reference Only

Use this only with an implementation agent that reliably stops after each stage. The recommended workflow is still one step file per reviewed turn.

You are implementing Phase 2: Historical Campaign Analysis for the Campaign Implementation Tool POC.

## Required base

Repository:

`https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Accepted base SHA:

`c6c9f41ea257aa33ae196b75cc8f76f8419431e7`

Before changing code, read completely and treat as authoritative:

1. `01_PHASE_2_FREEZE_AND_BOUNDARIES.md`
2. `02_AGENT_OPERATING_INSTRUCTIONS.md`
3. `10_PHASE_2_ACCEPTANCE_CHECKLIST.md`
4. `11_PROGRESS_TRACKER.md`
5. `12_PHASE_3_HANDOFF_CONTRACT.md`
6. `13_API_CONTRACT_REFERENCE.md`

Inspect the existing repository, verify HEAD/worktree status, and run the Phase 1 test baseline. Preserve unrelated changes and all accepted Phase 1 behavior.

## Frozen purpose

Phase 2 lets users analyze historical campaign performance, define a reproducible historical customer cohort, classify distinct selected customers as known positive or unlabeled under an explicit conversion definition, inspect aggregate profiles, and save an `analysis_run_id` for Phase 3.

Unlabeled does not mean confirmed negative.

Campaign history creates the cohort and label. Do not turn historical behavior into prospect-only features. Never link historical `customer_id` to demographic `person_id`.

## Execute in exact order

### Step 1

Follow `03_STEP_01_BASELINE_AND_ADDITIVE_SCHEMA.md`.

Verify the Phase 1 baseline and implement only the additive version-2 migration, analysis-run table, and justified filter indexes.

Run focused/full tests, update the progress tracker, report, and stop.

### Step 2

Only after approval, follow `04_STEP_02_HISTORICAL_OPTIONS_AND_OVERVIEW.md`.

Implement real database options and bounded overall historical aggregates in repository/service modules.

Run focused/full tests, update the progress tracker, report, and stop.

### Step 3

Only after approval, follow `05_STEP_03_COHORT_ANALYSIS_ENGINE.md`.

Implement the authoritative customer-grain cohort engine, conversion definitions, profiles, deterministic age, and analysis-run persistence/reopen behavior.

Run focused/full tests, update the progress tracker, report, and stop.

### Step 4

Only after approval, follow `06_STEP_04_HISTORICAL_ANALYSIS_APIS.md` and `13_API_CONTRACT_REFERENCE.md`.

Expose exactly the five bounded historical endpoints with typed validation and sanitized errors.

Run focused/full tests, update the progress tracker, report, and stop.

### Step 5

Only after approval, follow `07_STEP_05_OVERVIEW_ANALYTICS_UI.md`.

Add a concise historical-performance section to Overview using real API values. Preserve Phase 1 content.

Run focused/full/browser tests, update the progress tracker, report, and stop.

### Step 6

Only after approval, follow `08_STEP_06_HISTORICAL_ANALYZER_UI.md`.

Enable and build the full Historical Analysis workflow, saved-analysis list, and reopen behavior. Keep later phases disabled.

Run focused/full/browser tests, update the progress tracker, report, and stop.

### Step 7

Only after approval, follow `09_STEP_07_HARDENING_PERFORMANCE_AND_DOCS.md`.

Run the end-to-end hardening audit, full-data reconciliation where practical, query-plan/performance checks, failure paths, documentation, and acceptance checklist.

## Non-negotiable rules

- HTML/CSS/Vanilla JS only.
- FastAPI/Python and direct SQLite only.
- Additive migrations; no Phase 1 data loss.
- Parameterized SQL; allowlisted dynamic clauses only.
- Distinct-customer cohort grain.
- Positive if any matching row meets the selected definition.
- Positive + unlabeled = selected.
- Unlabeled is not negative.
- No raw customer/person data in Phase 2 APIs/UI.
- No demographics join or customer/person linkage.
- No PU training, model artifact, scoring, job queue, Audience Explorer, campaign builder, export, or activation.
- No hard-coded analytical metrics.
- No large Python/browser materialization.
- No dataset/LFS modifications.
- No commit/push without explicit authorization.

## Final deliverable

After Step 7, provide the structured completion report required by that step and a pass/fail evidence table for every section of `10_PHASE_2_ACCEPTANCE_CHECKLIST.md`, ending with a Go/No-Go recommendation for Phase 3.
