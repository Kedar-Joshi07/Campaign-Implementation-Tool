You are performing a **small corrective finalization pass on Phase 4 before Phase 5 begins**.

Repository:

`https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Current Phase 4 implementation SHA:

`21bf610b2aabcf2faabee98a82fcb6e637893fb3`

Phase 4 is already implemented and functionally accepted.

**Do not redesign Phase 4.**

**Do not begin Phase 5.**

This task is only to correct a few handoff/API-contract issues discovered during the final Phase 4 audit.

---

# 1. Verify the baseline first

Before changing anything:

```text
git rev-parse HEAD
git status --short
```

Expected HEAD:

`21bf610b2aabcf2faabee98a82fcb6e637893fb3`

If HEAD differs, stop and report the actual SHA unless the newer commit is clearly an explicitly approved continuation.

Do not overwrite unrelated user changes.

Run and record the current baseline:

```text
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
python scripts/validate_data.py --json
```

Also verify the existing full-data Phase 4 evidence remains present:

```text
analysis_run_id = 10
job_id = 3
model_run_id = 7
selected_candidate = BAGGING_PU
artifact_verified = true
```

---

# 2. Scope of this corrective update

Fix only the following required items:

1. Correct the Phase 5 handoff baseline SHA.
2. Fix model-detail feature-contract version/hash reporting.
3. Correct the API tests so they use the real Phase 3 feature-contract structure.
4. Correct worker/executor submission failure HTTP semantics.

Optional only if it can be done safely without disturbing the Phase 3 training engine:

5. Improve candidate-level progress-stage timing.

Do not implement anything else.

---

# 3. FIX 1 — Correct Phase 5 authoritative baseline

Inspect:

`Prompts/phase4_prompt_pack/13_PHASE_5_HANDOFF_CONTRACT.md`

It currently refers to:

`04e61caddedcf7963e824e2ccc425ac241d03842`

as the Phase 5 authoritative baseline.

That SHA is the **Phase 3 baseline**, not the completed Phase 4 implementation.

Replace it with:

`21bf610b2aabcf2faabee98a82fcb6e637893fb3`

The document should clearly say:

```text
Authoritative Phase 4 baseline for Phase 5:
21bf610b2aabcf2faabee98a82fcb6e637893fb3
```

However, because this corrective task itself will create a new commit, once this work is completed the document must ultimately be updated again to the **new final corrective commit SHA**.

Therefore:

* during implementation, use the current Phase 4 SHA as the starting baseline;
* after the corrective commit is created, replace the Phase 5 authoritative baseline with that new final SHA;
* the final report must explicitly state that the new corrective SHA is the authoritative Phase 4 baseline for Phase 5.

Do not leave `04e61...` as the Phase 5 starting point anywhere that could instruct an implementation agent to check out Phase 3 code.

Search relevant documentation for stale Phase 5 baseline references and correct only those that are semantically wrong.

---

# 4. FIX 2 — Correct feature-contract metadata returned by model detail API

Inspect:

`app/services/model_api_service.py`

and:

`app/ml/feature_contract.py`

The real frozen Phase 3 feature contract uses:

```python
FEATURE_CONTRACT_VERSION = "1"
FEATURE_CONTRACT_SHA256 = ...

FEATURE_CONTRACT = {
    "version": "1",
    "ordered_features": [...],
    ...
}
```

The persisted `feature_contract_json` therefore contains:

```json
{
  "version": "1",
  "ordered_features": [...],
  ...
}
```

It does **not** contain:

```text
feature_contract_version
feature_contract_sha256
```

Yet the current Phase 4 API attempts to read:

```python
feature_contract.get("feature_contract_version")
feature_contract.get("feature_contract_sha256")
```

This causes real completed model runs to return `null` version/hash metadata.

Fix this.

---

# 5. Required model-detail feature contract behavior

For:

`GET /api/models/{model_run_id}`

the `feature_contract` section should return:

```json
{
  "feature_contract_version": "1",
  "feature_contract_sha256": "<64-character real contract SHA>",
  "ordered_features": [
    "age",
    "gender",
    "state",
    "individual_yearly_income",
    "marital_status",
    "education",
    "employment_status",
    "resident_status",
    "resident_type",
    "family_member_count",
    "type_of_employment"
  ]
}
```

Do not hard-code an arbitrary test checksum.

Use the authoritative frozen feature-contract definition.

Preferred implementation:

```python
feature_contract_version = feature_contract.get("version")
```

For SHA-256, use the authoritative Phase 3 contract checksum:

```python
FEATURE_CONTRACT_SHA256
```

only after validating that the persisted contract represents the supported frozen contract.

A safer pattern is:

1. decode `feature_contract_json`;
2. validate expected version/order/structure;
3. compare/reconstruct canonical contract hash where appropriate;
4. return the authoritative supported hash.

Do not merely return `FEATURE_CONTRACT_SHA256` for arbitrary or malformed historical JSON.

If persisted feature-contract metadata is malformed or incompatible:

* do not crash with traceback;
* return a safe model-detail validation error or an explicit contract-verification state consistent with current API architecture.

---

# 6. Preserve exact 11-feature contract

The feature list must remain exactly:

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

Do not add or remove features.

Do not change:

```text
FEATURE_CONTRACT_VERSION = 1
```

unless a genuine contract change occurs.

This corrective task is **not** a feature-contract version change.

---

# 7. FIX 3 — Correct test fixtures to match real persisted Phase 3 metadata

Inspect:

`tests/test_model_api.py`

Current fixtures create artificial metadata resembling:

```json
{
  "feature_contract_version": "1",
  "feature_contract_sha256": "contract-sha",
  "ordered_features": [...]
}
```

This does not match the real Phase 3 persisted `feature_contract_json`.

Update tests to use the real structure:

```json
{
  "version": "1",
  "ordered_features": [...],
  "numeric_features": [...],
  "categorical_features": [...],
  ...
}
```

Prefer importing/reusing the actual frozen constants:

```python
FEATURE_CONTRACT
FEATURE_CONTRACT_JSON
FEATURE_CONTRACT_SHA256
FEATURE_CONTRACT_VERSION
ORDERED_FEATURES
```

rather than manually duplicating a fake contract.

Add a regression test proving a real Phase 3-compatible model row returns:

```text
feature_contract_version == "1"
feature_contract_sha256 == FEATURE_CONTRACT_SHA256
ordered_features == list(ORDERED_FEATURES)
```

Add a negative test for malformed/incompatible feature-contract metadata.

The test must prove the API is validating the **real persisted shape**, not a fixture designed around the API implementation.

---

# 8. FIX 4 — Correct worker submission failure HTTP semantics

Inspect:

`app/services/model_api_service.py`

The current behavior maps:

```text
ModelJobSubmissionError
```

into:

```text
ModelApiConflictError
```

which results in:

```text
HTTP 409
```

This is incorrect.

A worker/executor submission failure is an internal execution/service failure, not a request conflict.

Keep HTTP `409` for:

```text
another MODEL_TRAINING job already active
selected historical analysis not in usable/completed state
```

But map worker/executor submission failure to a sanitized server-side error.

Preferred:

```text
HTTP 500
```

unless the current API architecture has a clearly established `503` convention for temporary backend execution unavailability.

For minimum change, use `500`.

Public response:

```json
{
  "detail": "Model training could not be completed."
}
```

or the existing sanitized submission failure message.

Do not expose:

* executor exception;
* traceback;
* multiprocessing details;
* DB path;
* SQL.

Add/update API tests proving:

```text
active job conflict → 409
unusable analysis → 409
request validation → 422
worker submission failure → 500
```

---

# 9. Optional FIX 5 — Candidate progress-stage accuracy

This item is optional and must not destabilize the model engine.

Current Phase 4 progress may show:

```text
TRAINING_PRIMARY
```

while `train_pu_candidates()` internally trains:

```text
PRIMARY
CHALLENGER_1
DIAGNOSTIC_CONTROL
```

before later progress events for challenger/diagnostic are emitted.

If this can be corrected cleanly by adding a backward-compatible candidate progress callback inside:

`app/ml/training.py`

then do so.

Desired real sequence:

```text
TRAINING_PRIMARY
    ↓
Bagging training

TRAINING_CHALLENGER
    ↓
Elkan training or skip

TRAINING_DIAGNOSTIC
    ↓
Naive Logistic training
```

Requirements:

* existing CLI behavior unchanged;
* no duplicate training;
* no algorithm redesign;
* no new public model semantics;
* deterministic training unchanged.

If this requires invasive changes, **do not implement it**. Document it as a low-severity Phase 4 UX limitation instead.

---

# 10. Regression requirements

After implementing required fixes, run:

```text
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
python scripts/validate_data.py --json
```

Also run focused tests for:

```text
tests/test_model_api.py
tests/test_model_job_orchestration.py
tests/test_phase3_hardening.py
tests/test_frontend.py
```

All existing Phase 1–4 tests must continue to pass.

---

# 11. Verify the real full-data model detail

Reuse existing completed Phase 4 model:

```text
model_run_id = 7
```

if it still exists and its artifact remains valid.

Call/read equivalent of:

```text
GET /api/models/7
```

Verify:

```text
status = COMPLETED
selected_candidate = BAGGING_PU
model_role_policy_version = 2
evaluation_contract_version = 2
artifact.verified = true
```

and especially:

```text
feature_contract.feature_contract_version = "1"
feature_contract.feature_contract_sha256 = <real FEATURE_CONTRACT_SHA256>
feature_contract.ordered_features = all 11 frozen features
```

No value should be `null` if the persisted model uses the supported frozen contract.

Also verify:

```text
customer_id not exposed
person_id not exposed
validation_scores not exposed
raw SQL not exposed
absolute path not exposed
```

---

# 12. Phase 5 scope boundary must remain untouched

Do NOT implement:

```text
demographic scoring
propensity_scores
score bands
percentiles
/api/models/{id}/score
scoring jobs
Audience Explorer
target selection
campaign creation
audience persistence
export
activation
```

The application must remain Phase 4 after this correction.

---

# 13. Documentation update

Update:

```text
docs/PHASE_4_IMPLEMENTATION_SUMMARY.md
Prompts/phase4_prompt_pack/08_PROGRESS_TRACKER.md
Prompts/phase4_prompt_pack/12_PHASE_4_ACCEPTANCE_CHECKLIST.md
Prompts/phase4_prompt_pack/13_PHASE_5_HANDOFF_CONTRACT.md
```

Add a section such as:

```text
Phase 4 Finalization / Pre-Phase-5 Corrections
```

Document:

* corrected feature-contract API metadata;
* corrected real-contract API tests;
* corrected submission-failure HTTP semantics;
* Phase 5 handoff baseline correction;
* optional progress fix, if implemented;
* regression results.

Do not erase the original Phase 4 full-data evidence.

---

# 14. Commit and final authoritative SHA

After all tests pass and documentation is updated:

create one dedicated commit with a message similar to:

```text
Phase 4 finalization before Phase 5
```

After committing:

```text
git rev-parse HEAD
```

Update the Phase 5 handoff contract so the **new commit SHA** becomes:

```text
Authoritative Phase 4 baseline for Phase 5
```

If updating that SHA requires a final documentation-only commit, that final documentation commit becomes the authoritative baseline instead.

The final Phase 5 baseline must therefore always point to the actual repository HEAD containing all corrective changes.

---

# 15. Final report

Report:

1. Starting SHA:
   `21bf610b2aabcf2faabee98a82fcb6e637893fb3`
2. Final SHA.
3. Files changed.
4. Feature-contract API bug cause.
5. Feature-contract API fix.
6. Real `FEATURE_CONTRACT_VERSION`.
7. Real `FEATURE_CONTRACT_SHA256`.
8. Confirm all 11 features returned.
9. Confirm `model_run_id=7` artifact verification.
10. Worker submission failure old HTTP status.
11. Worker submission failure new HTTP status.
12. Focused test result.
13. Full pytest result.
14. pip check.
15. compileall.
16. data validation counts/status.
17. Confirm no Phase 5 functionality introduced.
18. Final authoritative Phase 4 SHA for Phase 5.
19. Final **Go / No-Go for Phase 5**.

**Stop after this corrective Phase 4 finalization. Do not start Phase 5.**

