# Prompt 11 — Calibration train/calibrate/test isolation

## Execution baseline

- Starting SHA: `f437efd3be9e6d4945b0ee12bff91ccce2697088`.
- The working tree already contained the uncommitted outputs of recovery-hardening
  Prompts 01–10. Those changes were preserved; this prompt was implemented on top
  of them and was not committed or pushed.
- Audit date: 2026-09-29.

## Leakage audit before the change

### Observation and lineage grain

- Model input grain was one unique customer. `customer_labels` aggregated every
  matching campaign-sales observation for a customer into one PU label.
- The model split used `train_test_split(..., stratify=pu_label)` at customer-row
  grain. It did not use campaign membership.
- Calibration reconstructed the model validation customer rows, then assigned a
  single group with `MIN(observations.campaign_id)`.
- Calibration split those assigned groups into calibration-fit and test halves.

### Canonical customer-to-campaign multiplicity

Read-only queries against `data/campaign_poc.db` found:

- 119,909 distinct customers with campaign observations;
- 96 distinct campaigns;
- 570,000 distinct customer/campaign pairs;
- 108,330 customers (90.34%) associated with more than one campaign;
- a maximum of 23 campaigns for one customer;
- one connected component across all 96 campaigns when campaigns sharing a
  customer are joined.

### Proven leakage defects

1. A campaign could contribute customers to model training and model validation
   because the model split was row-stratified.
2. The same campaign could then contribute customers to calibration fit and
   calibration test because only the validation rows were grouped afterward.
3. `MIN(campaign_id)` discarded every non-minimum campaign association for a
   multi-campaign customer. Two customers sharing a non-minimum campaign could
   be assigned to different groups, so the recorded zero group overlap did not
   prove zero campaign overlap.
4. Model runs persisted counts and a seed, but not the exact grouped partition
   lineage used by calibration.
5. Candidate metrics were evaluated on a calibration holdout, but publication
   did not prove that this holdout was also isolated from model-training campaign
   groups.

## Old versus new methodology

| Concern | Old methodology | New methodology |
|---|---|---|
| Model fit boundary | Stratified customer rows | Campaign-connected groups |
| Multi-campaign customer | Collapsed to `MIN(campaign_id)` during calibration | All campaign memberships form one deterministic connected component |
| Partitions | Model train/validation, then calibration fit/test | Model training, calibration fit, calibration evaluation |
| Overlap proof | Calibration group count only | Three pairwise overlap counts plus exact group-ID lists and hashes |
| Class safety | Both classes in fit/test | Both classes required in all three partitions |
| Evaluation use | Held out from calibrator fit | Held out from model fit and calibrator fit; candidate selection is evaluation-only |
| Insufficient data | Could appear valid after `MIN` collapse | Fails explicitly; never relaxes to row splitting |
| Persistence | Calibration split summary | Model `split_lineage_json` plus calibration v2 lineage and evaluation scope |

## Implemented contract

`CAMPAIGN_CONNECTED_THREE_WAY_V1` constructs the bipartite relationship between
customers and campaigns and merges campaigns that share any customer. The
resulting connected component is the indivisible leakage group. A fixed seed
assigns those groups to:

1. `model_training`;
2. `calibration_fit`;
3. `calibration_evaluation`.

Every partition must contain positive and negative outcomes. Persisted lineage
contains the strategy version, seed, observation grain, boundary definition,
fractions, group/customer/class counts, exact component IDs, component-ID
SHA-256 hashes, multi-campaign statistics, and all pairwise overlap counts.

The model continues to expose a train/validation interface to the existing
training pipeline. Its validation rows are the union of calibration-fit and
calibration-evaluation groups; neither group is used to fit the model. The
calibration service reconstructs and byte-for-byte compares the persisted model
lineage before scoring those rows.

Sigmoid and isotonic candidates are fitted only on `calibration_fit`. Brier
score, log loss, expected calibration error, ROC-AUC, average precision, and
top-decile lift are calculated only on `calibration_evaluation`. Selection uses
held-out Brier score with held-out log loss as the tie-breaker. The lineage
records `evaluation_records_used_for_fit: 0` and
`candidate_selection_partition: calibration_evaluation`.

Promotion now requires a complete v2 lineage: three nonempty pairwise-disjoint
group sets, zero recorded overlap, both classes in calibration fit/evaluation,
the exact strategy version, and evaluation-only selection. A Boolean flag by
itself is not sufficient.

## Schema and compatibility

- Schema version advanced from 28 to 29.
- `model_runs.split_lineage_json` was added as nullable validated JSON. Existing
  model rows remain unchanged and readable.
- `score_calibration_artifacts.calibration_contract_version` now accepts `1`
  and `2`. Existing v1 artifacts remain immutable and readable.
- New governed artifacts are written as calibration contract v2.
- Models without persisted grouped lineage are rejected for new v2 calibration
  rather than being reinterpreted.
- Model detail responses expose the persisted split lineage under governance.

## Verification

Focused isolation/calibration command:

```text
.venv\Scripts\python.exe -m pytest -q \
  tests/test_calibration_isolation_governance.py \
  tests/test_search_recovery_calibration_feedback.py
```

Result: `23 passed in 26.45s`.

Focused preprocessing/schema command (before the final promotion-lineage
tightening, unaffected by that tightening):

```text
.venv\Scripts\python.exe -m pytest -q \
  tests/test_calibration_isolation_governance.py \
  tests/test_search_recovery_calibration_feedback.py \
  tests/test_feature_preprocessing.py \
  tests/test_phase3_schema.py
```

Result: `45 passed in 85.06s`.

Training/cohort/Phase 10 compatibility command:

```text
.venv\Scripts\python.exe -m pytest -q \
  tests/test_training_cohort_service.py \
  tests/test_model_persistence.py \
  tests/test_phase10_model_resolution.py \
  tests/test_phase11_future_feedback_lineage.py
```

Result: `24 passed in 86.28s`.

Schema/migration regression command:

```text
.venv\Scripts\python.exe -m pytest -q \
  tests/test_database_schema.py tests/test_phase3_schema.py \
  tests/test_phase10_schema_registry_repository.py \
  tests/test_phase11_attempt_execution_fencing.py \
  tests/test_phase11_future_feedback_lineage.py tests/test_phase9_schema.py
```

Result: `53 passed in 77.56s`.

Static checks:

```text
ruff check <Prompt 11 changed Python files>
git diff --check
```

Result: Ruff passed. `git diff --check` reported no whitespace error; it emitted
only pre-existing CRLF normalization warnings for unrelated accumulated files.

Tests prove fixed-seed determinism, pairwise zero overlap, class presence,
deterministic multi-campaign union, held-out candidate metrics, unsafe promotion
rejection, schema v29, and transparent failure for impossible splits.

## Canonical acceptance decision

**NO-GO for promoting a new calibration from the current canonical dataset.**

All 96 campaigns form one campaign-connected group, while the governed contract
requires at least three independent groups with both classes. Therefore no
truthful three-way campaign-isolated split exists for the current data model.
The system now reports that insufficiency instead of silently weakening the
boundary. No calibration was promoted and no canonical model, score, or source
row was modified.

Resolution requires a governed data/policy decision, such as an explicitly
versioned independent grouping key that is not transitively connected by the
same customers, or a prospective evaluation design with campaigns held out at
data-collection time. The code must not choose either policy implicitly.
