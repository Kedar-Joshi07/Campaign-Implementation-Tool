# Prompt to Start Phase 5

You are starting **Phase 5 — 5M Prospect Scoring Engine**.

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Authoritative Phase 4 baseline: `fdae4a7a40c846e4038a8ebe656257eb4164cd5d`

First verify HEAD/worktree and run pip check, full pytest, compileall and data validation. Read `00`, `01`, `02`, `11`, `12`, `13`, `14`, `17`, `18`, and `10_PROGRESS_TRACKER.md` fully. Inspect current schema/job/executor/training/artifact/feature/model API code and Phase 4 tests.

Frozen contract:

```text
PRIMARY=BAGGING_PU
role policy=2
evaluation contract=2
feature contract=1
feature SHA=a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535
```

Phase 5 scores the independent demographics population only; no customer linkage, no whole-5M memory load, no Audience Explorer yet.

Now read `03_STEP_01_BASELINE_SCHEMA_V5.md` and implement **only Step 1**: schema v5, jobs extension for PROSPECT_SCORING, scoring_runs, propensity_scores, required indexes/repositories and migration tests.

Do not implement scoring engine, ProcessPool scoring worker, APIs or UI yet.

After Step 1 run focused/full tests, compile, pip and diff check; update tracker; report baseline/current status, changed files, migration/job preservation, schemas/indexes/tests/issues; STOP.
