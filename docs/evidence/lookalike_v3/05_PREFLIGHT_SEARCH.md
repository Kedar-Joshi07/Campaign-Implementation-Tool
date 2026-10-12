# Stage 14B_05 — independent preflight, search, and exact result reuse

Recorded 2026-10-07 on `main` from trusted HEAD
`336875c30fc32b00323d916ecc45b232016168a1`. Candidate: `UNCOMMITTED`.
Stage 14B_04 was the preceding completed stage. This run did not commit, push,
change canonical inputs, migrate the operator database, score five million
people, run a browser certification, or start Stage 14B_06.

## Implemented

- Explicit v3 submissions and retries now enter the durable Phase 11 coordinator.
  The v3 worker never calls Phase 10 probability, model, or calibration APIs.
  It resolves the exact historical product context, builds missing supported
  buyer profiles, reuses or scores current demographic generations, checks
  attestation/source identity, and completes under the attempt lease token.
  Busy concurrent profile/generation builds rejoin by bounded polling; stale
  Stage 04 leases can be reclaimed. Missing governed imports remain durably
  queued until import provenance is available.
- Progress names the preparation, scoring, verification, selection,
  materialization, and exact-reuse stages. Actual score chunk counts are
  propagated; a heartbeat runs during long operations. The existing ETA
  projector remains stage-history based and says insufficient history when
  there is no reliable estimate. Unsupported attributed-buyer history is a
  non-retryable `PROFILE_NOT_ELIGIBLE` block; transient work failures retain
  safe retry guidance. Zero qualifying customers publish an honest empty
  snapshot rather than fabricate customers.
- One full-precision v3 SQL selection builds both exact counts and immutable
  membership. Demographic conditions are AND within each branch, OR across
  branches, with one eligible person, valid coverage only, per-person maximum
  score and deterministic product tie-break. `.90` and `.80` are cumulative
  minimums, not disjoint probability buckets. TOP_N caps the same descending
  score/person order. The preflight separately reports demographic eligible,
  valid, invalid/unscored, qualifying, and selected counts.
- The v3 preflight and result cache keys include explicit v3 semantics,
  criteria/branch hashes, product/profile set, score generations, source
  identities, catalog version, minimum, selection mode, and cap. Cached
  membership is reopened with full artifact checksum, schema, order, count,
  manifest, and current generation checks. Publication is fenced to the active
  attempt and checks latest import identities inside its database transaction.
  Completion repeats an in-transaction source check. An old catalog token is
  rejected after imports change; stale similarity is reported separately.
- Schema remains version 32. Existing schema-32 installations with the old
  immutable-run trigger receive a conditional, transactional metadata-only
  repair during initialization; historical rows and analytical scores are not
  rewritten. A new additive `/api/health/modes` response and options
  `mode_readiness` distinguish infrastructure, v3 source availability, and
  probability calibration availability without changing legacy `/api/health`.
  Result detail reopens v3 snapshot provenance and exact count; v3 download
  remains disabled until Stage 14B_07 defines its export contract.

## Verification

- Independent A=.96, B=.92, C=.88, D=.73 eligible/E=.97 ineligible tests:
  `.90` selects A/B, `.80` selects A/B/C. Boundary/nextafter, unknown, invalid
  coverage, overlapping OR, all-equal ordering, empty selection, TOP_N, and
  cache-identity dimensions passed.
- One disposable real prepare → profile → score → preflight → search cycle
  produced a ten-person immutable snapshot. Exact preflight count, run count,
  snapshot manifest count, and reopened detail count agreed. Identical search
  reused the same snapshot; a changed minimum produced a separate snapshot.
  A later demographic import invalidated the old catalog token and reported
  stale similarity after refresh. The same cycle verified attempt heartbeat,
  retry idempotency, and rejection of the old fence. No purchase calibration
  existed in this ready-similarity fixture.
- A separate fixture with genuinely eligible governed purchase calibration
  reported similarity `NOT_AVAILABLE`, proving the reverse mode boundary.
- Focused Stage 05 tests: `tests/test_lookalike_v3_preflight_search.py`
  (5 tests) and the additional probability-ready test in
  `tests/test_preflight_materialization_parity.py` passed in targeted runs.
  Existing schema-32 identity, repair, and full-cycle tests: 3 passed in
  101.55s after the repair. Stale-publication-fence full cycle: 1 passed in
  58.75s. Existing v3 contract and health tests: 27 passed in 76.34s before
  the conditional trigger repair; their changed-path cases were retested.
- A serial non-browser/non-performance affected run reached 187 passed,
  27 deselected, 1 failed in 1060.72s. The sole failure was the pre-existing
  literal schema-32 assertion during a temporary schema-33 approach. That
  approach was removed; the assertion and the new repair/full-cycle tests
  passed afterward. A new single aggregate green run was **not** performed,
  so no such result is claimed. `git diff --check` and targeted compilation
  passed before the final evidence write.
- Final Stage 05 plus schema-32 assertion and mode-health command: 7 passed
  in 92.15s. This is the final changed-path green run.

## Decision and limits

**GO for bounded Stage 14B_05 implementation; NO-GO for release/full-scale
certification.** V1/v2 request semantics, raw scores, calibration governance,
and historical result contracts remain in their paths. Currentness is not
model quality. No five-million-row performance or multi-process recovery proof
is claimed here; those are later pack stages. V3 download/export and the
business UI are later stages. The final aggregate affected suite should be
rerun at its later integration gate to replace the transparent targeted-rerun
evidence with one all-green result.
