# Phase 6 Handoff Contract — Audience Explorer

Phase 6 consumes a COMPLETED Phase 5 `scoring_run_id` where scored count equals prospect snapshot and associated model remains completed with recorded Bagging/feature/artifact provenance.

Validated Phase 5 reference (2026-08-24 rerun): `model_run_id=7`, `job_id=16`, `scoring_run_id=5`, scored count = snapshot count = 5,000,000.

Phase 6 may then separately freeze and implement paginated scored-prospect retrieval, search/filter, ranking, score thresholds, percentiles/bands, aggregate audience profiling, top-N selection and Audience Explorer UI.

Score source is `propensity_scores JOIN scoring_runs JOIN demographics`, always restricted to `scoring_runs.status='COMPLETED'`.

`person_id` remains prospect identity and must never be linked to customer_id.

Phase 6 must separately freeze which demographic/PII fields may be displayed/exported; Phase 5 intentionally exposed none.

Continue describing score as model-specific relative affinity, not calibrated purchase probability.

Use Phase 5 rank index `(scoring_run_id, propensity_score DESC, person_id ASC)` and measure query plans before adding indexes.

After Phase 5 acceptance, final Phase 5 repository HEAD becomes the authoritative Phase 6 baseline.
