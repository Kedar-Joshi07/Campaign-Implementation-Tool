# Step 6 — Model Persistence, Reload Verification, and Training CLI

## Objective

Create the governed Phase 3 execution surface and persist a reusable model artifact.

## Model-run lifecycle

Implement:

```text
RUNNING
  ↓
reconstruct/reconcile
  ↓
split/preprocess/train/evaluate
  ↓
persist artifact
  ↓
reload validation
  ↓
COMPLETED
```

On any unrecoverable exception:

```text
RUNNING → FAILED
```

Persist internal diagnostic detail locally.

## Persistence

SQLite `model_runs` should store:

- source analysis ID;
- status;
- model name;
- selected algorithm;
- seed/split;
- counts;
- feature-contract JSON/fingerprint;
- preprocessing metadata;
- hyperparameters;
- evaluation metrics;
- exact library versions;
- relative artifact path;
- SHA-256;
- internal error field.

Do not store the serialized model as a SQLite BLOB.

## Artifact payload

Recommended joblib payload:

```python
{
    "artifact_version": "...",
    "feature_contract_version": "...",
    "feature_contract_sha256": "...",
    "raw_feature_order": [...],
    "preprocessor": fitted_preprocessor,
    "estimator": fitted_selected_pu_estimator,
    "selected_candidate": "...",
}
```

Do not include:

- customer IDs;
- raw train/validation matrices;
- source PII;
- campaign observations.

## Atomic write

Write to a temporary artifact path first, then rename/move after successful serialization.

If model-run completion fails, do not leave a file that appears valid without matching metadata.

## Reload verification

Immediately after persistence:

1. load the artifact from disk;
2. transform a bounded in-memory validation sample using the loaded preprocessor;
3. produce scores using the loaded estimator;
4. compare with pre-persistence scores within strict tolerance;
5. calculate SHA-256;
6. persist relative path and checksum.

## CLI

Create:

`scripts/train_pu_model.py`

Example:

```powershell
.\.venv\Scripts\python.exe scripts\train_pu_model.py `
  --analysis-run-id 10 `
  --model-name "Holiday Electronics Lookalike" `
  --json
```

Expected terminal summary:

```text
Model run: 1
Analysis run: 10
Status: COMPLETED
Selected candidate: ELKAN_NOTO_LOGISTIC
Customers: ...
Known positives: ...
Unlabeled: ...
Validation lift@10%: ...
Artifact: artifacts/models/model_run_000001/pu_model.joblib
SHA-256: ...
```

JSON mode should be machine-readable and bounded.

## Model inspection CLI

Optionally add:

`scripts/inspect_model_run.py --model-run-id ...`

or a reusable service to load model-run metadata.

Do not create public HTTP training APIs yet unless Phase 4 explicitly requests them.

## Tests

- successful lifecycle;
- failed lifecycle;
- artifact relative path;
- no absolute path in public-style summary;
- SHA matches file bytes;
- reload equivalence;
- missing artifact detected;
- corrupted artifact detected;
- source analysis ID preserved;
- no PII/customer IDs in metadata JSON;
- no raw training matrix persisted;
- CLI success/failure exit code;
- JSON CLI output parses.

## Exit criteria

A completed Phase 2 analysis can produce a persisted, checksummed, reloadable PU model artifact and a governed `model_run_id`.
