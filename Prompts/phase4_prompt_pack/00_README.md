# Phase 4 Prompt Pack — Model Training Orchestration, APIs, Jobs, and UI

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Authoritative Phase 3 baseline: `04e61caddedcf7963e824e2ccc425ac241d03842`

## Purpose
Phase 3 already proves the ML workflow. Phase 4 makes that workflow usable from the application without changing the frozen modeling logic.

Phase 4 implements:
- persistent training jobs;
- bounded local background execution;
- model-training API;
- job-status API;
- model-run list/detail APIs;
- Model Training UI;
- progress polling;
- PRIMARY / CHALLENGER / DIAGNOSTIC comparison;
- restart/failure handling;
- Phase 5 handoff.

Phase 4 must NOT implement 5M scoring, propensity storage, Audience Explorer, campaign creation, audience export, or activation.

## Execution order
Read first:
1. `01_PHASE_4_FREEZE_AND_BOUNDARIES.md`
2. `02_AGENT_OPERATING_INSTRUCTIONS.md`
3. `09_JOB_LIFECYCLE_CONTRACT.md`
4. `10_MODEL_API_CONTRACT.md`
5. `11_MODEL_TRAINING_UI_CONTRACT.md`
6. `08_PROGRESS_TRACKER.md`

Then execute one step at a time:
1. `03_STEP_01_SCHEMA_JOB_FOUNDATION.md`
2. `04_STEP_02_BACKGROUND_ORCHESTRATION.md`
3. `05_STEP_03_MODEL_AND_JOB_APIS.md`
4. `06_STEP_04_MODEL_TRAINING_UI.md`
5. `07_STEP_05_HARDENING_AND_FINAL_VALIDATION.md`

Use `12_PHASE_4_ACCEPTANCE_CHECKLIST.md` for final sign-off.
Use `13_PHASE_5_HANDOFF_CONTRACT.md` to freeze the next phase.
Use `15_SINGLE_MASTER_PHASE4_PROMPT.md` only with an agent that reliably obeys staged stop points.
