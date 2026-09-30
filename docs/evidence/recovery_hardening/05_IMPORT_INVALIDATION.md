# Step 05 — Authoritative import invalidation and currentness

Date: 2026-09-29
Starting commit: `f437efd3be9e6d4945b0ee12bff91ccce2697088`
Disposition: **GO**

## Defects reproduced

- An existing targeting catalog was returned without restoring its `is_current`
  flag when the authoritative checksums returned to a previously seen version.
- Exact preflight selected any reusable READY generation and any promoted
  calibration without proving current source identity or a current deep
  attestation. A prior `CURRENT` cache row could consequently outlive source
  replacement.
- Post-import maintenance rebuilt only the targeting catalog. It did not stale
  calibrations, preflight cache entries, or result snapshots.
- Result history and download eligibility checked only demographics. Customer or
  campaign-sales replacement could leave old result membership reporting
  `CURRENT`.

## Authoritative dependency matrix

| Derived artifact | customers | campaign_sales | demographics | Reason |
|---|---:|---:|---:|---|
| targeting option catalog identity | yes | yes | yes | The persisted catalog contract is versioned by all three authoritative checksums; product/campaign choices come from campaign sales and targeting facets come from demographics. |
| historical analysis/cohort | yes | yes | no | Customer attributes and attributed campaign outcomes define the historical cohort. |
| trained model | yes | yes | no | Training consumes the historical cohort and its outcome definition. |
| raw scoring generation | yes | yes | yes | Scoring inherits model/history lineage and scores the demographic prospect universe. |
| deep verification attestation | yes | yes | yes | The attestation binds the complete generation, model, scoring, rank, analytics, and latest import identities. |
| calibration artifact | yes | yes | yes | Calibration is owned by one exact scoring lineage; historical outcome or prospect-universe replacement invalidates that lineage. |
| exact preflight cache | yes | yes | yes | Counts combine the calibrated scoring population with current demographic predicates and current catalog choices. |
| immutable result snapshot currentness | yes | yes | yes | Membership is selected from the exact generation and therefore becomes stale when any bound source is replaced. |
| future export eligibility | yes | yes | yes | Export requires current membership lineage; demographics additionally supplies current contact and consent attributes at stream time. Historical export audit rows are retained. |

## Implemented contract

- `reconcile_source_currentness()` is an idempotent repair boundary invoked after
  every successful authoritative import and during application startup.
- The authoritative import remains committed independently. A post-commit
  maintenance failure is logged and never rewrites import truth; startup repeats
  the same reconciliation.
- Reconciliation builds or re-promotes the exact checksum-addressed catalog and
  marks incompatible VERIFIED attestations, PROMOTED calibrations, CURRENT
  preflight cache rows, and CURRENT result snapshots stale. It deletes no
  historical records and does not rewrite immutable identity fields.
- Catalog re-promotion is atomic and guarantees one current checksum version,
  including the case where checksums return to an older catalog version.
- Preflight reports `CURRENT` only for a READY/reusable generation with exact
  latest sources, a current v2 deep attestation, an exact promoted calibration,
  and the requested current catalog. A stale requested catalog is evaluated
  against its immutable choices but returns `STALE`; cached counts are not reused
  and calibrated zero counts are not presented as current.
- Legacy v1 result snapshots retain backward compatibility while their exact
  three-source generation lineage remains current. Calibrated v2 snapshots also
  require their exact promoted calibration and current attestation.
- Download preparation independently rechecks complete lineage and marks a stale
  snapshot before rejecting the download. Demographic identity is rechecked
  again before and during streaming.

## Verification

Commands and outcomes:

- `python -m compileall -q app tests/test_intelligence_attestation_currentness.py`
  — passed.
- `python -m pytest tests/test_intelligence_attestation_currentness.py -q`
  — **13 passed**.
- `python -m pytest tests/test_intelligence_attestation_currentness.py tests/test_phase11_business_search_form.py -q -k "authoritative_replacement or catalog_checksum or exact_preflight_api"`
  — **5 passed, 68 deselected**.
- `python -m pytest tests/test_phase11_results_history_detail.py -q -k "not renders and not pauses and not uploads and not secure_entropy and not responsive"`
  — **5 passed, 8 deselected**. The deselected cases are Playwright UI cases.
- `python -m pytest tests/test_phase11_omnichannel_export_engine.py -q`
  — **18 passed**.
- `python -m pytest tests/test_data_import.py -q`
  — **30 passed**, including the simulated post-commit maintenance failure.
- `git diff --check` — passed; only pre-existing line-ending notices were emitted.

The new matrix explicitly covers customers, campaign sales, and demographics.
For each replacement it proves: a preflight cache starts CURRENT; replacement
makes the same request STALE with no current calibrated count; the old
attestation is rejected; calibration/cache/snapshot status becomes STALE; and
download is refused. A separate regression proves that a previously seen
catalog checksum is re-promoted as the sole current catalog.
Reconciliation is also proven idempotent, and a simulated maintenance exception
proves that the already-committed authoritative import remains `COMPLETED` for
deterministic startup repair.

## Environmental note

An initial broad collection also selected browser tests imported by the chosen
modules. Those cases could not start because the active Python environment has
no `playwright` package. This is not a Step 05 functional failure and no browser
certification is required by this prompt. The non-browser tests from those
modules were rerun as recorded above.

## Remaining risk

Preflight cache-key exactness and materialization parity are intentionally owned
by Prompt 06. Step 05 guarantees stale lineage cannot self-report current; it
does not claim Prompt 06's broader cache-identity certification.
