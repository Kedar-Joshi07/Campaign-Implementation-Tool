# Phase 3 Prompt Pack — PU Learning Foundation and Model Training

Repository:

`https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Authoritative Phase 2 baseline:

`52396010f945b0328b84453ce25c587b11ed7fd7`

## Purpose

Phase 3 converts a valid, completed Phase 2 `analysis_run_id` into a real and reproducible positive-unlabeled (PU) model-training workflow.

Phase 3 must prove that the application can:

1. Load and validate a completed historical analysis.
2. Reconstruct the exact customer-grain cohort from saved normalized filters.
3. Reconcile selected/positive/unlabeled counts with the Phase 2 snapshot.
4. Build a leakage-safe training matrix using only customer attributes that have compatible concepts in the independent demographic prospect universe.
5. Apply deterministic preprocessing.
6. Train a genuine PU-learning model.
7. Compare it against bounded diagnostic baselines/challengers.
8. Evaluate it using PU-appropriate ranking and stability metrics.
9. Persist a reloadable preprocessing + model artifact and governed metadata.
10. Reproduce the same outputs when rerun with the same inputs and seed.

Phase 3 deliberately does **not** score the 5-million-person prospect universe, expose propensity scores, build Audience Explorer, create campaigns, or add the Model Training browser workflow. Those are later phases.

## Recommended execution order

Give the coding agent these files first:

1. `01_PHASE_3_FREEZE_AND_BOUNDARIES.md`
2. `02_AGENT_OPERATING_INSTRUCTIONS.md`
3. `11_PROGRESS_TRACKER.md`
4. `13_ML_FEATURE_CONTRACT.md`
5. `14_MODEL_EVALUATION_CONTRACT.md`

Then execute exactly one implementation step at a time:

1. `03_STEP_01_BASELINE_SCHEMA_DEPENDENCIES.md`
2. `04_STEP_02_RECONSTRUCT_TRAINING_COHORT.md`
3. `05_STEP_03_FEATURE_ENGINEERING_PREPROCESSING.md`
4. `06_STEP_04_PU_TRAINING_ALGORITHMS.md`
5. `07_STEP_05_EVALUATION_MODEL_SELECTION.md`
6. `08_STEP_06_MODEL_PERSISTENCE_AND_CLI.md`
7. `09_STEP_07_HARDENING_PERFORMANCE_DOCS.md`

After each step:

- run the relevant focused tests;
- run all previously existing tests;
- inspect the diff;
- update `11_PROGRESS_TRACKER.md`;
- do not advance if a Critical acceptance item is broken.

Use `10_PHASE_3_ACCEPTANCE_CHECKLIST.md` for final sign-off.

`12_PHASE_4_HANDOFF_CONTRACT.md` freezes what the next phase may consume.

`16_SINGLE_MASTER_PHASE3_PROMPT.md` exists only for an agent that can reliably execute staged work without running ahead.

## Expected Phase 3 completion state

At the end of Phase 3, the repository should be able to execute a command conceptually equivalent to:

```powershell
.\.venv\Scripts\python.exe scripts\train_pu_model.py --analysis-run-id 10
```

and produce:

- one persisted `model_runs` record;
- one reloadable model artifact on disk;
- one stable feature contract;
- one metrics/evaluation snapshot;
- one SHA-256 artifact checksum;
- one documented library/version snapshot;
- zero prospect propensity-score rows.

The browser should still show Model Training as a later-phase/disabled navigation item.
