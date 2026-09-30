# Prompt 12 — Feedback recalibration and learning boundary

## Execution baseline

- Starting SHA: `f437efd3be9e6d4945b0ee12bff91ccce2697088`.
- The working tree already contained the uncommitted outputs of recovery-hardening
  Prompts 01–11. Those changes were preserved. Prompt 12 was implemented on top
  of that tree and was not staged, committed, or pushed.
- Audit date: 2026-09-30.

## Defects reproduced

1. The automatic feedback worker was described publicly and internally as model
   retraining, although it only fitted a new calibration transform over existing
   immutable raw propensity scores.
2. Drift used a feedback-selected score distribution as one population and the
   full scored universe as the reference. Those populations did not share a
   selection basis, so the resulting PSI was not a defensible drift trigger.
3. Every small accepted feedback batch created another `WAITING_FOR_DATA`
   decision row, producing unbounded noisy state instead of one bounded pending
   state with immutable batch audit records.
4. Candidate metric validation did not reject every non-finite governed metric.
5. Worker claim and terminal writes were not fully status-fenced.
6. Feedback accepted while recalibration was active was not bound to a fixed
   batch cutoff, so the worker's input could depend on timing.
7. The repository did not document the boundary between score recalibration and
   true feedback-driven model retraining.

## Root cause

The feedback feature evolved around legacy persistence names
(`feedback_retraining_decisions`) before the statistical operation was defined
precisely. The worker never created a `model_run`, never refitted the feature
model, and reused existing raw scores, but the terminology implied otherwise.
Likewise, the original PSI reused readily available distributions rather than
recording a reproducible, like-for-like population identity.

## Implemented contract

### Truthful semantics

- The runtime worker is `FeedbackRecalibrationWorker`; the old class and
  configuration names remain aliases for source compatibility.
- New API response fields are `recalibration_status` and
  `recalibration_reason`. Deprecated `retraining_*` response aliases remain so
  existing clients do not break.
- Stored legacy table/primary-key names remain unchanged because renaming them
  would be destructive.
- UI, README, logs, thread names, safe errors, and current documentation say
  recalibration. They explicitly state that the operation does not retrain the
  prediction model.
- Recalibration comparison metadata records `model_created: false`,
  `raw_scores_reused: true`, the existing `model_run_id`, and the exact feedback
  batch cutoff.

### Reproducible like-for-like PSI

Each accepted feedback batch records `selection_basis_sha256`, a deterministic
hash of the exact scoring generation, calibration artifact, selection contract,
probability bucket or legacy match strength, selection mode/count, targeting
criteria, and filter branches.

PSI is calculated only when both populations:

- use the same scoring run and calibration artifact;
- have the identical selection-basis hash;
- fall on opposite sides of the latest promoted decision's recorded feedback
  batch cutoff; and
- are nonempty finite distributions over the same ten score bins.

If no comparable population exists, PSI is persisted as unavailable and cannot
manufacture a trigger. Drift lineage records the reference decision, both batch
cutoffs, selection-basis hash, population counts, bin counts, and a deterministic
distribution SHA-256.

### Adaptive and bounded decision state

- Existing floors remain: at least 1,000 labels, 100 positives, 100 negatives,
  and two distinct completed searches.
- After a terminal evaluation, new information requires either at least 10%
  more labels or comparable PSI of at least `0.20`.
- Accepted feedback batches and outcomes remain immutable audit records.
- At most one waiting decision exists per scoring run. New small batches update
  that bounded state instead of appending unlimited waiting rows.
- Migration 30 deterministically retains the newest legacy waiting row and
  closes older duplicates before creating the partial unique index.
- If feedback arrives during active recalibration, the active decision retains
  its fixed batch cutoff. Later feedback accumulates in one waiting successor,
  which is reevaluated after the active decision becomes terminal.

### Challenger governance and worker safety

- Startup changes interrupted `TRAINING` decisions back to `QUEUED` and resumes
  them through the single-slot executor.
- Claim is atomic (`QUEUED` to `TRAINING`) and checks affected-row count.
- Terminal and failure writes require the row still to be `TRAINING`.
- The worker reads accepted feedback only through the decision's persisted batch
  cutoff. Legacy active rows receive a bounded cutoff before processing.
- Recalibration uses the Prompt 11 three-way isolated model lineage. It refuses
  to run if governed model-training group lineage is absent.
- Promotion requires finite Brier score, log loss, expected calibration error,
  ROC-AUC, average precision, and top-decile lift. Brier score must improve;
  ROC-AUC and average precision may regress by no more than `0.01`; lift may not
  regress. Failed gates retain the incumbent.

## Schema and compatibility

- Schema version advanced from 29 to 30.
- `campaign_feedback_batches.selection_basis_sha256` was added as nullable for
  historical compatibility and is required by new ingestion behavior.
- `feedback_retraining_decisions` gained:
  - `decision_kind` (`RECALIBRATION`);
  - `latest_feedback_batch_id`;
  - `reference_decision_id`;
  - validated `drift_lineage_json`.
- A partial unique index enforces one `WAITING_FOR_DATA` decision per scoring
  run.
- Historical feedback, decisions, raw propensity scores, result snapshots, and
  model runs are not rewritten.

## True-model-learning boundary

True model retraining is intentionally not implemented by this prompt. The
future contract is documented in `docs/FEEDBACK_LEARNING_BOUNDARY.md`. A true
implementation must create a new governed `model_run`, apply frozen feature and
leakage contracts, compare challenger and incumbent on held-out data, rescore
the current demographic universe, publish a new scoring generation, pass
currentness/integrity gates, and promote atomically. Fitting a calibration over
old raw scores must never be relabeled as model retraining or reinforcement
learning.

## Verification

Focused feedback, PSI, worker, migration, and calibration-governance suite:

```text
.venv\Scripts\python.exe -m pytest -q \
  tests/test_search_recovery_calibration_feedback.py \
  tests/test_calibration_isolation_governance.py
```

Final result: `30 passed in 46.41s`.

Schema/migration regression suite:

```text
.venv\Scripts\python.exe -m pytest -q \
  tests/test_database_schema.py tests/test_phase3_schema.py \
  tests/test_phase10_schema_registry_repository.py \
  tests/test_phase11_attempt_execution_fencing.py \
  tests/test_phase11_future_feedback_lineage.py tests/test_phase9_schema.py
```

Result: `53 passed in 141.78s`.

Real browser feedback-upload contract:

```text
.venv\Scripts\python.exe -m pytest -q \
  tests/test_phase11_results_history_detail.py::test_result_detail_uploads_csv_and_json_feedback_with_governed_headers
```

The initial sandbox launch was denied by the operating-system browser-process
boundary. The final approved real-browser rerun passed: `1 passed in 27.61s`.

Static checks:

```text
ruff check <Prompt 12 changed Python files>
.venv\Scripts\python.exe -m compileall -q <Prompt 12 changed Python files>
```

Result: Ruff reported `All checks passed!`; compilation completed successfully.

The tests cover deterministic PSI, exact population identity and persisted
reference lineage, unavailable-PSI behavior, threshold boundaries, bounded
waiting state, active-decision batch fencing, legacy duplicate migration,
startup recovery, promotion/non-regression, rejection of every non-finite
metric, API compatibility, and truthful UI terminology.

## Acceptance decision and remaining risk

**GO for Prompt 12.** The automatic behavior is now truthfully named,
reproducibly bounded, concurrency-fenced, and statistically guarded. It fails
closed when comparable PSI or governed split lineage is unavailable.

The current canonical dataset remains unable to produce a new governed
calibration because Prompt 11 proved that all 96 campaigns form one connected
campaign group, while safe train/calibration/evaluation isolation requires at
least three independent groups with both classes. This is an explicit data and
policy limitation, not a reason to weaken the statistical boundary. Therefore
Prompt 12 is implementation-GO, but canonical recalibration promotion remains
unavailable until independently groupable data or an approved prospective
evaluation design exists.

Recommended next prompt:
`13_ZERO_CUSTOMER_ROOT_CAUSE_AND_SELECTION_POLICY_DECISION_GATE.md`.
