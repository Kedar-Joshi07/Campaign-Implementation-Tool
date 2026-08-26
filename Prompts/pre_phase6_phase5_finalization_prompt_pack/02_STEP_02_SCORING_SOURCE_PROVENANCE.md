# Step 2 — Scoring Source Provenance and Completion Hardening

Use the HEAD produced by Step 1. Do not begin Phase 6.

## Objective
Bind each new canonical completed scoring run to the exact demographic source used to produce its scores.

## Provenance source
Use authoritative COMPLETED demographics metadata in data_import_runs.

Resolve and validate:
- demographic_import_id
- demographic_source_checksum
- dataset_name = demographics
- status = COMPLETED
- rows_inserted = current demographics count
- source checksum is populated/valid

If trustworthy provenance cannot be resolved, do not allow a new canonical scoring run.

## Persistence
Prefer to keep schema v5 unchanged unless a schema change is clearly necessary.

Persist source provenance in canonical score_summary_json:
- demographic_import_id
- demographic_source_checksum
- demographic_snapshot_count
- demographic_min_person_id
- demographic_max_person_id
- model_run_id
- selected_candidate
- feature_contract_version
- feature_contract_sha256
- artifact_sha256
- chunk_size
- chunk_count
- score_count
- score_min
- score_mean
- score_max
- total_seconds
- rows_per_second
- age_semantics_note

All JSON must be finite and canonical.

## Capture/recheck
Before first scoring chunk capture import ID/checksum/count/min/max.
Before completion resolve them again.
If any value changed, FAIL the scoring run.

## Completion hardening
ScoringRepository.mark_completed must require a valid non-empty summary payload.
Do not allow an application-layer COMPLETED scoring run without canonical summary metadata.

Add a helper such as validate_completed_scoring_run_provenance() verifying:
- status COMPLETED
- count reconciliation
- model provenance
- artifact provenance
- feature provenance
- demographic import/checksum provenance
- optionally current source still matches

This helper is the safe Phase 6 handoff gate.

## Historical run
Existing scoring_run_id=5 did not record this provenance.
Do not rewrite history to pretend it did.
Treat it as legacy Phase 5 evidence, not the final canonical Phase 6 run.

## API safety
A bounded demographic_source_verified boolean is okay.
Do not expose source filesystem paths, database paths, PII, or raw rows.

## Tests
Cover:
- missing import provenance
- invalid checksum
- count mismatch
- capture before scoring
- checksum/import ID drift during run
- completion missing summary
- canonical completed validation
- legacy run not canonical
- no source path leakage

Run:
python -m pytest -q
python -m compileall -q app scripts tests
python -m pip check
git diff --check

Report changes, provenance design, schema impact, completion hardening, source-drift behavior, legacy handling, tests, and unresolved issues.

STOP.
