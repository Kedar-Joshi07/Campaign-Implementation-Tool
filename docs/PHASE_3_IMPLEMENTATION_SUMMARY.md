# Phase 3 Implementation Summary

## Decision

Phase 3 is complete and is a **Go for Phase 4**. All Critical acceptance items
pass. The result is a deterministic, leakage-safe, positive-unlabeled modeling
foundation with governed SQLite metadata and a checksum-verified local artifact.

This is a synthetic-data proof of concept. Its observed-label ranking metrics are
not claims of real-world conversion performance, true-negative discrimination,
causality, fairness, or calibrated population probability.

## Baseline and preservation

- Exact accepted Phase 2 baseline:
  `52396010f945b0328b84453ce25c587b11ed7fd7`
- Working branch: `main`
- Phase 3 remained additive. Existing direct `sqlite3`, FastAPI, and static
  HTML/CSS/Vanilla JavaScript architecture was preserved.
- Phase 1 and Phase 2 APIs and the Historical Analysis UI remain unchanged.
- Source Git LFS CSV/JSON/GZIP files were not changed by model execution.
- Local SQLite and `artifacts/models/*` remain ignored runtime state.

## Implemented flow

```text
COMPLETED analysis_run_id
        ↓
reconstruct saved Phase 2 filters and reconcile counts
        ↓
deterministic customer-grain train/validation split
        ↓
training-only preprocessing of 11 frozen raw features
        ↓
Elkan–Noto + bounded Bagging PU + diagnostic naive baseline
        ↓
PU-aware evaluation and genuine-PU-only selection
        ↓
RUNNING model_runs row
        ↓
atomic joblib write, reload/rescore, SHA-256
        ↓
COMPLETED model_run_id (or FAILED with local diagnostic and cleanup)
```

Schema version 3 adds only `model_runs` plus two bounded indexes. It contains no
model BLOB, raw matrix, customer list, or propensity-score table. Migration is
ordered, transactional, idempotent, rollback-tested, and preserves populated
Phase 1/2 rows.

## PU and feature semantics

- Label `1` means known positive under the saved Phase 2 conversion definition.
- Label `0` means unlabeled; it is never described as a confirmed negative.
- One reconstructed row represents one distinct historical customer.
- Campaign/sales observations define cohort membership and label only.
- Age is derived from the saved `contact_date_to`, not wall-clock time.
- The exact raw feature order is:

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

The contract version is `1`; SHA-256 is
`a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`.
Customer identifiers, PII, address/ZIP fields, campaign/product attributes,
behavior, response, spend/margin, `pu_label`, `person_id`, ethnicity, religion,
occupation industry, and family income are excluded from X and artifacts.

Numeric validation, median imputation, and scaling are fitted on training rows
only. Categorical null/blank values normalize to `Unknown/Other`; one-hot
encoding ignores unseen categories safely. Default splitting is stratified at
customer grain with seed 42 and validation fraction 0.20.

## Algorithms and evaluation

- Required genuine-PU candidate: `ELKAN_NOTO_LOGISTIC` using
  `pulearn.ElkanotoPuClassifier` plus bounded logistic regression.
- Genuine-PU challenger: `BAGGING_PU`, 10 estimators, one CPU job.
- Diagnostic only: `NAIVE_PU_LABEL_BASELINE`; it cannot win selection.

Evaluation records observed-label ROC-AUC/AP with an explicit disclaimer,
known-positive retrieval at top 5/10/20%, positive and unlabeled distribution
summaries, empirical KS separation, candidate runtime, quality flags, and a
transparent selection reason. Non-finite/negative outputs fail; constant genuine
PU candidates are quality-rejected; all-genuine-candidate failure never falls
back to the naive baseline.

## Full-data evidence

The populated run used completed `analysis_run_id=10`, conversion definition
`ATTRIBUTED_PURCHASE`, and seed 42.

| Measure | Evidence |
|---|---:|
| Matching observations / selected customers | 14,037 / 14,037 |
| Known positive / unlabeled | 626 / 13,411 |
| Training rows | 11,229 (501 positive / 10,728 unlabeled) |
| Validation rows | 2,808 (125 positive / 2,683 unlabeled) |
| Transformed features | 64 |
| Reconstructed frame memory | 8,219,363 bytes |
| Training sparse-matrix storage | 1,527,148 bytes |
| Validation sparse-matrix storage | 381,892 bytes |

Model run 2 supplied the final stage telemetry:

| Stage | Seconds |
|---|---:|
| Reconstruction/reconciliation | 0.509392 |
| Deterministic split | 0.163546 |
| Preprocessing | 0.503757 |
| Candidate training | 0.365268 |
| Evaluation/selection | 0.054028 |
| Persistence/reload/checksum | 0.091396 |
| Governed end-to-end execution | 1.857761 |

No production SLA is claimed. Reconstruction performs SQL reduction before
pandas materialization: Python receives 14,037 customer rows, not 570,000
observations. Trace tests find no demographics query and no N+1 path. Training
does not scan the 5-million-row prospect table, run grid search, or use unbounded
parallelism.

`BAGGING_PU` was selected. Key full-data validation evidence:

| Metric | Bagging PU |
|---|---:|
| Observed-label ROC-AUC (diagnostic) | 0.534944 |
| Observed-label average precision (diagnostic) | 0.055552 |
| Known-positive recall @ 5% / 10% / 20% | 0.096 / 0.160 / 0.232 |
| Known-positive lift @ 5% / 10% / 20% | 1.911830 / 1.598861 / 1.159174 |
| Observed-label KS | 0.086065 |

The only overall quality flag was `OBSERVED_LABEL_METRICS_ONLY`, which preserves
the limitation that unlabeled observations are not ground-truth negatives.

## Persistence and CLI

The CLI is:

```powershell
.\.venv\Scripts\python.exe scripts\train_pu_model.py `
  --analysis-run-id 10 `
  --model-name "Holiday Electronics Lookalike" `
  --json
```

Model run 1 completed with artifact:

```text
artifacts/models/model_run_000001/pu_model.joblib
```

- Size: 10,108 bytes
- SHA-256:
  `04913a2eb766d116b2e73ea9842ecf25914b3360f35e1fee65860351841bf1de`
- Reload/rescore verification: PASS on 128 validation rows at `rtol=1e-12`,
  `atol=1e-12`

The payload contains only artifact/feature-contract identifiers, the 11-feature
order, fitted preprocessor, selected fitted estimator, and selected-candidate
name. Missing/corrupt/unsafe/incompatible artifacts fail clearly. CLI success
returns 0; failure returns 1; `--json` is parseable and excludes absolute paths
and internal traceback detail.

## Same-seed reproducibility

Model runs 1 and 2 used the same completed analysis, seed, validation fraction,
and challenger configuration.

- Reconstructed and split counts: exact match.
- Train membership SHA-256:
  `1fa32707a64de921f384940981b92680aaf40208e1fdae120b1c08f509f807b8`
- Validation membership SHA-256:
  `d5a507cc9b4d5e2170054ce55f447a9dd6bd74ffe6b679877bf9903ba73b64c7`
- Feature-contract SHA-256: exact match.
- Selected candidate: `BAGGING_PU` for both.
- Non-runtime metrics SHA-256:
  `3f2c2de650443d7c96cd0b07f9505d55aa5ff2ff50f3762cf8e4822d3a80b43a`
- Preprocessing metadata, hyperparameters, and library versions: exact match.
- First 128 reloaded score SHA-256:
  `57298cf46af64d8d1d85a3f405176344b39cad88f7536722eb0206817c366c67`
- Maximum absolute score difference: `0.0`.
- Artifact bytes and SHA-256: identical in this environment.

No customer ID values were persisted to produce these hashes.

## Runtime dependencies and licenses

The tested environment recorded Python 3.12.0, NumPy 2.3.3, pandas 2.3.3,
SciPy 1.16.1, scikit-learn 1.7.1, pulearn 0.0.12, and joblib 1.5.2 per completed
model run. scikit-learn is BSD-style, pulearn is BSD 3-Clause, and joblib is BSD
3-Clause. Dependencies remain local/open-source-first; no commercial or hosted
ML runtime was introduced.

## Verification

- Focused Step 2–6 regression before hardening: 52 passed.
- Phase 3 persistence/telemetry focus after hardening: 5 passed.
- Full pre-documentation regression: 215 passed.
- Final Step 7 test, compile, dependency, diff, data, and scope results are
  recorded in `Prompts/phase3_prompt_pack/11_PROGRESS_TRACKER.md` and the Phase 3
  acceptance checklist.
- Populated `validate_data.py --json`: `OK`; 125,000 customers, 570,000 campaign
  observations, 5,000,000 demographics, zero invalid customer references, zero
  PU consistency violations, and all 23 indexes present.

## Known limitations and Phase 4 boundary

- Data and labels are synthetic; no causal, fairness, or production-performance
  claim is made.
- Elkan–Noto 0.0.12 needs a bounded dense training conversion; the hard cap is
  512 MiB and full-data use was 5,749,248 bytes.
- Elkan–Noto corrected scores may exceed 1 and are ranking scores, not calibrated
  probabilities. Bagging/naive probabilities remain within `[0,1]`.
- SQLite, synchronous CLI execution, and local joblib storage are appropriate for
  this single-user POC, not a multi-user production model platform.
- Exact runtimes vary with CPU, cache, storage, and concurrent load.
- No prospect/demographic scoring, propensity table, Audience Explorer,
  campaign workflow/export, customer/person linkage, training API, or active
  Model Training UI exists.

Phase 4 receives `model_run_id`. A usable run must be `COMPLETED`, linked to a
valid completed analysis, feature-contract-compatible, and backed by an existing
checksum-verified artifact. Phase 4 may add orchestration, background job/API
lifecycle, run listing/detail, and the disabled Model Training UI by reusing the
Phase 3 service. It must not silently add prospect scoring or later audience and
campaign features.
