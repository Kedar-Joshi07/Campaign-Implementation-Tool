# Step 1 — Baseline, Schema v3, Dependencies, and Artifact Boundary

## Objective

Prepare the accepted Phase 2 repository for modeling without training a model yet.

## Tasks

### A. Verify baseline

Record:

- `git rev-parse HEAD`
- `git status --short`
- full existing pytest result
- `pip check`
- compile result
- populated data reconciliation result where available

The required baseline is `52396010f945b0328b84453ce25c587b11ed7fd7`.

### B. Correct Phase 2 post-commit evidence wording

Add a concise note to the Phase 2 acceptance/progress documentation:

> Phase 2 was validated while the implementation was still in the working tree on the accepted Phase 1 base; the accepted Phase 2 implementation was subsequently committed as `52396010f945b0328b84453ce25c587b11ed7fd7` and this SHA is the authoritative Phase 3 baseline.

Do not alter recorded test timings/counts merely to make history look cleaner.

### C. Add ML dependencies

Update dependency files using compatible open-source versions.

Required logical dependencies:

- `scikit-learn`
- `pulearn`
- `joblib`

NumPy and pandas already exist through generator requirements.

Do not pin versions blindly to values not actually installed/tested. Use a bounded compatible range in source requirements and record exact versions in each model run.

Run:

```text
python -m pip install -r requirements.txt
python -m pip check
python -c "import sklearn, pulearn, joblib; ..."
```

Record versions.

### D. Add schema version 3

Create additive migration v2 → v3.

Add `model_runs` with the fields from the freeze.

Requirements:

- transactional;
- idempotent;
- preserves every prior table/row;
- version advances only after successful migration;
- future versions still rejected;
- FK references completed/any historical run structurally; service enforces COMPLETED status;
- no `propensity_scores` table.

### E. Artifact folders

Add:

```text
artifacts/
  models/
```

as runtime-only structure, preferably with `.gitkeep` only if project convention needs it.

Update `.gitignore` so actual model artifacts and metadata produced by training are not committed.

### F. Tests

Add tests for:

- fresh v3 initialization;
- populated v2 migration with Phase 1/2 row preservation;
- required `model_runs` columns/constraints/indexes;
- failed migration rollback;
- no `propensity_scores` table;
- artifact runtime path ignored.

## Do not do

- no cohort reconstruction;
- no feature engineering;
- no model fitting;
- no model UI/API.

## Step exit criteria

- all old tests pass;
- new migration tests pass;
- schema version is 3;
- dependencies import;
- artifact boundary is established;
- progress tracker updated.
