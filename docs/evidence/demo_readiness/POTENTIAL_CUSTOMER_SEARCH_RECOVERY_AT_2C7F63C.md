# Potential-Customer Search Recovery Evidence

Baseline: `2c7f63ce7cf85ddcd1da7cdc3104f417e907d81d`

## Implemented recovery contracts

- Schema version 21 adds immutable search attempts, append-only progress events,
  calibrated scores, verification attestations, exact preflight caching, targeting
  catalogs, feedback batches, and retraining decisions. Version 21 also adds a
  normalized, indexed product catalog keyed by the targeting-catalog version.
- Search creation persists the search, attempt, runtime, and initial progress before
  orchestration. Multiple durable submissions remain supported; expensive
  intelligence resolution is serialized behind one heavy-work slot.
- Progress uses persisted stages, processed/total units, 15-second-or-faster
  heartbeats, and historical p50-p90 ETA ranges. It does not advance from elapsed
  wall time alone.
- Failed, blocked, and stale-processing attempts have structured, allowlisted issue
  guidance. Retry uses the same visible search ID, creates an immutable next
  attempt, requires an idempotency key, and prevents concurrent active attempts.
- The UI exposes calibrated purchase-propensity buckets, exact preflight, progress,
  retry, run-again, polling recovery, and governed feedback upload. Completed results
  also provide server-generated CSV and JSON templates plus a visible field and
  validation guide, so users do not need to infer the accepted feedback schema.
- Targeting options use a compact checksum-keyed catalog. Successful authoritative
  imports refresh that catalog after commit, and startup safely retries a missed
  refresh. Product rendering reads the 36-row normalized catalog before using the
  indexed legacy lookup for historical rows. Results history uses bulk projections
  instead of per-run query expansion.

## Canonical calibration

The canonical database was migrated from schema 19 through schema 21. Scoring run 6 was
calibrated in the repository's locked Python environment with scikit-learn 1.7.2.

| Field | Value |
|---|---:|
| Promoted calibration artifact | 2 |
| Contract / method | 1 / SIGMOID |
| Calibrated people | 5,000,000 |
| Probability minimum / maximum | 0.065177887 / 0.078555994 |
| Brier score | 0.056369909 |
| Log loss | 0.227049857 |
| Expected calibration error | 0.006297550 |
| ROC-AUC | 0.544008969 |
| Average precision | 0.068868320 |
| Top-decile lift | 1.205366498 |
| Deep verification | VERIFIED, 5,000,000 rows |

An initial publication made with system Python/scikit-learn 1.7.1 was retained as
immutable artifact 1 and marked `STALE`. Artifact 2 was generated with the locked
1.7.2 runtime and is the only `PROMOTED` artifact.

The current calibrated distribution contains no probability at or above 0.50.
Therefore all five approved selection buckets (`0.50` through `0.90`) contain zero
members. Historical raw scores were not rewritten.

## Exact 20-scenario preflight

The exact demographic definitions were evaluated in one five-million-row pass and
cached by canonical criteria and current lineage. No criteria were widened and no
scenario was substituted.

| # | Scenario | Demographic pool | Bucket | Exact | Demo-ready |
|---:|---|---:|---:|---:|---|
| 1 | Working-Age Mainstream | 1,389,349 | 0 | 0 | No |
| 2 | CA + TX Younger Professionals | 168,533 | 0 | 0 | No |
| 3 | NY/NJ/FL Mature Middle Income | 258,616 | 0 | 0 | No |
| 4 | Midwest Value Market | 182,172 | 0 | 0 | No |
| 5 | Western Growth Markets | 167,301 | 0 | 0 | No |
| 6 | East Coast Affluent Professionals | 74,514 | 0 | 0 | No |
| 7 | Southern Family-Value Market | 265,247 | 0 | 0 | No |
| 8 | Married Family Households | 164,862 | 0 | 0 | No |
| 9 | Educated Full-Time Professionals | 148,110 | 0 | 0 | No |
| 10 | Older Retired Middle-Income | 460,423 | 0 | 0 | No |
| 11 | Urban Young Professionals | 105,496 | 0 | 0 | No |
| 12 | Established Inner-Suburban Families | 129,595 | 0 | 0 | No |
| 13 | Self-Employed / Gig Professionals | 159,164 | 0 | 0 | No |
| 14 | Private-Sector Urban/Suburban Workforce | 840,022 | 0 | 0 | No |
| 15 | Women - Four Largest Markets | 202,805 | 0 | 0 | No |
| 16 | Men - Four Largest Markets | 133,497 | 0 | 0 | No |
| 17 | Higher-Education / Higher-Income | 156,188 | 0 | 0 | No |
| 18 | Young Value Seekers | 948,268 | 0 | 0 | No |
| 19 | Mature Suburban Households | 212,846 | 0 | 0 | No |
| 20 | National High-Confidence Match | 2,114,560 | 0 | 0 | No |

Qualified scenarios: **0 of 20**. Per the approved rule, no real searches were
submitted because none had an exact current count of at least 10,000. The limiting
factor is the calibrated probability distribution, not demographic scarcity.

Machine-readable local evidence is stored at ignored path
`output/demo_preload/recovery_preflight_20.json`.

## Real application and browser verification

The ordinary Uvicorn application was started against `data/campaign_poc.db`.

- The Find Potential Customers page displayed all five calibrated probability
  ranges and loaded the compact targeting catalog.
- A real browser preflight using the recorded common products and Email profile
  displayed: demographic pool 5,000,000; propensity bucket 0; exact result 0; and
  an explicit statement that filters were not widened.
- Results history displayed Retry Search for blocked search 33 and failed search 21.
- Blocked result detail displayed progress, safe cause, resolution steps, and Retry
  Search. Completed searches displayed the separate Run Again action.
- Retry Search was exercised on failed search 21. It preserved the visible search,
  created immutable attempt 3 with a unique browser idempotency key, entered the
  processing state, and then returned the expected structured retryable failure
  because the historical intelligence dependency is still unavailable.
- The completed-result feedback panel and empty-file validation were exercised in
  the real browser. Successful CSV/JSON ingestion and membership rejection remain
  covered by API and service tests so no customer outcome was fabricated in the
  canonical database.
- No non-qualifying search was submitted during browser certification.

Warm canonical response measurements were repeated three times by the read-only
`scripts/validation/benchmark_search_recovery.py` gate. The table reports the
slowest observation, rather than the median:

| Endpoint | Observed | Budget |
|---|---:|---:|
| Targeting options | 0.534 s | < 2 s |
| Results history (20) | 0.441 s | < 2 s |
| Search status/detail | 0.275 s | < 0.5 s |
| Exact-result reuse lookup | 0.051 s | < 0.5 s |
| Immutable snapshot validation | 0.028 s | < 2 s |

The machine-readable benchmark is
`docs/evidence/demo_readiness/POTENTIAL_CUSTOMER_SEARCH_RECOVERY_PERFORMANCE.json`.
Search-creation acknowledgement and new-result materialization were deliberately
not executed against the canonical database: both would create a non-qualifying
search while zero scenarios meet the approved 10,000-customer gate. Their isolated
API and orchestration contracts are covered by the automated matrix.

All 20 cached exact scenario preflights were revalidated sequentially in 11.039
seconds total (about 0.552 seconds per scenario).

Canonical `EXPLAIN QUERY PLAN` verification confirmed that calibrated bucket
counts use covering index `idx_calibrated_bucket`, search history uses
`idx_campaign_search_runs_created`, product summaries use the compact
`targeting_product_catalog` primary key (with indexed legacy fallback), and exact
catalog-version reads use the catalog primary-key index. Result history now resolves
all queued positions through one
windowed bulk query; its regression test forbids the former per-result lookup.
Saved-search history (`/runs`) also bulk-loads runtimes and queue positions, with
regression coverage proving one query for each collection rather than one query
per saved search.

## Verification summary

Final bounded certification after the last implementation changes:

- **76 non-browser recovery tests passed** in 243.98 seconds across calibration,
  feedback, immutable attempts, retry, progress, submission concurrency, business
  search, history, and result detail. Twenty-one browser-marked cases were selected
  separately rather than skipped as a substitute for verification.
- **21 real Playwright browser tests passed** in 259.05 seconds. This includes the
  calibrated form and preflight, progress and retry presentation, a 60-cycle polling
  pause followed by Resume Updates recovery, and governed CSV and JSON feedback
  uploads with browser idempotency headers.
- **45 migration/import/lineage tests passed** in 149.70 seconds across authoritative
  import behavior, Phase 9 and Phase 10 schema compatibility, and Phase 11 feedback
  lineage.
- **74 result-registry and smart-reuse tests passed** in 233.19 seconds, covering
  immutable snapshot publication, exact cache reuse, selection semantics, and the
  associated repository/service regressions.
- The final bounded certification therefore contains **216 distinct passing tests**:
  195 backend/service/API tests plus 21 real-browser tests.
- The permanent-failure case proves a non-retryable issue cannot create another
  attempt. The concurrent result-publication tests pass after making result-root
  initialization safe under simultaneous workers.
- The feedback UI now uses `crypto.randomUUID()` where supported and a
  `crypto.getRandomValues()` fallback where a non-secure browser context does not
  expose `randomUUID`; both CSV and JSON upload paths are browser-certified.
- The read-only canonical performance gate passed every operation it executed. It
  does not mutate search history or claim certification for an operation blocked by
  the scenario-qualification rule.

- 102 focused backend tests passed before browser-only environment skips.
- 50 lifecycle, status-contract, history, detail, and form tests passed after the
  final additive response-contract change.
- Calibration determinism, disjoint grouped splits, exact bucket boundaries,
  idempotent publication, deep attestation, feedback membership, feedback
  idempotency, and conflict rejection are covered.
- The final recovery/lifecycle hardening suite passed 10 tests. It additionally
  proves that future-dated feedback is rejected and that failed deep verification
  cannot leave a calibration candidate or promoted artifact behind.
- An additional 41 API contract tests passed for catalogs, creation, v2 attempts,
  idempotent retry, exact read-only preflight, durable executor handoff, safe
  failures, validation boundaries, history, and every available delivery profile.
- Fifteen focused calibration/feedback tests passed, including JSON and CSV
  feedback upload followed by API retrieval, exact automatic-learning thresholds,
  challenger metric non-regression gates, non-finite metric rejection, and startup
  recovery of queued or interrupted challenger decisions.
- Nine lifecycle/concurrency tests passed, including eight simultaneous retry
  requests with one idempotency key producing exactly one immutable next attempt,
  startup-submit races, concurrent independent searches, shared intelligence, and
  single-snapshot publication under a result-cache race.
- Eleven lifecycle/history tests passed after the queue projection optimization,
  including FIFO positions, terminal-run exclusion, and the no-N+1 assertion.
- Four focused saved-search/result-history API tests passed after bulk runtime and
  queue projection was extended to both history endpoints.
- A real 10.5-second compatibility wait test passed and observed a persisted
  heartbeat during the wait, proving long heavy stages no longer remain silently
  fixed at 3 percent.
- A prior 211-case focused sweep produced 190 passes, with only two stale
  schema-version expectations failing; both were updated to version 21 and the
  affected 32-test follow-up passed. The final bounded certification subsequently
  launched Playwright with the required local browser permissions and all 21
  selected browser cases passed.
- Focused Ruff checks, Python bytecode compilation, JavaScript syntax checks, and
  `git diff --check` completed successfully for the changed recovery surface.
- System-browser checks verified the real UI against the canonical database.
- The broad 891-test sweep was intentionally stopped earlier because it projected
  an unbounded runtime; focused coverage and real-browser verification were used
  instead. Repository-wide Ruff also contains unrelated pre-existing lint debt;
  modified recovery modules pass focused lint.

## Honest release limitation

The recovery and orchestration defects are addressed, but the current model is not
strong enough to populate any approved 50%-plus calibrated probability bucket.
Creating 20 searches with 10,000 customers each would require either validated new
outcome feedback and a better promoted challenger or explicit business approval for
a separately versioned lower-probability selection contract. The implementation
does not fabricate counts, duplicate people, widen filters, or silently change
scenario semantics.
