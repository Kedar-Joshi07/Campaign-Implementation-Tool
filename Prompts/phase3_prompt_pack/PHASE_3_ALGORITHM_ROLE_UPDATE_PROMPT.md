# Phase 3 Algorithm Role Update Prompt
## PU Bagging Primary + Elkan–Noto Challenger + Naive Logistic Diagnostic Control

Repository:

`https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Authoritative implemented Phase 3 baseline:

`d2d46bdc08a02a27e4c6a7069857354a2e32a1d6`

Commit message at this baseline:

`Phase 3 Implementation and phase 4 handoff completed.`

---

# 1. PURPOSE OF THIS UPDATE

Phase 3 is already implemented. Do **not** rebuild Phase 3 from scratch.

This is a controlled **post-Phase-3 algorithm-role update** to align the implemented modeling engine with the revised modeling decision:

```text
PRIMARY
PU Bagging + Logistic Regression

CHALLENGER 1
Elkan–Noto + Logistic Regression

DIAGNOSTIC CONTROL
Naive Logistic Regression
(U temporarily treated as N for diagnostic comparison only)
```

The current implementation already contains all three algorithms. The task is to change their **governed roles, execution semantics, selection policy, metadata, CLI wording, tests, documentation, and Phase 4 handoff** without changing the frozen data/feature architecture.

The update must preserve the existing successful Phase 3 foundation:

- completed Phase 2 `analysis_run_id` input;
- customer-grain cohort reconstruction;
- known-positive vs unlabeled semantics;
- 11 frozen prospect-compatible features;
- leakage-safe preprocessing;
- deterministic train/validation split;
- PU-aware metrics;
- SQLite `model_runs`;
- joblib artifact persistence;
- SHA-256 verification;
- artifact reload/rescore verification;
- no prospect scoring yet;
- no demographic/customer linkage;
- no active Model Training UI yet.

---

# 2. CURRENT IMPLEMENTATION — UNDERSTAND BEFORE EDITING

At baseline `d2d46bdc08a02a27e4c6a7069857354a2e32a1d6`, inspect at minimum:

```text
app/ml/pu_estimators.py
app/ml/training.py
app/ml/evaluation.py
app/ml/preprocessing.py
app/ml/feature_contract.py

app/services/model_training_service.py
app/repositories/model_run_repository.py

scripts/train_pu_model.py

tests/test_pu_training.py
tests/test_model_evaluation.py
tests/test_model_persistence.py
tests/test_phase3_hardening.py

docs/PHASE_3_IMPLEMENTATION_SUMMARY.md

Prompts/phase3_prompt_pack/
```

Current behavior that must be deliberately changed:

1. `ELKAN_NOTO_LOGISTIC` is presently treated in tests/docs as the required/primary PU candidate.
2. `BAGGING_PU` is presently treated as the optional challenger.
3. `run_challenger` currently controls whether Bagging PU runs.
4. Bagging PU can currently be marked:
   - `SKIPPED_DISABLED`
   - `SKIPPED_RUNTIME`
   - `SKIPPED_INCOMPATIBLE`
5. Elkan–Noto failures currently behave more like required-model failures.
6. Current evaluation can select either genuine PU model based on ranking metrics.
7. The current tie-break explicitly favors Elkan–Noto.
8. The naive Logistic Regression is already diagnostic-only and must remain ineligible.
9. The real Phase 3 full-data evidence already selected `BAGGING_PU`; preserve that evidence as historical evidence, then perform a new post-update validation.

Do not blindly rename variables without understanding these existing semantics.

---

# 3. REVISED AUTHORITATIVE MODEL ROLE CONTRACT

Create one authoritative model-role contract in code.

Recommended constants:

```python
PRIMARY_MODEL_NAME = BAGGING_PU_NAME
CHALLENGER_1_MODEL_NAME = ELKAN_NOTO_NAME
DIAGNOSTIC_CONTROL_NAME = NAIVE_BASELINE_NAME
MODEL_ROLE_POLICY_VERSION = "2"
```

Recommended explicit roles:

```text
PRIMARY
CHALLENGER_1
DIAGNOSTIC_CONTROL
```

Do not infer a model role only from UI text.

Each `CandidateTrainingResult` should expose an explicit role, for example:

```python
candidate_role: Literal[
    "PRIMARY",
    "CHALLENGER_1",
    "DIAGNOSTIC_CONTROL",
]
```

or an equivalently strict enum/constant-based implementation.

The model names themselves may remain:

```text
BAGGING_PU
ELKAN_NOTO_LOGISTIC
NAIVE_PU_LABEL_BASELINE
```

This avoids breaking older model-run metadata unnecessarily.

The **roles**, not the legacy names, are what change.

---

# 4. PRIMARY — PU BAGGING + LOGISTIC REGRESSION

`BAGGING_PU` becomes the mandatory primary model.

Implementation:

```text
pulearn.BaggingPuClassifier
        +
sklearn.linear_model.LogisticRegression
```

Preserve the existing Logistic Regression base estimator unless testing demonstrates a compatibility issue.

## Primary model requirements

The primary must:

- use known-positive = `1`;
- use unlabeled = `0` according to the tested Bagging PU library contract;
- use deterministic `random_state`;
- use bounded estimator count;
- use bounded CPU (`n_jobs=1` for this POC unless explicitly changed and tested);
- return finite nonconstant positive-class scores;
- produce scores within `[0,1]` when the underlying classifier contract does so;
- record hyperparameters and runtime;
- be persisted when the governed model run completes.

## Primary failure semantics

Because Bagging PU is now PRIMARY:

**Do not skip it merely because it exceeds the old challenger runtime limit.**

The existing behavior in which Bagging PU can become:

```text
SKIPPED_RUNTIME
```

because it exceeds `DEFAULT_CHALLENGER_RUNTIME_LIMIT_SECONDS`
must not apply to the primary model.

Runtime should be measured and recorded, but a soft POC runtime threshold must not convert the required primary into an optional skipped model.

If Bagging PU:

- cannot fit;
- cannot score;
- returns non-finite scores;
- returns degenerate constant scores that violate the quality contract;
- is incompatible with the installed tested library;

then the governed training run should fail clearly rather than silently switching the official model family.

Do not automatically fall back to the naive model.

Do not silently promote Elkan–Noto as the primary artifact.

---

# 5. CHALLENGER 1 — ELKAN–NOTO + LOGISTIC REGRESSION

`ELKAN_NOTO_LOGISTIC` becomes `CHALLENGER_1`.

Implementation remains:

```text
pulearn.ElkanotoPuClassifier
        +
sklearn.linear_model.LogisticRegression
```

Preserve:

- deterministic random seed;
- Elkan–Noto holdout logic;
- labeling propensity `c`;
- bounded dense conversion/memory protection;
- nonnegative finite score validation;
- documented fact that corrected scores may exceed 1 and are ranking scores, not calibrated probabilities.

## Challenger execution

By default, Challenger 1 should run.

Replace ambiguous Bagging-oriented options such as:

```text
run_challenger
```

with an explicit Elkan-oriented concept such as:

```text
run_elkan_challenger
```

or a more future-proof:

```text
challenger_policy
```

For this update, keep the implementation simple.

Recommended:

```python
run_elkan_challenger: bool = True
```

If disabled:

```text
ELKAN_NOTO_LOGISTIC
role = CHALLENGER_1
status = SKIPPED_DISABLED
```

If Elkan–Noto cannot run because of its bounded dense-memory compatibility requirement or an estimator/library incompatibility, record a safe challenger skip/failure state such as:

```text
SKIPPED_INCOMPATIBLE
```

with a bounded reason.

A challenger failure must **not** turn the naive diagnostic into an official model.

A challenger failure also does not necessarily invalidate a technically valid primary Bagging model.

---

# 6. DIAGNOSTIC CONTROL — NAIVE LOGISTIC REGRESSION

Preserve:

```text
NAIVE_PU_LABEL_BASELINE
```

but make its role explicit:

```text
DIAGNOSTIC_CONTROL
```

Logic:

```text
known positive → 1
unlabeled      → temporarily treated as 0
```

This is intentional only to provide a reference supervised classifier.

Required metadata:

```json
{
  "role": "DIAGNOSTIC_CONTROL",
  "is_genuine_pu": false,
  "unlabeled_treatment": "temporarily_treated_as_negative_for_diagnostic_only",
  "eligible_for_selection": false
}
```

It must never:

- be called a PU learner;
- be called the primary;
- be persisted as the selected production/look-alike estimator;
- win because of ROC-AUC, AP, accuracy, precision, or any other observed-label metric;
- act as fallback if genuine PU training fails.

If practical, keep this control mandatory because it is useful for comparing how much PU treatment changes ranking behavior.

---

# 7. REVISED TRAINING EXECUTION ORDER

Change the conceptual order to:

```text
Validated customer-grain training cohort
        ↓
Leakage-safe preprocessing
        ↓
PRIMARY
BAGGING_PU + Logistic Regression
        ↓
CHALLENGER_1
ELKAN_NOTO_LOGISTIC + Logistic Regression
        ↓
DIAGNOSTIC_CONTROL
NAIVE_PU_LABEL_BASELINE
        ↓
Evaluate all completed candidates
        ↓
Persist PRIMARY Bagging model
        ↓
Store challenger/control comparison metrics
```

The order should also be reflected in:

- `TrainingCandidateSet`;
- evaluation snapshots;
- documentation;
- CLI summary where relevant.

Recommended refactor:

```python
@dataclass(frozen=True)
class TrainingCandidateSet:
    primary: CandidateTrainingResult
    challenger_1: CandidateTrainingResult
    diagnostic_control: CandidateTrainingResult
```

If changing these field names creates unnecessary compatibility risk, preserve existing attributes but expose explicit aliases/role metadata.

Do not retain code where `elkan_noto` is semantically named or tested as “primary.”

---

# 8. REVISED MODEL SELECTION POLICY

This is the most important behavioral change.

## Primary selection rule

If `BAGGING_PU`:

- has status `FITTED`;
- is genuine PU;
- returns finite, nonconstant scores;
- passes mandatory contract/quality validation;

then:

```text
selected_candidate = BAGGING_PU
selected_role = PRIMARY
```

The primary is selected because it is the **frozen champion model policy**, not because a generic `max()` happened to choose it.

## Challenger comparison

Elkan–Noto must still receive the same PU-aware evaluation metrics when it runs.

Compare:

- observed-label ROC-AUC — diagnostic only;
- observed-label average precision — diagnostic only;
- known-positive recall @ 5%, 10%, 20%;
- known-positive lift @ 5%, 10%, 20%;
- KS separation;
- score mean/median distributions;
- runtime;
- Elkan labeling propensity stability;
- quality flags.

Add explicit comparison metadata, for example:

```json
{
  "primary_candidate": "BAGGING_PU",
  "challenger_1": "ELKAN_NOTO_LOGISTIC",
  "diagnostic_control": "NAIVE_PU_LABEL_BASELINE",
  "selected_candidate": "BAGGING_PU",
  "selection_policy": "PRIMARY_ROLE_GOVERNED",
  "challenger_outperformed_primary": false,
  "challenger_comparison": {
      "top10_lift_delta": 0.0,
      "top10_recall_delta": 0.0,
      "observed_label_ap_delta": 0.0,
      "fit_seconds_delta": 0.0
  }
}
```

## Do not silently promote Challenger 1

For this POC update, if Elkan–Noto scores better on some metrics:

- record it;
- surface a quality/advisory flag such as `CHALLENGER_OUTPERFORMED_PRIMARY`;
- record which metrics were better;
- keep `BAGGING_PU` as selected primary as long as the primary passes mandatory validity/quality gates.

Do not automatically convert Challenger 1 into the official artifact without a separately approved promotion policy.

This keeps the model governance explicit and makes future champion/challenger promotion a deliberate decision rather than an accidental metric tie-break.

## Remove Elkan tie preference

The current selection key contains an Elkan-specific tie preference.

Remove that behavior.

There should be no generic tie-break that prefers Elkan–Noto.

---

# 9. EVALUATION CONTRACT UPDATE

Bump:

```text
EVALUATION_CONTRACT_VERSION
```

from:

```text
1
```

to:

```text
2
```

because candidate-role and selection semantics have changed.

Do not change the mathematical definitions of the existing PU-aware metrics unless a bug is found.

Preserve:

```text
known_positive_recall_at_k
known_positive_concentration_at_k
known_positive_lift_at_k

k = 5%, 10%, 20%
```

Preserve the disclaimer:

> Observed-label metrics measure separation of labeled positives from unlabeled observations, not true positives from true negatives.

Add to every candidate snapshot:

```text
candidate_role
eligible_for_official_selection
```

Expected:

```text
BAGGING_PU
candidate_role = PRIMARY
eligible_for_official_selection = true

ELKAN_NOTO_LOGISTIC
candidate_role = CHALLENGER_1
eligible_for_official_selection = false under Phase 3 role-governed policy

NAIVE_PU_LABEL_BASELINE
candidate_role = DIAGNOSTIC_CONTROL
eligible_for_official_selection = false
```

Add top-level:

```text
model_role_policy_version
primary_candidate
challenger_candidates
diagnostic_controls
selection_policy
```

No customer IDs or validation score arrays should enter persisted evaluation JSON.

---

# 10. QUALITY GATES

Preserve existing quality flags such as:

```text
LOW_POSITIVE_COUNT
LOW_SCORE_VARIANCE
LOW_TOP10_LIFT
POSITIVE_SCORE_DISTRIBUTION_WORSE
PU_PROPENSITY_ESTIMATE_UNSTABLE
OBSERVED_LABEL_METRICS_ONLY
```

Revise challenger-specific flags where necessary.

For example, the current:

```text
CHALLENGER_SKIPPED_RUNTIME
```

should apply to Elkan–Noto only if the updated challenger policy supports runtime skipping.

Add if appropriate:

```text
CHALLENGER_1_SKIPPED
CHALLENGER_OUTPERFORMED_PRIMARY
PRIMARY_LOW_TOP10_LIFT
```

Do not fail the primary solely because Challenger 1 is unavailable.

Do fail the governed run if the primary itself cannot satisfy the minimum model contract.

---

# 11. MODEL ARTIFACT

The final persisted artifact must contain:

```text
preprocessor
+
BAGGING_PU fitted primary estimator
```

for successful updated model runs.

Expected:

```text
selected_candidate = BAGGING_PU
```

Add role-policy metadata to the artifact only if useful, for example:

```text
selected_role = PRIMARY
model_role_policy_version = 2
```

If artifact payload keys change, either:

1. bump `ARTIFACT_VERSION` to `"2"`, **or**
2. preserve artifact version 1 if no payload contract changes are necessary.

Do not bump artifact version just for documentation changes.

Existing historical Phase 3 model artifacts created before this update must remain understandable as historical artifacts.

Do not rewrite old SQLite model rows or artifact files in place.

New model runs created after this update should use the new role policy.

---

# 12. MODEL_RUNS / SQLITE

Prefer **no schema migration** unless an actual persistent relational field is required.

The existing table already stores:

```text
algorithm
selected_candidate
hyperparameters_json
metrics_json
library_versions_json
artifact_path
artifact_sha256
```

The revised role information can be stored safely inside:

```text
metrics_json
hyperparameters_json
```

and selected Bagging information in existing columns.

Do not create schema version 4 solely to store redundant candidate role strings.

If a migration is genuinely necessary, justify it before implementing.

---

# 13. SERVICE API UPDATE

Update:

```text
app/services/model_training_service.py
```

Current:

```python
run_challenger: bool = True
```

is ambiguous and currently means Bagging challenger.

Change it so Bagging is always the primary.

Recommended public service signature:

```python
train_and_persist_model(
    ...,
    run_elkan_challenger: bool = True,
)
```

Do not expose an option that disables the primary Bagging model.

Training should call the candidate engine under the revised role contract.

The selected model persisted by `_artifact_payload(...)` must be Bagging for a valid completed run.

The summary should include:

```text
primary_candidate
challenger_1
diagnostic_control
selected_candidate
selection_policy
```

along with existing counts/runtime/artifact data.

---

# 14. CLI UPDATE

Update:

```text
scripts/train_pu_model.py
```

Replace:

```text
--run-challenger / --no-run-challenger
```

whose current meaning is Bagging PU.

Recommended:

```text
--run-elkan-challenger
--no-run-elkan-challenger
```

Default:

```text
enabled
```

Bagging PU must always run.

CLI human-readable output should make the role clear:

```text
Primary model: BAGGING_PU
Challenger 1: ELKAN_NOTO_LOGISTIC (FITTED)
Diagnostic control: NAIVE_PU_LABEL_BASELINE
Selected model: BAGGING_PU
Selection policy: PRIMARY_ROLE_GOVERNED
```

Keep existing:

- analysis/model IDs;
- counts;
- lift;
- artifact path;
- SHA-256.

JSON mode must remain bounded and machine-readable.

---

# 15. BACKWARD COMPATIBILITY

Existing Phase 3 model runs and artifacts are historical records.

Do not mutate them.

The loader must continue to load a valid old completed artifact if its artifact version and metadata are supported.

New training runs should record:

```text
model_role_policy_version = 2
```

Old runs that lack that field may be interpreted as legacy Phase 3 selection policy:

```text
model_role_policy_version = 1
```

only where required for inspection/backward compatibility.

Do not silently claim an old Elkan-selected model was produced under the new Bagging-primary policy.

---

# 16. TEST UPDATES — REQUIRED

## A. `tests/test_pu_training.py`

Change expectations from:

```text
Elkan = primary
Bagging = challenger
```

to:

```text
Bagging = PRIMARY
Elkan = CHALLENGER_1
Naive = DIAGNOSTIC_CONTROL
```

Add/assert:

- Bagging role = PRIMARY.
- Bagging always runs for normal training.
- Bagging cannot be disabled by a challenger flag.
- Bagging runtime is measured but does not create `SKIPPED_RUNTIME` because it is primary.
- Bagging fit/scoring failure raises `TrainingAlgorithmError`.
- Elkan role = CHALLENGER_1.
- Elkan can be disabled explicitly.
- Elkan bounded incompatibility is recorded without silently invalidating a valid Bagging primary.
- Naive role = DIAGNOSTIC_CONTROL.
- Naive `is_genuine_pu = False`.
- same seed reproduces all fitted candidates.

## B. `tests/test_model_evaluation.py`

Update/remove tests that currently require Elkan preference.

Specifically revise the current deterministic tie test that expects:

```text
selected_candidate == ELKAN_NOTO_NAME
```

New expectation:

```text
selected_candidate == BAGGING_PU_NAME
```

because Bagging is the governed primary.

Add tests:

1. Bagging valid + Elkan better on a metric:
   - Bagging still selected.
   - `CHALLENGER_OUTPERFORMED_PRIMARY` advisory metadata/flag recorded.
2. Bagging valid + Elkan identical:
   - Bagging selected.
3. Bagging invalid/constant:
   - governed run/evaluation fails according to primary-quality contract;
   - do not promote naive.
4. Naive has perfect observed-label metrics:
   - remains diagnostic-only;
   - Bagging selected if valid.
5. Elkan unavailable:
   - Bagging can still be selected if valid.
6. evaluation JSON contains role-policy version and no IDs/PII.

## C. `tests/test_model_persistence.py`

Current helper disables the Bagging challenger:

```python
run_challenger=False
```

This must be changed.

The primary Bagging model must still train and be persisted.

Add assertions:

```text
selected_candidate == BAGGING_PU
artifact estimator is the Bagging PU primary
role policy == 2
```

Test with:

```text
run_elkan_challenger=False
```

and prove the artifact is still Bagging.

## D. CLI tests

Assert:

- new challenger flag semantics;
- Bagging cannot be disabled;
- JSON identifies roles;
- successful selected candidate is `BAGGING_PU`.

## E. Phase 3 hardening

Add scope/contract tests ensuring:

- no demographic scoring introduced;
- no propensity table;
- no active Model Training UI;
- no customer/person linkage;
- feature contract unchanged;
- model role policy v2 is present.

---

# 17. DO NOT CHANGE THESE FROZEN PARTS

Do not alter the 11 raw feature contract:

```text
age
gender
state
individual_yearly_income
marital_status
education
employment_status
resident_status
resident_type
family_member_count
type_of_employment
```

Do not add behavioral features.

Do not use:

- purchase history;
- engagement history;
- spend;
- recency;
- response counts;
- campaign IDs;
- product IDs;
- PII;
- ethnicity;
- religion;
- `person_id`.

Do not alter Phase 2 P/U cohort semantics.

Do not score the 5M demographic universe.

Do not build:

- propensity table;
- scoring API;
- Audience Explorer;
- Campaign Builder;
- export;
- model training UI;
- background job orchestration.

Those remain later-phase concerns.

---

# 18. DOCUMENTATION UPDATE

Update:

```text
docs/PHASE_3_IMPLEMENTATION_SUMMARY.md
README.md
Prompts/phase3_prompt_pack/11_PROGRESS_TRACKER.md
Prompts/phase3_prompt_pack/10_PHASE_3_ACCEPTANCE_CHECKLIST.md
Prompts/phase3_prompt_pack/12_PHASE_4_HANDOFF_CONTRACT.md
```

Do not erase historical evidence from the original Phase 3 implementation.

Add a clearly dated/identified post-Phase-3 update section.

Document:

```text
PRIMARY
BAGGING_PU + Logistic Regression

CHALLENGER_1
ELKAN_NOTO_LOGISTIC + Logistic Regression

DIAGNOSTIC_CONTROL
NAIVE_PU_LABEL_BASELINE
```

Explain:

- unlabeled is not negative;
- the naive model treats U as N only for diagnostic comparison;
- Bagging is the frozen primary look-alike ranking model;
- Elkan–Noto provides an independent PU challenger;
- challenger metrics are recorded;
- challenger does not silently replace primary under policy version 2;
- observed-label metrics are not true-negative performance;
- the score is a look-alike/PU ranking score, not a guaranteed calibrated purchase probability.

Update the Phase 4 handoff so Phase 4 knows:

```text
selected primary artifact = Bagging PU under role policy v2
```

for new model runs.

---

# 19. FULL-DATA VALIDATION

After implementation, use the same full-data Phase 3 reference analysis where available:

```text
analysis_run_id = 10
conversion_definition = ATTRIBUTED_PURCHASE
```

Do not hard-code this ID in production logic.

Create a **new** model run.

Record all three:

## PRIMARY — Bagging PU

- fit status;
- fit seconds;
- scoring seconds;
- observed-label ROC-AUC diagnostic;
- observed-label AP diagnostic;
- recall @ 5/10/20%;
- lift @ 5/10/20%;
- KS;
- score distribution;
- quality flags.

## CHALLENGER 1 — Elkan–Noto

Same metrics plus:

```text
labeling_propensity_c
```

and challenger status.

## DIAGNOSTIC CONTROL — Naive Logistic

Same comparable ranking diagnostics, clearly labeled diagnostic-only.

Then prove:

```text
selected_candidate = BAGGING_PU
candidate_role = PRIMARY
```

for a valid Bagging run.

Compare the challenger to the primary and record deltas.

Do not claim one model is objectively better in the real world based only on synthetic observed-label results.

---

# 20. REPRODUCIBILITY

Run the updated model twice using:

```text
same analysis_run_id
same random seed
same validation fraction
same challenger configuration
```

Verify:

- cohort counts match;
- split fingerprints match;
- feature contract hash unchanged;
- primary candidate is Bagging in both;
- candidate role metadata identical;
- non-runtime metrics equal/tolerance-equivalent;
- validation scores equal/tolerance-equivalent;
- persisted artifact reload results match.

Record exact evidence.

---

# 21. REQUIRED COMMANDS BEFORE COMPLETION

Run:

```text
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
python scripts/validate_data.py --json
```

Run focused tests for:

```text
tests/test_pu_training.py
tests/test_model_evaluation.py
tests/test_model_persistence.py
tests/test_phase3_hardening.py
```

Record exact counts/results.

---

# 22. ACCEPTANCE CRITERIA

The update is complete only if all are true:

- [ ] Baseline SHA `d2d46bdc08a02a27e4c6a7069857354a2e32a1d6` was reviewed before editing.
- [ ] Existing Phase 1/2/3 regression tests pass after updates.
- [ ] `BAGGING_PU` is explicitly role `PRIMARY`.
- [ ] Bagging uses Logistic Regression base estimator.
- [ ] Bagging cannot be disabled through challenger controls.
- [ ] Bagging is not skipped merely for the old challenger runtime threshold.
- [ ] Primary Bagging failure does not silently fall back to naive.
- [ ] `ELKAN_NOTO_LOGISTIC` is explicitly `CHALLENGER_1`.
- [ ] Elkan uses Logistic Regression base estimator.
- [ ] Elkan runs by default.
- [ ] Elkan can be explicitly disabled/skipped as challenger without changing the primary.
- [ ] `NAIVE_PU_LABEL_BASELINE` is explicitly `DIAGNOSTIC_CONTROL`.
- [ ] Naive treats U as 0 only for diagnostic purposes.
- [ ] Naive is permanently ineligible for official selection.
- [ ] Evaluation contract version is bumped to 2.
- [ ] Selection policy is explicitly role-governed.
- [ ] Valid Bagging primary remains selected even if Challenger 1 slightly outperforms it.
- [ ] Challenger outperformance is surfaced rather than hidden.
- [ ] Old Elkan-specific tie preference is removed.
- [ ] New successful artifacts persist Bagging as selected estimator.
- [ ] Existing historical model runs/artifacts are not rewritten.
- [ ] Feature contract is unchanged.
- [ ] P/U semantics are unchanged.
- [ ] No PII/behavioral leakage introduced.
- [ ] No demographic scoring/propensity/Audience Explorer added.
- [ ] Same-seed reproducibility passes.
- [ ] Documentation and Phase 4 handoff reflect new roles.

---

# 23. FINAL IMPLEMENTATION REPORT

When finished, report:

1. Starting SHA.
2. Final HEAD/worktree status.
3. Exact files changed.
4. Test results.
5. Data reconciliation result.
6. Evaluation contract version.
7. Model role policy version.
8. Full-data `analysis_run_id`.
9. New `model_run_id`.
10. PRIMARY Bagging metrics.
11. CHALLENGER_1 Elkan metrics.
12. DIAGNOSTIC_CONTROL naive metrics.
13. Challenger-vs-primary deltas.
14. Selected candidate.
15. Selection policy.
16. Artifact path, size, SHA-256.
17. Artifact reload verification.
18. Same-seed reproducibility evidence.
19. Confirm feature contract unchanged.
20. Confirm no later-phase functionality was introduced.
21. Final Go/No-Go recommendation for continuing to Phase 4.

Do not begin Phase 4 as part of this update.
