# 14B-07 — immutable membership, export, feedback, and lineage

Date: 2026-10-08. Starting HEAD: `336875c30fc32b00323d916ecc45b232016168a1`. Candidate: `UNCOMMITTED`. The checkout already contained uncommitted 14B-00 through 14B-06 work; it was preserved. Stage 08 was not started. No canonical database was migrated, no five-million-row scoring was run, and no campaign was sent.

## Implemented contract

- Membership 3 remains a separate full-precision, no-contact-data snapshot. Validation now checks winning product against the recorded generation, exact selection identity, file hash and count, the manifest, and path/symlink safety. Unknown membership versions fail closed; v1/v2 fields and aliases remain unchanged. No probability is manufactured in v3.
- Publication is staged, checksum-verified, owner/attempt-fenced, and atomically moved before the registry transaction. A failed pre-registry publication cannot create a completed downloadable run. Startup reconciliation removes only old, unregistered generated directories with known file names; registered history is retained.
- Schema 33 adds a separate `buyer_similarity_export_events` aggregate-only audit table and versioned feedback identity columns. The v32 tests still exercise v32 explicitly with their original assertions; a new test certifies v32-to-v33 migration and unchanged legacy export table SQL.
- V3 has version-2 analytical and contact-only omnichannel profiles. Analytical CSVs contain `buyer_similarity_score`, tier, winning product, method, coverage, and generation; contact-only CSVs intentionally omit score fields. Neither places similarity in legacy propensity/rank columns. Historical v3 form inputs naming a v1 channel profile resolve to an advertised v2 analytical profile; the saved run records the resolved profile. V1/v2 headers and channel mapping remain frozen.
- The v3 exporter validates current similarity/source lineage and snapshot integrity, reuses existing channel consent/identifier/hash/formula protections, streams in bounded chunks, and records selected, deliverable, and excluded aggregate counts. Result detail displays the latest completed reconciliation; no contact rows are stored in analytics or evidence. Interrupted streams are marked aborted.
- V3 feedback validates immutable membership, idempotency, duplicates, run/attempt/snapshot, method, profile, generation, and per-person winning product/score. Its scores are stored in distinct similarity columns and never routed to probability recalibration. The response truthfully reports learning unavailable without independently valid probability lineage. Read-only feedback lineage exposes connected-component grouping statistics without person identifiers.

## Verification

| Check | Result |
|---|---|
| `pytest -q tests/test_lookalike_v3_snapshot_export_feedback.py` | 8 passed; includes v32→v33 migration, analytical/contact-only CSV, full precision, source drift, tamper fail-closed, feedback isolation and grouping, interrupted export, and crash-orphan reconciliation. |
| `pytest -q tests/test_lookalike_v3_contract_migration.py tests/test_lookalike_v3_preflight_search.py` | 19 passed; historical v32 assertions unchanged. |
| `pytest -q tests/test_lookalike_v3_snapshot_export_feedback.py tests/test_lookalike_v3_contract_migration.py tests/test_lookalike_v3_preflight_search.py tests/test_phase11_omnichannel_profile_contracts.py tests/test_phase11_omnichannel_export_engine.py tests/test_phase11_future_feedback_lineage.py tests/test_search_recovery_calibration_feedback.py tests/test_feedback_statistical_integrity.py tests/test_phase11_results_history_detail.py --disable-warnings --maxfail=1` | 115 passed, then Playwright Windows named-pipe permission error in sandbox; no assertion failed. |
| Same browser-dependent result-history module plus `tests/test_lookalike_v3_business_ui.py`, rerun with Windows browser permission | 25 passed. |
| `pytest -q tests/test_lookalike_v3_snapshot_export_feedback.py tests/test_search_recovery_calibration_feedback.py` | 31 passed after feedback schema/wiring changes. |
| `pytest -q tests/test_feedback_statistical_integrity.py` | 7 passed, including transitive grouping. |
| Python compile of affected modules and `git diff --check` | Passed. Node CLI syntax check unavailable (`node` not installed); the real-browser suites loaded the edited modules. |

Tests use disposable fixture databases and local generated artifacts. Legacy version assertions were not weakened; test setup now pins those two historical checks to v32, while the separate new test checks v33 migration. No full-repository or remote-CI result is claimed.

## Decision and limitations

`14B_07_BOUNDED_GO`: scoped implementation and affected disposable-data regressions pass. This is not `FULL5M_GO`, predictive validation, demo readiness, or remote-CI certification. Exportable counts are determined when the governed export is prepared; the result page shows the latest completed export reconciliation, or “Not checked yet” before one exists. A current v3 result with no valid probability lineage remains independently exportable, while feedback cannot trigger probability learning. The next pack stage is 14B-08 only when directed by the operator.
