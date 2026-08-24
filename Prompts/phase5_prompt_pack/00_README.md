# Phase 5 Prompt Pack — 5M Prospect Scoring Engine

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Authoritative Phase 4 baseline: `fdae4a7a40c846e4038a8ebe656257eb4164cd5d`

## Phase 5 purpose

Phase 5 takes one verified completed Phase 4 `model_run_id` and scores the independent demographic prospect universe.

```text
Historical Analysis
→ analysis_run_id
→ governed PU Model Training
→ verified model_run_id
→ PROSPECT_SCORING job
→ 5M independent demographics
→ exact 11-feature contract
→ persisted preprocessor
→ persisted BAGGING_PU estimator
→ Look-alike Propensity Score
→ propensity_scores
→ completed scoring_run_id
```

## Phase 5 implements

1. schema v5;
2. `scoring_runs` and `propensity_scores`;
3. Phase 4 job-framework extension for `PROSPECT_SCORING`;
4. strict model/artifact/feature-contract scoreability gating;
5. bounded keyset demographic reads;
6. chunked transform/inference/persistence;
7. scoring progress and restart/failure handling;
8. scoring APIs/status/aggregate summary;
9. Prospect Scoring controls inside the existing Model Training workspace;
10. exact 5M validation;
11. Phase 6 Audience Explorer handoff.

## Explicitly not Phase 5

- Audience Explorer;
- individual prospect list/detail API;
- score bands/percentiles/ranks;
- audience selection;
- campaign builder;
- export;
- activation.

## Read order

Read first:

1. `01_PHASE_5_FREEZE_AND_BOUNDARIES.md`
2. `02_AGENT_OPERATING_INSTRUCTIONS.md`
3. `11_SCHEMA_V5_CONTRACT.md`
4. `12_SCORING_MODEL_AND_FEATURE_CONTRACT.md`
5. `13_SCORE_SEMANTICS_AND_SUMMARY_CONTRACT.md`
6. `14_SCORING_JOB_LIFECYCLE_CONTRACT.md`
7. `15_SCORING_API_CONTRACT.md`
8. `16_SCORING_UI_CONTRACT.md`
9. `17_PERFORMANCE_MEMORY_SQLITE_CONTRACT.md`
10. `18_SECURITY_PRIVACY_BOUNDARY.md`
11. `10_PROGRESS_TRACKER.md`

Then implement one step at a time:

1. `03_STEP_01_BASELINE_SCHEMA_V5.md`
2. `04_STEP_02_SCORING_DATA_ACCESS_FEATURE_COMPATIBILITY.md`
3. `05_STEP_03_CHUNKED_SCORING_ENGINE.md`
4. `06_STEP_04_SCORING_JOB_ORCHESTRATION.md`
5. `07_STEP_05_SCORING_APIS.md`
6. `08_STEP_06_SCORING_UI.md`
7. `09_STEP_07_HARDENING_FULL_5M_VALIDATION.md`

After each step: focused tests, full regression, compile, `git diff --check`, update tracker, STOP.

Acceptance: `19_PHASE_5_ACCEPTANCE_CHECKLIST.md`

Phase 6 handoff: `20_PHASE_6_HANDOFF_CONTRACT.md`

Master prompt: `22_SINGLE_MASTER_PHASE5_PROMPT.md`

Recommended kickoff: `23_PHASE5_START_PROMPT.md`
