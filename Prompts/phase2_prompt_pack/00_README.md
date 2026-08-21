# Phase 2 Prompt Pack — Historical Campaign Analysis

This pack implements Phase 2 of the Campaign Implementation Tool POC on top of the verified Phase 1 hardening commit:

`c6c9f41ea257aa33ae196b75cc8f76f8419431e7`

Phase 2 makes the application analytically useful. It lets a user explore the two-year historical campaign dataset, define a reproducible customer cohort, distinguish known-positive customers from unlabeled customers, inspect aggregate campaign and customer profiles, and save the resulting analysis definition for Phase 3.

Phase 2 does **not** train a model, score the 5-million-person prospect universe, select prospects, create campaigns, or export audiences.

## Recommended execution order

Give the coding agent these files first:

1. `01_PHASE_2_FREEZE_AND_BOUNDARIES.md`
2. `02_AGENT_OPERATING_INSTRUCTIONS.md`
3. `11_PROGRESS_TRACKER.md`

Then give it exactly one step file at a time:

1. `03_STEP_01_BASELINE_AND_ADDITIVE_SCHEMA.md`
2. `04_STEP_02_HISTORICAL_OPTIONS_AND_OVERVIEW.md`
3. `05_STEP_03_COHORT_ANALYSIS_ENGINE.md`
4. `06_STEP_04_HISTORICAL_ANALYSIS_APIS.md`
5. `07_STEP_05_OVERVIEW_ANALYTICS_UI.md`
6. `08_STEP_06_HISTORICAL_ANALYZER_UI.md`
7. `09_STEP_07_HARDENING_PERFORMANCE_AND_DOCS.md`

After every step, require tests, review the diff, and verify that the progress tracker was updated before allowing the next step.

Use `10_PHASE_2_ACCEPTANCE_CHECKLIST.md` for the final audit. `12_PHASE_3_HANDOFF_CONTRACT.md` freezes the exact artifact that Phase 3 may consume. `13_API_CONTRACT_REFERENCE.md` is a concise API reference. `14_SINGLE_MASTER_PHASE2_PROMPT.md` is provided only for an agent that can reliably execute staged work without running ahead.

## Expected outcome

At the end of Phase 2, a user can:

1. Open the application and review real historical campaign performance.
2. Navigate to Historical Analysis.
3. Select campaigns, products/categories, channels, date range, and a conversion definition.
4. Analyze distinct historical customers at customer grain.
5. Review known-positive versus unlabeled counts and aggregate profiles.
6. Save and reopen a reproducible analysis run.
7. Hand the saved analysis-run identifier to Phase 3 without having trained or scored anything yet.

