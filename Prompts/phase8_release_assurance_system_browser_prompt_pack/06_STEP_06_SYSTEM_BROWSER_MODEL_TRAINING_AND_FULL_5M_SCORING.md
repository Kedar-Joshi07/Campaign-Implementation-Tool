# Step 6 — System Browser: Model Training & Full 5M Scoring

This is a critical certification step. Do not initiate training or scoring through backend/service calls.

## Model Training
Use the analysis created in Step 5.

Exercise:
- source analysis selector
- model name
- random seed
- validation fraction
- challenger toggle
- refresh options/runs
- Train Look-alike Model
- recent model list/detail controls

Click Train through the system browser.

Observe UI lifecycle:
QUEUED → RUNNING → COMPLETED

Verify UI output:
source analysis, selected/P/U, train/validation counts, exact feature count, Bagging primary, Elkan challenger, Naive diagnostic, candidate metrics, governed selection and artifact/quality state.

Independent backend assertions:
- exact 11 features
- Feature Contract v1/SHA
- Model Role Policy v2
- Evaluation Contract v2
- BAGGING_PU selected
- artifact SHA

## Full 5M scoring
Using the newly browser-created model, click `Score Prospect Universe` through the system browser.

Observe submission, active job, progress/stage transitions, finalization and completion.

Use state-aware waits. No arbitrary short timeout.

The run must score exactly 5,000,000 current prospects.

After completion independently verify:
- snapshot 5M
- score rows 5M
- distinct IDs 5M
- duplicates 0
- invalid FK 0
- non-finite 0
- out-of-range 0
- correct source/model/artifact/feature provenance
- runtime/chunks/throughput

Run deterministic rescore of at least 256 IDs within frozen tolerance.

Exercise all scoring-related refresh/status/detail controls.

Update control inventory.

Create `docs/evidence/phase8/06_SYSTEM_BROWSER_TRAINING_AND_5M_SCORING_REPORT.md`.

STOP.
