# Single Master Phase 3 Prompt

Use this only with an agent that can execute a staged implementation without skipping review gates.

You are implementing **Phase 3 — PU Learning Foundation and Model Training** in:

`https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Authoritative accepted Phase 2 baseline:

`52396010f945b0328b84453ce25c587b11ed7fd7`

Before changing code, read and obey:

- `01_PHASE_3_FREEZE_AND_BOUNDARIES.md`
- `02_AGENT_OPERATING_INSTRUCTIONS.md`
- `13_ML_FEATURE_CONTRACT.md`
- `14_MODEL_EVALUATION_CONTRACT.md`
- `15_LIBRARY_AND_LICENSE_NOTES.md`
- `11_PROGRESS_TRACKER.md`

## Non-negotiable product boundary

Phase 3 begins with a valid completed Phase 2 `analysis_run_id` and ends with a governed `model_run_id` plus a reloadable genuine PU model artifact.

Phase 3 must **not** score the 5-million-person demographic universe, create propensity scores, enable Audience Explorer, create campaigns, export audiences, or activate the Model Training browser page.

## Execute in seven gated steps

### Step 1
Implement only `03_STEP_01_BASELINE_SCHEMA_DEPENDENCIES.md`.

Stop. Test. Update progress tracker.

### Step 2
Implement only `04_STEP_02_RECONSTRUCT_TRAINING_COHORT.md`.

Stop. Test. Update progress tracker.

### Step 3
Implement only `05_STEP_03_FEATURE_ENGINEERING_PREPROCESSING.md`.

Stop. Test. Update progress tracker.

### Step 4
Implement only `06_STEP_04_PU_TRAINING_ALGORITHMS.md`.

Stop. Test. Update progress tracker.

### Step 5
Implement only `07_STEP_05_EVALUATION_MODEL_SELECTION.md`.

Stop. Test. Update progress tracker.

### Step 6
Implement only `08_STEP_06_MODEL_PERSISTENCE_AND_CLI.md`.

Stop. Test. Update progress tracker.

### Step 7
Implement only `09_STEP_07_HARDENING_PERFORMANCE_DOCS.md`.

Then complete `10_PHASE_3_ACCEPTANCE_CHECKLIST.md`.

## Critical rules

- Historical cohort must be reconstructed at distinct customer grain from saved Phase 2 filters.
- Recomputed observation/selected/positive/unlabeled counts must match the saved Phase 2 snapshot.
- Unlabeled is not negative.
- Allowed X features are exactly the 11 frozen prospect-compatible features.
- No PII, IDs, campaign behavior, purchase/spend/history, or demographic enrichment may enter X.
- Derive age using saved analysis end date.
- Fit preprocessing on training split only.
- Primary candidate must be genuine PU learning using `pulearn`.
- Naive supervised P-vs-U classifier is diagnostic only and can never be the selected official model.
- Evaluation must emphasize held-out known-positive ranking/lift and clearly label observed-label metrics.
- Persist model artifact to disk, not SQLite BLOB.
- Store relative path + SHA-256.
- Reload artifact and verify predictions.
- Exact runtime library versions must be saved.
- No customer ID list or raw training matrix may be persisted.
- No 5M demographic scoring.

## Required final evidence

At completion report:

1. final HEAD / working tree status;
2. schema version;
3. full pytest count/result;
4. pip check;
5. compileall;
6. data reconciliation;
7. full-data source `analysis_run_id`;
8. reconstructed counts;
9. train/validation counts;
10. feature-contract fingerprint;
11. exact library versions;
12. PU candidate results;
13. selected candidate and reason;
14. top-5/10/20 known-positive recall/lift;
15. `model_run_id`;
16. artifact relative path/size/SHA-256;
17. artifact reload verification;
18. same-seed reproducibility result;
19. scope scan proving no demographic scoring or later-phase feature;
20. final Phase 4 Go/No-Go decision.

Do not start Phase 4.
