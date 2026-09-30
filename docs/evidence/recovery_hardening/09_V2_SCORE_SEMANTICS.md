# Step 09 — v2 calibrated-probability semantics

## Starting point and working tree

- Starting SHA: `f437efd3be9e6d4945b0ee12bff91ccce2697088`.
- The working tree was already dirty with the sequential, uncommitted outputs of recovery-hardening Steps 01–08. Those changes and their evidence files were preserved.
- No commit or push was performed.

## Defects reproduced

Repository inspection confirmed four semantic defects:

1. The calibrated selection iterator aliased `calibrated_probability` to `propensity_score`.
2. Snapshot publication and validation always used membership contract `1`, whose `propensity_score` field means the legacy raw model score.
3. Results history/detail always presented `Match Strength`, including for calibrated v2 searches, and the score summary was sourced from raw `scoring_runs` aggregates.
4. The frozen omnichannel export reader only understood v1 membership and had no explicit decision for calibrated v2 snapshots.

This allowed one unversioned field name to carry two meanings, which violated the prompt's acceptance gate.

## Implemented contract

### Immutable membership

- v1 remains contract `1` with the unchanged schema:
  `person_id, propensity_score, percentile_bucket, decile, rank_band`.
- v2 is contract `2` with the explicit schema:
  `person_id, calibrated_purchase_probability, probability_bucket, raw_propensity_score, percentile_bucket, decile, rank_band`.
- `raw_propensity_score` is retained in v2 under that explicit name only to support frozen v1 export profiles. It is never used as the v2 selection value.
- v2 rows are ordered by calibrated purchase probability and validated against both their stored bucket boundaries and the run's exact requested bucket.
- Existing v1 files are not rewritten. Compatibility aliases remain frozen to v1 for old callers, while new publication and readers resolve the membership version from the immutable selection contract.

### Cache, manifest, and registry identity

- Result cache identity now includes the resolved membership contract version. The v2 key also continues to bind selection contract, bucket, calibration artifact, and catalog version.
- v2 manifests record manifest contract `2`, membership contract `2`, selection contract `2`, exact propensity bucket, calibration artifact, and the v2 storage schema.
- Registry insertion derives the membership contract from the selection contract rather than using a global constant.
- Schema version `27` permits membership versions `1` and `2`.
- The v26→v27 migration broadens only the verified CHECK definition. It does not rebuild or rewrite the snapshot table, snapshot rows, AUTOINCREMENT identity, indexes, triggers, or child references. The migration advances the SQLite schema cookie and verifies foreign keys and database integrity.

### Results API and UI

- v1 preserves `Match Strength` and `LEGACY_RAW_SCORE` semantics.
- v2 returns and renders:
  - selection label `Purchase Propensity`;
  - exact bucket labels such as `50% to <60%` and `60% to <70%`;
  - semantic marker `CALIBRATED_PURCHASE_PROBABILITY`;
  - calibrated population minimum, mean, and maximum from the promoted `calibrated_propensity_scores` artifact.
- The v2 detail view suppresses legacy Match Strength as the primary targeting label and displays probability values as percentages.
- History/detail response schemas explicitly admit both versioned projections.

### Export decision

- Frozen omnichannel profile columns are unchanged.
- Existing export column `propensity_score` continues to mean the legacy/raw model score for both v1 and v2 source snapshots.
- For v2 membership, the export reader maps only explicit `raw_propensity_score` into that frozen column; calibrated probability is not silently renamed or exposed.
- Responses add `X-Result-Membership-Contract-Version` and `X-Export-Score-Semantics: LEGACY_RAW_PROPENSITY_SCORE`.

## Files changed for Step 09

- `app/database/phase11_schema.py`
- `app/database/schema.py`
- `app/repositories/campaign_result_registry_repository.py`
- `app/schemas/potential_customer_search.py`
- `app/services/phase11_export_service.py`
- `app/services/phase11_result_contracts.py`
- `app/services/phase11_result_snapshot_service.py`
- `app/services/phase11_results_service.py`
- `app/services/phase11_search_orchestration_service.py`
- `frontend/js/business-search-status.js`
- `tests/test_phase11_api_backward_compatibility.py`
- `tests/test_phase11_omnichannel_export_engine.py`
- `tests/test_phase11_results_history_detail.py`
- `tests/test_phase11_search_result_registry.py`
- `tests/test_preflight_materialization_parity.py`

## Verification

Commands and results:

1. `python -m compileall -q app`
   - Passed.
2. Focused Ruff check over all Step 09 Python implementation files.
   - Passed: `All checks passed!`.
3. Focused snapshot/results/export/parity/registry suite with browser tests excluded:
   - `99 passed, 8 deselected`.
4. Broader schema, fencing, feedback-lineage, reuse, API-compatibility, calibration-feedback, and business-form suite:
   - `132 passed, 17 deselected`.
5. Final focused API, export-profile, v2 membership, and calibrated-detail checks:
   - `14 passed`.
6. Project-environment Playwright Results/Detail suite, run outside the restricted subprocess sandbox:
   - `9 passed, 5 deselected`.
7. `git diff --check`
   - Passed; only pre-existing CRLF normalization warnings were reported.

The tests prove:

- a v1 snapshot remains readable with its original schema;
- a v2 snapshot has explicit calibrated and raw fields and no ambiguous `propensity_score` field;
- v1 and v2 cache identities differ;
- v2 manifests and registry rows bind contract `2`;
- 0.50 and 0.60 buckets remain visibly distinct in the Results cards;
- v2 details use promoted calibrated-score aggregates rather than raw scoring-run aggregates;
- v1 export profiles retain their exact headers, row values, counts, and checksum behavior;
- v2-to-frozen-export mapping uses the explicitly named raw score;
- a completed v1 run and its referenced snapshot survive the v26→v27 migration byte-for-field;
- browser cards and detail panels render Purchase Propensity, calibrated ranges, and probability summaries without presenting Match Strength as the v2 primary label.

## Known remaining risks

- The frozen v1 omnichannel export does not expose calibrated probability. A future export contract must add a new explicitly named column and version rather than changing v1.
- Schema migration 27 necessarily uses SQLite's guarded `writable_schema` mechanism because SQLite has no `ALTER CHECK` operation. The migration accepts only the exact v26 constraint, changes one definition once, advances the schema cookie, and is covered by row/reference/integrity tests.
- This step does not commit or push the accumulated prompt-pack changes.

## Gate

**GO for Prompt 09.** Raw propensity and calibrated purchase probability now have an explicit, enforced version boundary from selection through membership, cache, manifest, registry, API, UI, and export consumption.

Recommended next prompt: `10_TARGETING_CATALOG_LIFECYCLE_AND_OPTION_LOAD_CORRECTNESS.md`.
