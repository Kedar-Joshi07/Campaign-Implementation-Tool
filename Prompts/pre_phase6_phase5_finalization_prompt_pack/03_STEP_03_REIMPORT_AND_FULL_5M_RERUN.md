# Step 3 — Reimport Corrected 5M Demographics and Full Scoring Rerun

Use the HEAD produced by Step 2. Do not begin Phase 6.

## Pre-run
Run:
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
python scripts/validate_data.py --json

## Reimport
Use the project's existing authoritative import pipeline.
Do not patch SQLite directly.

Import data/usa_demographic_synthetic_5000000_rows.csv.gz.

Verify:
- rows read = 5,000,000
- rows inserted = 5,000,000
- rows rejected = 0
- latest completed demographics import has demographic_import_id and source_checksum

## Database quality
Verify:
- COUNT(*) = 5,000,000
- COUNT(DISTINCT person_id) = 5,000,000
- age <18 = 0
- age >100 = 0
- Minor / not in labor force = 0
- child-only education categories = 0
- individual_yearly_income <0 = 0
- family_member_count <1 = 0

Record min/max age. Do not export PII.

## Historical score handling
Old scoring_run_id=5 belongs to the previous demographic source and must not be the new canonical Phase 6 score set.

Do not silently delete history.
If the existing one-COMPLETED-run-per-model constraint blocks the rerun, make the minimum safe governance change that preserves historical evidence while allowing exactly one current/canonical completed run for Phase 6.

Do not implement Audience Explorer.

## Model
Use a real completed role-policy-v2 BAGGING_PU model. model_run_id=7 is evidence only, never hard-code it.
Verify status, selected candidate, role policy v2, evaluation contract v2, feature contract v1/SHA, and artifact SHA.

## Real API path
POST /api/models/{model_run_id}/score -> 202
Poll GET /api/jobs/{job_id} -> COMPLETED
Capture new scoring_run_id.
Verify GET /api/scoring-runs/{id} and GET /api/models/{model_run_id}/scoring-status.

While active:
- second scoring submit -> 409
- model training submit -> 409

## Exact reconciliation
Require:
- demographic_snapshot_count = 5,000,000
- scored_person_count = 5,000,000
- score rows = 5,000,000
- duplicate person IDs = 0
- invalid demographic FK = 0
- nonfinite = 0
- score <0 = 0
- score >1 = 0
- 0 <= min <= mean <= max <=1

## Provenance
Completed run must record/validate:
demographic_import_id
demographic_source_checksum
demographic_snapshot_count
model_run_id
artifact_sha256
feature_contract_version
feature_contract_sha256

Current demographics must still match the run provenance.

## Deterministic verification
Run verify_scoring_run_sample(scoring_run_id=<new>, sample_size=256).
Expected verified=true and max_abs_diff approximately 0.0.

## Performance
Record:
chunk_size
chunk_count
largest_chunk_rows
largest_transformed_matrix_bytes
runtime
rows_per_second
DB size before/after

Confirm no OFFSET, no whole-5M pandas load, and no accumulated 5M score list.

## Post-run
Run:
python -m pytest -q
python -m pip check
python -m compileall -q app scripts tests
git diff --check
python scripts/validate_data.py --json

Report demographic import/checksum, model/job/scoring IDs, exact 5M counts, score stats, chunk/memory/runtime/throughput, deterministic re-score, conflicts, regression results, and unresolved issues.

STOP.
