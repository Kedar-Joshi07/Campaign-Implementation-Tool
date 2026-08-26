# Phase 6 Handoff Contract — Audience Explorer

Phase 6 may consume a Phase 5 scoring run only when all canonical usability rules are satisfied against the current demographics source.

Canonical Phase 5 finalization reference (pre-Phase-6):
- `model_run_id=6`
- `job_id=18`
- `scoring_run_id=7`
- `demographic_import_id=5`
- `demographic_source_checksum=7d57a02add836f448ed2d937e60bb6c0d38402c3c82e6f219b54e904e0e0c2db`
- scored count = snapshot count = `5,000,000`
- feature contract version/hash = `1` / `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`
- artifact SHA = `a6f50f3391997bec539f1371306a81d314079020686b588a28b3c44815a1a210`

Canonical usability rule for Phase 6:
- `status = COMPLETED`;
- score row count reconciles to scored count and demographic snapshot;
- model/artifact/feature governance remains valid;
- demographic import provenance is valid;
- `demographic_source_checksum` matches the current source;
- demographic count and min/max `person_id` envelope match the current source.

Any stale completed run (source mismatch) is audit history only and must be rejected for Phase 6 audience actions.

Phase 6 must reject any score set whose provenance does not match loaded demographics:
- reject when `demographic_import_id` differs,
- reject when `demographic_source_checksum` differs,
- reject when `demographic_snapshot_count` differs,
- reject when demographic min/max `person_id` envelope differs.

Historical scoring evidence remains preserved (`scoring_run_id=5` on `model_run_id=7`) and is not canonical for Phase 6.

Final correction validation evidence is recorded at `docs/evidence/phase5_final_corrections_validation.json`.

Phase 6 may then separately freeze and implement paginated scored-prospect retrieval, search/filter, ranking, score thresholds, percentiles/bands, aggregate audience profiling, top-N selection, and Audience Explorer UI.

Score source is `propensity_scores JOIN scoring_runs JOIN demographics`, always restricted to `scoring_runs.status='COMPLETED'`.

`person_id` remains prospect identity and must never be linked to customer_id.

Phase 6 must separately freeze which demographic/PII fields may be displayed/exported; Phase 5 intentionally exposed none.

Continue describing score as model-specific relative affinity, not calibrated purchase probability.

Use Phase 5 rank index `(scoring_run_id, propensity_score DESC, person_id ASC)` and measure query plans before adding indexes.

After Phase 5 finalization commit, final Phase 5 repository HEAD is the authoritative Phase 6 baseline.
