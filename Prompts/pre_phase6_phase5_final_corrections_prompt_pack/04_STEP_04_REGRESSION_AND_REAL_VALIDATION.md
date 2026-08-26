# Step 4 — Regression and Real Lifecycle Validation

Use the HEAD produced by Step 3. Do NOT begin Phase 6.

## Objective

Prove the fixes with both full regression and bounded lifecycle simulations. Do not rerun expensive 5M scoring unless needed.

## A. Full regression

Run:

```text
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
python scripts/validate_data.py --json
```

## B. Current canonical evidence

Validate current known evidence (IDs are evidence only; never hard-code):

```text
model_run_id = 6
scoring_run_id = 7
demographic_import_id = 5
```

Verify status COMPLETED, 5M score rows, 5M scored count, current source provenance match=true, and deterministic sample re-score still verifies.

## C. Bounded source-change lifecycle

Use a safe small test DB/copy:

```text
Source A imported
same model scored → Run A current
Source B imported atomically
Run A remains COMPLETED historical
Run A current-source verified=false
same model becomes eligible
Run B submitted/completed
Run B current-source verified=true
```

## D. Failed replacement lifecycle

Prove:

```text
Source A live
Source B replacement forced to fail after multiple staging batches
Source A remains unchanged
Source B import = FAILED
Run A current-source verification remains true
```

## E. Same-model coexistence

Verify multiple COMPLETED runs for the same model can coexist across distinct sources.

## F. Scope

Confirm no Audience Explorer, scored-prospect browser API, score bands/percentiles/deciles, audience selection, campaign builder, export, or activation.

## Evidence artifact

Create a sanitized committed JSON report, e.g.:

```text
docs/evidence/phase5_final_corrections_validation.json
```

Do not include absolute paths, PII, raw person IDs, SQL, or traceback.

Include regression counts, canonical verification, source-change lifecycle, failed rollback proof, same-model coexistence, and scope scan.

## Report

Report full gates, current canonical verification, source-change lifecycle, failed rollback result, historical coexistence, API semantics, evidence artifact path, and unresolved issues.

STOP.
