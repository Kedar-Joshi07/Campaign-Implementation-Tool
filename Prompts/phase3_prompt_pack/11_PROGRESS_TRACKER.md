# Phase 3 Progress Tracker

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Authoritative Phase 2 baseline: `52396010f945b0328b84453ce25c587b11ed7fd7`

Update this file after every Phase 3 step.

## Baseline

- Date: 2026-08-21
- Starting HEAD: `52396010f945b0328b84453ce25c587b11ed7fd7`
- Branch/remote: `main`; 0 ahead / 0 behind `origin/main`
- Working tree status: only the user-provided untracked
  `Prompts/phase3_prompt_pack/`; no tracked or `data/` changes
- Existing pytest: 158 passed in 51.42s; no warnings reported
- pip check: `No broken requirements found.`
- compileall: `python -m compileall -q app scripts tests` passed with no output
- data validation: overall `OK` in 10.119s; schema version 2; customers 125,000;
  campaign sales 570,000; demographics 5,000,000; zero invalid customer
  references; zero PU consistency violations; all 21 required indexes present
- completed analysis ID chosen for full-data testing: `analysis_run_id=10`
  (`ATTRIBUTED_PURCHASE`); 14,037 observations; 14,037 selected customers;
  626 positives; 13,411 unlabeled; invariant reconciles exactly
- historical analysis table: healthy; 10 `COMPLETED` rows and no rows in another
  status at baseline
- Initialization scope: all six foundational/contract documents read and
  accepted; no Phase 3 implementation step started

---

## Step 1 — Baseline / schema / dependencies

Status: COMPLETE — 2026-08-21T11:20:26+05:30

### Files changed
- `.gitignore`
- `requirements.txt`
- `artifacts/models/.gitkeep`
- `app/database/schema.py`
- `tests/test_database_schema.py`
- `tests/test_data_api.py`
- `tests/test_data_reconciliation.py`
- `tests/test_health.py`
- `tests/test_phase3_schema.py`
- `Prompts/phase2_prompt_pack/11_PROGRESS_TRACKER.md`
- `Prompts/phase3_prompt_pack/11_PROGRESS_TRACKER.md`

### Decisions
- Added one ordered, transactional v2→v3 migration. Fresh initialization now
  creates v3 through the existing v1→v2→v3 registry; repeated initialization is
  idempotent, and the version advances only after migration success.
- Added only `model_runs`; no customer-ID list, training matrix, raw SQL, BLOB
  artifact, or `propensity_scores` table exists.
- Added `idx_model_runs_newest` for bounded newest-first listing and
  `idx_model_runs_analysis_run_id` for source-run lookup. A status index was not
  added because Step 1 has no measured query evidence that justifies it.
- The database FK enforces structural reference to `historical_analysis_runs`;
  the frozen `COMPLETED`-status rule remains a service concern for Step 2.
- Actual artifacts under `artifacts/models/` are ignored; `.gitkeep` preserves
  the runtime boundary in source control.
- Dependency source ranges reflect the tested environment. Exact versions must
  still be captured per future model run.

### Dependency versions
- Python: 3.12.0
- NumPy: 2.3.3
- pandas: 2.3.3
- scikit-learn: 1.7.1
- pulearn: 0.0.12
- joblib: 1.5.2

### Tests
- Dependency install: `python -m pip install -r requirements.txt` passed after
  package-index access was enabled; `pulearn 0.0.12` was installed.
- Dependency verification: `python -m pip check` passed; direct imports of
  `sklearn`, `pulearn`, and `joblib` passed and reported the versions above.
- Focused: `python -m pytest -q tests/test_database_schema.py
  tests/test_phase3_schema.py tests/test_data_reconciliation.py
  tests/test_data_api.py tests/test_health.py` → 57 passed in 20.57s.
- Full: `python -m pytest -q` → 163 passed in 69.00s; no warnings reported.
- Compile: `python -m compileall -q app scripts tests` passed with no output.
- Diff check: `git diff --check` passed; informational LF-to-CRLF notices only.
- An initial 18-pass/1-fail schema run exposed incorrect multi-path use of
  `git check-ignore --quiet` in the new test. The test was corrected to check
  each path separately; no implementation defect was involved.

### Evidence
- Populated migration: schema 2→3 completed; customers 125,000, campaign sales
  570,000, demographics 5,000,000, data import runs 3, and historical analysis
  runs 10 were preserved. Repeated initialization remained idempotent.
- Handoff preservation: `analysis_run_id=10` remains `COMPLETED` with 14,037
  observations/customers, 626 positives, and 13,411 unlabeled.
- `model_runs` has all 26 frozen logical columns, a restrictive FK to
  `historical_analysis_runs`, bounded status/fraction/count/invariant/checksum
  constraints, and both required indexes. It contains zero rows after Step 1.
- Failed v3 migration test leaves schema version 2 and rolls back created DDL.
- Populated `python scripts/validate_data.py --json`: overall `OK` in 18.222s;
  zero invalid customer references, zero PU consistency violations, and all 23
  required indexes present.
- `git check-ignore` confirms future `.joblib` and model metadata paths are
  ignored while `artifacts/models/.gitkeep` remains source-visible.
- Phase 2 evidence now states the exact accepted-commit chronology required by
  the Phase 3 freeze without changing historical test counts or timings.

### Open issues
- None within Step 1. `pulearn` import compatibility is proven; estimator-fit
  compatibility belongs to Step 4 and was not tested early.
- Cohort reconstruction, feature engineering, model fitting/evaluation,
  persistence/CLI, APIs, and UI were not implemented. Step 2 is not started.

---

## Step 2 — Training cohort reconstruction

Status: COMPLETE — 2026-08-21T11:37:20+05:30

### Files changed
- `app/repositories/historical_repository.py`
- `app/repositories/model_training_repository.py`
- `app/services/training_cohort_service.py`
- `tests/test_training_cohort_service.py`
- `Prompts/phase3_prompt_pack/11_PROGRESS_TRACKER.md`

### Full-data reconstruction
- analysis_run_id: 10
- observations: 14,037
- selected customers: 14,037
- positives: 626
- unlabeled: 13,411
- runtime: 0.511792s
- approximate frame memory: 8,219,363 bytes / 7.839 MiB
- reconciliation: PASS — stored counts, reconstructed counts, unique customer
  count, and `626 + 13,411 = 14,037` all match exactly

### Tests
- Focused cohort plus authoritative Phase 2 semantic/hardening regression:
  `python -m pytest -q tests/test_training_cohort_service.py
  tests/test_historical_analysis_service.py tests/test_phase2_hardening.py` →
  40 passed in 27.18s.
- Full: `python -m pytest -q` → 173 passed in 65.04s; no warnings reported.
- Compile: `python -m compileall -q app scripts tests` passed with no output.
- Dependency: `python -m pip check` → `No broken requirements found.`
- Diff: `git diff --check` and explicit trailing-whitespace scans passed;
  informational LF-to-CRLF notices only.

### Evidence
- Extracted the Phase 2 matching-observation/customer-label CTE into one shared
  code-owned builder; the existing Phase 2 repository wrapper and hardening test
  remain compatible, so Phase 3 uses the exact same filter and conversion logic.
- Reconstruction performs SQL reduction before pandas materialization and
  returns one deterministically ordered row per distinct historical customer.
- Returned frame columns are exactly internal `customer_id`/`pu_label` plus the
  eleven frozen prospect-compatible raw features, in contract order. Customer
  IDs are unique; labels are exact 0/1; numeric/nullable/string dtypes are
  enforced; no PII, campaign behavior, product behavior, spend, or margin fields
  are returned.
- Age uses the saved normalized `contact_date_to`. The fixture proved birthday
  boundaries of 25 on the birthday and 24 one day before the birthday.
- Fixture evidence covers multiple observations/customer, positive-if-any,
  outside-filter isolation, all three conversion definitions, contacted-only,
  inclusive dates, missing/RUNNING/FAILED/malformed runs, and current-source
  count/label mutation as a hard reconciliation stop.
- Trace-based service-path evidence captured every SQLite statement and found no
  `demographics` query.
- Full-data run 10 used `ATTRIBUTED_PURCHASE` and reference date 2025-12-31;
  all 13 returned columns matched the frozen boundary. No database row, model
  artifact, or data file was created or changed by reconstruction.

### Open issues
- None within Step 2. The in-memory frame intentionally retains `customer_id`
  only as an internal reconciliation/split key and `pu_label` only as the target;
  Step 3 must remove both from model inputs.
- Categorical normalization, deterministic splitting, preprocessing, model
  fitting/evaluation, model-run persistence, artifact writing, and CLI work were
  not implemented. Step 3 is not started.

---

## Step 3 — Feature engineering / preprocessing

Status: COMPLETE — 2026-08-21T12:02:36+05:30

### Files changed
- `app/ml/__init__.py`
- `app/ml/feature_contract.py`
- `app/ml/preprocessing.py`
- `app/repositories/model_training_repository.py`
- `app/services/training_cohort_service.py`
- `tests/test_feature_preprocessing.py`
- `Prompts/phase3_prompt_pack/11_PROGRESS_TRACKER.md`

### Feature contract
- version: 1
- SHA-256: `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`
- raw feature count: 11
- transformed feature count: 64 on full-data run 10

### Split
- seed: 42
- validation fraction: 0.20
- train customers: 11,229
- validation customers: 2,808
- train positives: 501; train unlabeled: 10,728
- validation positives: 125; validation unlabeled: 2,683
- customer overlap: 0

### Tests
- Focused: `python -m pytest -q tests/test_feature_preprocessing.py
  tests/test_training_cohort_service.py` → 27 passed in 16.04s; no warnings.
- Full: `python -m pytest -q` → 190 passed in 85.40s; no warnings reported.
- Compile: `python -m compileall -q app scripts tests` passed with no output.
- Dependency: `python -m pip check` → `No broken requirements found.`
- Diff: `git diff --check`, explicit trailing-whitespace scans, and the Step 3
  scope scan passed; informational LF-to-CRLF notices only.

### Evidence
- Centralized the versioned feature order/types, internal non-feature fields,
  adult age bounds (18–100), numeric validity rules, categorical normalization,
  preprocessing configuration, canonical JSON, and SHA-256 in one contract
  module. Reconstruction now imports this contract rather than owning duplicate
  feature lists.
- Numeric pipeline: explicit coercion/finite/range/integer validation, training-
  only median imputation, then `StandardScaler`. A numeric feature missing from
  every training row is a hard error rather than an invented median.
- Categorical pipeline: null/blank → `Unknown/Other`, surrounding whitespace
  trim, retained meaningful text, then one-hot encoding with unknown categories
  ignored safely.
- Deterministic split sorts by internal customer key, stratifies by PU label,
  uses seed 42, requires positive and unlabeled rows in both partitions, and
  returns feature matrices with neither `customer_id` nor `pu_label` in X.
- Leakage tests proved validation-only values do not affect numeric medians,
  validation-only categories do not enter the fitted vocabulary, campaign fields
  are rejected, customers never cross partitions, and no wall-clock date or
  estimator/model-fit logic exists in the Step 3 modules.
- Missing numeric and null/blank categorical fixtures transformed to finite
  matrices; invalid age/income/family values failed before imputation; unseen
  validation categories transformed without failure.
- Full-data run 10 timings: reconstruction 0.378673s, split 0.227185s,
  train fit plus train/validation transform 0.722166s, total 1.328024s.
- Full-data transformed shapes: training `(11229, 64)`, validation `(2808, 64)`;
  approximate sparse storage 1,527,148 and 381,892 bytes respectively.
- Full-data training-only medians: age 47, individual income 41,000, family count
  2. Category cardinalities: gender 3, state 27, marital 4, education 7,
  employment status 7, resident status 4, resident type 3, employment type 6.
- Metadata contains raw/transformed feature names and counts, category
  cardinalities, numeric imputation values, NumPy/pandas/scikit-learn versions,
  contract JSON/version/hash, and no raw customer values.

### Open issues
- None within Step 3. Adult bounds are deliberately hard validation, not silent
  clipping; later prospect scoring must apply the same contract.
- No PU estimator, diagnostic baseline, challenger, evaluation, model selection,
  model-run persistence, artifact writing, CLI, API, UI, or demographic scoring
  was implemented. Step 4 is not started.

---

## Step 4 — PU training

Status: COMPLETE — 2026-08-21T12:17:25+05:30

### Files changed
- `app/ml/pu_estimators.py`
- `app/ml/training.py`
- `tests/test_pu_training.py`
- `Prompts/phase3_prompt_pack/11_PROGRESS_TRACKER.md`

### Candidate A
- name: `ELKAN_NOTO_LOGISTIC`
- estimator: `pulearn.ElkanotoPuClassifier` with deterministic, bounded
  `sklearn.linear_model.LogisticRegression`
- runtime: fit 0.071990s; validation scoring 0.000331s
- warnings: none on full-data run 10
- fit status: FITTED; genuine PU
- labeling propensity `c`: 0.047463730845
- validation score range: 0.210658759639–4.223669404009; 2,808 finite,
  nonnegative, distinct scores

### Naive diagnostic baseline
- runtime: fit 0.031921s; validation scoring 0.000393s
- fit status: FITTED; explicitly `diagnostic_only_not_pu_learning`
- validation score range: 0.010760804712–0.199475456622; 2,808 finite,
  unit-interval, distinct scores

### Challenger
- name: `BAGGING_PU`
- runtime: fit 0.243872s; validation scoring 0.004990s
- status/skip reason: FITTED; no skip required; 10 estimators, one CPU job
- validation score range: 0.010976309799–0.192969742675; 2,808 finite,
  unit-interval, distinct scores

### Tests
- Focused: `python -m pytest -q tests/test_pu_training.py
  tests/test_feature_preprocessing.py tests/test_training_cohort_service.py` →
  35 passed in 16.09s; no warnings.
- Full: `python -m pytest -q` → 198 passed in 69.34s; no warnings reported.
- Compile: `python -m compileall -q app scripts tests` passed with no output.
- Dependency: `python -m pip check` → `No broken requirements found.`
- Diff: `git diff --check`, explicit trailing-whitespace scans, and the Step 4
  scope scan passed; informational LF-to-CRLF notices only.

### Open issues
- Full-data input: analysis run 10; seed 42; 64 transformed features; 11,229
  training customers (501 positive / 10,728 unlabeled); 2,808 validation
  customers (125 positive). Total three-candidate training wall time was
  0.357128s after reconstruction/splitting/preprocessing.
- The public label contract remains 1=known positive and 0=unlabeled. Only the
  Elkan–Noto package boundary converts unlabeled to its required `-1`; the base
  estimator receives 0/1. No hidden or sampled true-negative class is created.
- `pulearn 0.0.12` Elkan–Noto cannot apply its internal row deletion to SciPy
  sparse input. Training therefore performs a bounded dense conversion only for
  that candidate (5,749,248 bytes on run 10; hard cap 512 MiB) while retaining a
  sparse-compatible logistic solver/configuration. Naive and bagging training
  remain sparse.
- The package's Elkan–Noto `c` correction can produce scores above 1. Those
  finite nonnegative scores are intentionally not clipped because clipping
  creates top-score ties and damages ranking; metadata states that they are
  probability-like PU scores, not calibrated probabilities. Naive and bagging
  probabilities remain unit-interval.
- Same-seed full-data reruns produced byte-identical validation score arrays:
  Elkan–Noto SHA-256 `ce778ea198a5cca52a474279093426e2dd3a58ea0e2ba9ff7a3493db2b9d6594`,
  naive SHA-256 `31df22d04ae3f24c46780bb25f9fae032af58e18f928e043e8895a4954819279`,
  and bagging SHA-256 `a24dad43810cd69623331be56aa566c315d186a571f9c830c7f1c702c718f2e3`.
- Tests cover genuine Elkan–Noto and bagging fits, diagnostic-only baseline
  governance, score shape/range/finiteness, deterministic reruns, 0/1 label
  validation, all-positive/all-unlabeled/insufficient-positive rejection,
  feature-contract enforcement, captured warnings, and measured runtime skips.
- No observed-label metrics, top-slice metrics, evaluation, model selection,
  database model-run writes, artifact persistence, CLI, API, UI, or demographic
  scoring was implemented. Step 5 is not started.

---

## Step 5 — Evaluation / selection

Status: COMPLETE — 2026-08-21T12:49:15+05:30

### Files changed
- `app/ml/evaluation.py`
- `tests/test_model_evaluation.py`
- `Prompts/phase3_prompt_pack/11_PROGRESS_TRACKER.md`

### Candidate results

#### Elkan-Noto
- status/runtime: FITTED; fit 0.084770s; scoring 0.000634s
- observed-label ROC-AUC: 0.526873
- observed-label AP: 0.053176
- recall@5/@10/@20: 0.064 / 0.152 / 0.240
- lift@5/@10/@20: 1.274553 / 1.518918 / 1.199146
- known positives captured@5/@10/@20: 8 / 19 / 30
- positive mean/median score: 0.968460 / 0.926365
- unlabeled mean/median score: 0.927968 / 0.886590
- observed-label KS / mean separation: 0.069084 / 0.040493
- candidate quality flags: none

#### Challenger
- status/runtime: FITTED; fit 0.672412s; scoring 0.016649s
- observed-label ROC-AUC / AP: 0.534944 / 0.055552
- recall@5/@10/@20: 0.096 / 0.160 / 0.232
- lift@5/@10/@20: 1.911830 / 1.598861 / 1.159174
- known positives captured@5/@10/@20: 12 / 20 / 29
- positive mean/median score: 0.047089 / 0.045268
- unlabeled mean/median score: 0.044680 / 0.043142
- observed-label KS / mean separation: 0.086065 / 0.002409
- candidate quality flags: none

#### Naive diagnostic
- status/runtime: FITTED; fit 0.083506s; scoring 0.001027s
- observed-label ROC-AUC / AP: 0.535067 / 0.055167
- recall@5/@10/@20: 0.104 / 0.160 / 0.232
- lift@5/@10/@20: 2.071149 / 1.598861 / 1.159174
- known positives captured@5/@10/@20: 13 / 20 / 29
- positive mean/median score: 0.046883 / 0.045022
- unlabeled mean/median score: 0.044515 / 0.042870
- observed-label KS / mean separation: 0.073530 / 0.002368
- explicitly diagnostic-only and ineligible for official selection

### Selected official PU candidate
- `BAGGING_PU`

### Selection reason
- Bagging PU led the eligible genuine-PU candidates at the practically relevant
  top-10% slice: 20/125 positives captured, recall 0.160, and lift 1.598861,
  versus Elkan-Noto's 19/125, recall 0.152, and lift 1.518918. Bagging also had
  the higher observed-label KS separation (0.086065 versus 0.069084). The naive
  baseline tied Bagging at top 10% and led at top 5%, but was excluded by the
  frozen diagnostic-only governance rule rather than treated as PU fallback.

### Quality flags
- `OBSERVED_LABEL_METRICS_ONLY`
- This records the required limitation: diagnostics separate known positives
  from unlabeled observations, not true positives from true negatives.
- No selected-candidate low-count, low-variance, low-lift, worse-positive-score,
  propensity-instability, or challenger-runtime flag was raised.

### Tests
- Focused Step 2–5 regression: `python -m pytest -q
  tests/test_model_evaluation.py tests/test_pu_training.py
  tests/test_feature_preprocessing.py tests/test_training_cohort_service.py` →
  47 passed in 37.17s; no warnings.
- Full: `python -m pytest -q` → 210 passed in 137.01s; no warnings reported.
- Compile: `python -m compileall -q app scripts tests` passed with no output.
- Dependency: `python -m pip check` → `No broken requirements found.`
- Diff: `git diff --check` passed; informational LF-to-CRLF notices only.

### Evidence
- Full-data source: completed synthetic `analysis_run_id=10`; 14,037 matching
  observations/customers, 626 known positives, and 13,411 unlabeled. Training
  split was 11,229 (501 / 10,728); validation was 2,808 (125 / 2,683), observed
  positive-label prevalence 0.044516; transformed feature count 64.
- Full reconstruction through selection completed in 3.614612s. All three
  candidates produced finite, nonconstant scores and no captured warnings.
- Top slices use `max(1, ceil(n*k))` for 5%, 10%, and 20%. Exact ties use the
  stable positional index of the deterministic split, never PII; top-slice
  sizes on full data were 141, 281, and 562.
- Every fitted candidate records split context; honestly named observed-label
  ROC-AUC/AP with the contract disclaimer; top-slice counts, recall,
  concentration, and lift; positive/unlabeled count, mean, median, population
  standard deviation, p10/p25/p75/p90; empirical two-sample KS and mean
  separation; fit/scoring runtime; algorithm metadata; and tested package
  versions.
- Canonical JSON uses sorted compact keys and `allow_nan=False`. Tests prove it
  contains no customer identifier, PII value, or per-customer validation score.
  Non-finite or negative scores fail evaluation; constant genuine-PU candidates
  are flagged and cannot win; all-degenerate genuine candidates fail rather
  than falling back to the naive model.
- Read-only post-evaluation verification found zero `model_runs` rows and only
  `.gitkeep` under `artifacts/models/`. No model-run persistence, model artifact,
  CLI, API, UI, or demographic scoring was added.

### Open issues
- None within Step 5. Metrics are synthetic POC evidence and not a claim of
  real-world model performance or calibrated population probabilities.
- Step 6 must persist the selected estimator/preprocessor and bounded canonical
  metadata transactionally, implement checksum/reload verification and the CLI,
  and retain the selected runtime object without storing validation rows. Step 6
  is not started.

---

## Step 6 — Persistence / CLI

Status: COMPLETE — 2026-08-21T13:27:30+05:30

### Files changed
- `app/repositories/model_run_repository.py`
- `app/services/model_training_service.py`
- `scripts/train_pu_model.py`
- `tests/test_model_persistence.py`
- `Prompts/phase3_prompt_pack/11_PROGRESS_TRACKER.md`

### Model run
- model_run_id: 1
- analysis_run_id: 10
- model name: `Holiday Electronics Lookalike`
- status: `COMPLETED`
- selected candidate: `BAGGING_PU`
- customers: 14,037; known positives: 626; unlabeled: 13,411
- validation positives: 125; validation lift@10%: 1.598861209964413
- quality flags: `OBSERVED_LABEL_METRICS_ONLY`
- artifact relative path:
  `artifacts/models/model_run_000001/pu_model.joblib`
- artifact bytes: 10,108
- artifact SHA-256:
  `04913a2eb766d116b2e73ea9842ecf25914b3360f35e1fee65860351841bf1de`
- reload verification: PASS — the loaded preprocessor transformed the first 128
  validation rows and the loaded estimator reproduced pre-persistence scores at
  `rtol=1e-12`, `atol=1e-12`; an independent loader/hash check also passed

### CLI
- command: `python scripts/train_pu_model.py --analysis-run-id 10
  --model-name "Holiday Electronics Lookalike" --json`
- exit: 0
- JSON parse: PASS — one bounded object on standard output with model/analysis
  IDs, `COMPLETED`, selected candidate, counts, lift, quality flags, relative
  artifact path, and SHA-256; no absolute path or internal diagnostic

### Tests
- Focused persistence/CLI: `python -m pytest -q
  tests/test_model_persistence.py` → 5 passed in 72.32s; no warnings.
- Focused Step 2–6 regression: `python -m pytest -q
  tests/test_model_persistence.py tests/test_model_evaluation.py
  tests/test_pu_training.py tests/test_feature_preprocessing.py
  tests/test_training_cohort_service.py` → 52 passed in 70.03s; no warnings.
- Full: `python -m pytest -q` → 215 passed in 184.65s; no warnings reported.
- Compile: `python -m compileall -q app scripts tests` passed with no output.
- Dependency: `python -m pip check` → `No broken requirements found.`
- Diff/whitespace: `git diff --check` and explicit new-file trailing-whitespace
  scan passed; informational LF-to-CRLF notices only.
- Populated validation: `python scripts/validate_data.py --json` → overall `OK`
  in 20.572124s; 125,000 customers, 570,000 campaign sales, 5,000,000
  demographics, zero invalid customer references, zero PU violations, and all
  23 required indexes present.

### Evidence
- Lifecycle is explicit and state-guarded: insert `RUNNING`; reconstruct and
  reconcile; split/preprocess/train/evaluate; serialize a versioned payload to a
  UUID temporary file; atomically replace the final path; reload and rescore;
  hash; then update the same row to `COMPLETED` in one SQLite transaction.
- Any post-insert exception captures a bounded internal traceback, removes only
  the new temporary/final file and run directory, and transitions the row from
  `RUNNING` to `FAILED`. An injected completion-transaction failure proved that
  no apparently valid artifact remains without matching completed metadata.
- The completed row persists the exact source analysis ID, seed/fraction and
  reconciled split counts, canonical feature contract and SHA-256,
  preprocessing metadata, selected hyperparameters, full bounded Step 5
  evaluation JSON, exact Python/NumPy/pandas/SciPy/scikit-learn/pulearn/joblib
  versions, relative artifact path, SHA-256, and no error.
- Artifact payload keys are exactly artifact/feature-contract versions and hash,
  raw feature order, fitted preprocessor, fitted selected estimator, and selected
  candidate. Tests and payload inspection found no customer IDs, PII, raw rows,
  training/validation matrices, or per-customer validation scores.
- The reusable verified loader rejects absent files, checksum corruption,
  unsafe/absolute paths, incompatible payloads, non-completed rows, and
  candidate/metadata mismatch before returning a scoring payload.
- CLI tests exercised real successful training and a failing source ID in
  subprocesses: success returned 0, failure returned 1, both JSON outputs parsed,
  and neither exposed absolute paths or internal tracebacks.
- `git check-ignore` resolves the real joblib artifact to the existing
  `artifacts/models/*` rule. The populated database and artifact are local
  runtime state, not source changes.

### Open issues
- None within Step 6. The selected artifact is a synthetic-data POC model, not a
  real-world performance or probability-calibration claim.
- No model inspection HTTP endpoint, training API/UI, prospect/demographic
  scoring, propensity table, audience workflow, or Step 7 hardening work was
  added. Step 7 is not started.

---

## Step 7 — Hardening / final validation

Status: COMPLETE — 2026-08-21T13:48:06+05:30

### Files changed in Step 7
- `README.md`
- `app/services/model_training_service.py`
- `tests/test_model_persistence.py`
- `tests/test_phase3_hardening.py`
- `docs/PHASE_3_IMPLEMENTATION_SUMMARY.md`
- `Prompts/phase3_prompt_pack/10_PHASE_3_ACCEPTANCE_CHECKLIST.md`
- `Prompts/phase3_prompt_pack/11_PROGRESS_TRACKER.md`

### Full commands
- pip check: `python -m pip check` → `No broken requirements found.`
- pytest: `python -m pytest -q` → 219 passed in 126.75s; no warnings
  reported. This includes all Phase 1/2 API, schema, reconciliation, historical
  service/UI, and frontend regressions.
- compileall: `python -m compileall -q app scripts tests` passed with no output.
- git diff --check: passed; explicit Step 7/new-file trailing-whitespace scan
  also passed; informational LF-to-CRLF notices only.
- data validation: `python scripts/validate_data.py --json` → overall `OK` in
  21.395477s; schema v3; 125,000 customers, 570,000 campaign sales, 5,000,000
  demographics; zero invalid customer references and PU consistency violations;
  all 23 indexes present.
- focused hardening/persistence/frontend/Historical UI: 37 passed in 62.12s.

### Same-seed rerun
- model runs compared: 1 and 2; both analysis 10, seed 42, validation 0.20,
  challenger enabled, status `COMPLETED`
- counts equal: PASS — 14,037 selected = 626 positive + 13,411 unlabeled;
  train 11,229; validation 2,808; validation positives 125
- split reproducible: PASS — train membership SHA-256
  `1fa32707a64de921f384940981b92680aaf40208e1fdae120b1c08f509f807b8`;
  validation membership SHA-256
  `d5a507cc9b4d5e2170054ce55f447a9dd6bd74ffe6b679877bf9903ba73b64c7`
- feature hash equal: PASS — both
  `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`
- selected candidate equal: PASS — `BAGGING_PU` in both
- metrics tolerance: PASS — all non-runtime evaluation metadata was exactly
  equal; canonical comparison SHA-256
  `3f2c2de650443d7c96cd0b07f9505d55aa5ff2ff50f3762cf8e4822d3a80b43a`
- prediction tolerance: PASS — first 128 reloaded validation scores had identical
  SHA-256 `57298cf46af64d8d1d85a3f405176344b39cad88f7536722eb0206817c366c67`;
  maximum absolute difference 0.0 at `rtol=1e-12`, `atol=1e-12`
- artifact reproducibility: bytes were identical; both 10,108 bytes with SHA-256
  `04913a2eb766d116b2e73ea9842ecf25914b3360f35e1fee65860351841bf1de`
- preprocessing metadata, hyperparameters, and library versions: exact match

### Full-data performance
- run 2 stage seconds: reconstruction 0.509392; split 0.163546; preprocessing
  0.503757; candidate training 0.365268; evaluation/selection 0.054028;
  persistence/reload/checksum 0.091396; governed total 1.857761
- transformed features: 64 from the exact 11-feature raw contract
- approximate memory/storage: reconstructed frame 8,219,363 bytes; training
  sparse matrix 1,527,148 bytes; validation sparse matrix 381,892 bytes
- SQL reduces 570,000 observations to 14,037 customer rows before pandas.
  Trace tests prove no demographics query/N+1 path; there is no grid search,
  unbounded parallelism, or 5M scoring scan.
- Bagging challenger remained bounded at 10 estimators/one CPU job and completed;
  no runtime skip was necessary.

### Scope scan
- propensity scoring absent: PASS — no table, API, script, service, or executable
  application reference
- demographics scoring absent: PASS — prospect-table references remain confined
  to unchanged Phase 1 import/status/overview code; training boundary has none
- Model Training UI disabled: PASS — hardening/frontend tests verify three
  disabled later-phase navigation buttons and no model-training router
- customer/person mapping absent: PASS — explicit source scan returned no mapping
- PII feature leakage absent: PASS — exact feature/artifact/metadata tests and
  hardening scan; no raw customer rows or ID list persisted
- Audience Explorer/campaign builder/export: absent; navigation remains disabled
- prohibited infrastructure: absent from requirements/application/scripts
- source LFS data: unchanged; no `data/` status/diff and no LFS object change
- runtime state: no `.db` or `.joblib` is tracked; database and both artifacts
  resolve to explicit `.gitignore` rules

### Final changed-file manifest
- Foundation/schema/dependencies: `.gitignore`, `requirements.txt`,
  `app/database/schema.py`, `artifacts/models/.gitkeep`,
  `tests/test_phase3_schema.py`, and the Phase 1 schema/API/reconciliation/health
  expectation tests updated for additive schema v3.
- Cohort: `app/repositories/historical_repository.py`,
  `app/repositories/model_training_repository.py`,
  `app/services/training_cohort_service.py`,
  `tests/test_training_cohort_service.py`.
- ML: `app/ml/__init__.py`, `app/ml/feature_contract.py`,
  `app/ml/preprocessing.py`, `app/ml/pu_estimators.py`, `app/ml/training.py`,
  `app/ml/evaluation.py`, `tests/test_feature_preprocessing.py`,
  `tests/test_pu_training.py`, `tests/test_model_evaluation.py`.
- Persistence/CLI: `app/repositories/model_run_repository.py`,
  `app/services/model_training_service.py`, `scripts/train_pu_model.py`,
  `tests/test_model_persistence.py`.
- Hardening/docs: `README.md`, `docs/PHASE_3_IMPLEMENTATION_SUMMARY.md`,
  `tests/test_phase3_hardening.py`, Phase 2 SHA clarification, this tracker, and
  `10_PHASE_3_ACCEPTANCE_CHECKLIST.md`.
- Ignored local runtime outputs (not source manifest): `data/campaign_poc.db` and
  `artifacts/models/model_run_000001|000002/pu_model.joblib`.

### Known limitations
- Synthetic observed-label metrics do not establish population ground truth,
  causal/fairness outcomes, calibrated conversion probabilities, or production
  performance.
- Elkan-Noto/pulearn 0.0.12 requires a bounded dense training conversion; full
  data used 5,749,248 bytes under a 512 MiB hard cap. Its corrected scores may
  exceed 1 and are ranking scores, not calibrated probabilities.
- Local synchronous CLI, SQLite, and trusted-local joblib storage fit this
  single-user POC but are not production multi-user/model-registry infrastructure.
- Runtime varies with CPU/storage/cache/load; recorded timings are sanity evidence,
  not an SLA.
- No prospect scoring, propensity table, Audience Explorer, campaign workflow,
  training API/background job, active Model Training UI, or customer/person
  linkage exists by design.

### Acceptance checklist
- PASS: 119 checked items, including every Critical item
- FAIL: 0
- PARTIAL: 0
- NOT TESTED: 0
- decision evidence is recorded in
  `Prompts/phase3_prompt_pack/10_PHASE_3_ACCEPTANCE_CHECKLIST.md`

### Final Phase 4 recommendation
- **GO FOR PHASE 4.** Phase 3 is regression-safe, PU-correct, leakage-safe,
  persisted, reload/checksum verified, performant for the local POC, and exactly
  reproducible on the same seed/input. Phase 4 should consume a verified
  `COMPLETED model_run_id` and reuse the training service for orchestration/UI.
  It must retain the frozen no-scoring/no-audience/no-campaign/no-linkage boundary
  unless separately approved.
