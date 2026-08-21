# Phase 2 Acceptance Checklist

Use this checklist only after Steps 1–7 are complete. Mark each item `PASS`, `FAIL`, `PARTIAL`, or `NOT TESTED`, and attach concrete evidence.

Any failed Critical item means **No-Go for Phase 3**.

## A. Base and repository integrity

- [x] **PASS** **Critical** The work started from or was explicitly reconciled against `c6c9f41ea257aa33ae196b75cc8f76f8419431e7`.
- [x] **PASS** Baseline Phase 1 test result was recorded before Phase 2 changes.
- [x] **PASS** Unrelated user changes were preserved.
- [x] **PASS** Git LFS datasets, pointers, sizes, and hashes are unchanged.
- [x] **PASS** No generated database, logs, model artifacts, or exports were committed.
- [x] **PASS** `git diff --check` passes.

## B. Frozen architecture and scope

- [x] **PASS** **Critical** Frontend remains HTML/CSS/Vanilla JavaScript.
- [x] **PASS** **Critical** Backend remains FastAPI/Python with direct `sqlite3`.
- [x] **PASS** No unapproved framework/infrastructure dependency was added.
- [x] **PASS** **Critical** No `customer_id` ↔ `person_id` mapping exists.
- [x] **PASS** Historical analysis does not scan or join the demographics table.
- [x] **PASS** **Critical** No PU model training or simulated model exists.
- [x] **PASS** **Critical** No propensity scoring exists.
- [x] **PASS** No Audience Explorer, campaign creation, export, or activation exists.
- [x] **PASS** Later-phase navigation remains disabled and honestly labeled.

## C. Migration and schema

- [x] **PASS** **Critical** Schema version 2 is applied additively and idempotently.
- [x] **PASS** Fresh empty database initialization succeeds.
- [x] **PASS** Populated version-1 database migration preserves Phase 1 row counts/data.
- [x] **PASS** Failed migration cannot falsely advance schema version.
- [x] **PASS** Future/unknown schema version is rejected safely.
- [x] **PASS** `historical_analysis_runs` has required columns and constraints.
- [x] **PASS** Analysis-run list index exists.
- [x] **PASS** Phase 2 campaign filter indexes exist.
- [x] **PASS** Any composite index has measured query-plan justification.
- [x] **PASS** Existing Phase 1 tables/indexes/foreign keys remain valid.

## D. Historical options and overview

- [x] **PASS** Options come from real SQLite values and are deterministically ordered.
- [x] **PASS** Option arrays are bounded and exclude blanks.
- [x] **PASS** Available date range is correct.
- [x] **PASS** Default filters are correct.
- [x] **PASS** Overview counts independently reconcile.
- [x] **PASS** Financial totals independently reconcile.
- [x] **PASS** Rates use documented denominators.
- [x] **PASS** Zero denominators never produce NaN/Infinity.
- [x] **PASS** Monthly trend is chronological and bounded.
- [x] **PASS** Channel/category/campaign/product breakdowns are deterministic and bounded.
- [x] **PASS** Overview returns no person-level data.

## E. Cohort semantics

- [x] **PASS** **Critical** Cohort labels are calculated at distinct customer grain.
- [x] **PASS** **Critical** A customer with multiple matching rows is counted once.
- [x] **PASS** **Critical** A customer is positive when any matching row meets the selected definition.
- [x] **PASS** **Critical** Activity outside filters cannot change the current label.
- [x] **PASS** **Critical** `positive + unlabeled = selected distinct customers` always holds.
- [x] **PASS** UI/docs explicitly state unlabeled is not confirmed negative.
- [x] **PASS** `contacted_only=true` correctly restricts eligible observations.
- [x] **PASS** `contacted_only=false` correctly includes all matching records.
- [x] **PASS** Date boundaries are inclusive.
- [x] **PASS** Campaign, product, category, channel, and type filters work independently and together.
- [x] **PASS** SQL-looking values remain ordinary parameter values.
- [x] **PASS** Zero-match behavior is stable and user-friendly.

## F. Conversion definitions

- [x] **PASS** **Critical** `ATTRIBUTED_PURCHASE` requires attributed flag and purchase flag.
- [x] **PASS** **Critical** `ANY_PURCHASE` requires purchase flag.
- [x] **PASS** **Critical** `RESPONSE` requires response flag.
- [x] **PASS** Default is `ATTRIBUTED_PURCHASE`.
- [x] **PASS** Inconsistent label/attribution fixture is detected or handled according to the documented rule.
- [x] **PASS** Conversion definition is persisted and displayed.

## G. Profiles and determinism

- [x] **PASS** Selected, positive, unlabeled, and historical baseline profiles exist.
- [x] **PASS** Profiles are aggregated only; no customer IDs/PII appear.
- [x] **PASS** Profile counts and shares reconcile to group totals.
- [x] **PASS** High-cardinality profiles are bounded with deterministic `Other` handling.
- [x] **PASS** Age uses normalized analysis end date, not current date.
- [x] **PASS** Birthday boundary tests pass.
- [x] **PASS** Income/family-size bands match the frozen contract.
- [x] **PASS** No unsupported attributes are guessed or linked from demographics.

## H. Persistence and Phase 3 handoff

- [x] **PASS** A run is recorded with normalized stable JSON.
- [x] **PASS** Completed run list fields match full results.
- [x] **PASS** Reopened result matches the original saved snapshot.
- [x] **PASS** Failed runs retain internal diagnostic detail.
- [x] **PASS** Public failed-run response is sanitized.
- [x] **PASS** Recent-run pagination/order is correct.
- [x] **PASS** Corrupt stored JSON fails safely.
- [x] **PASS** **Critical** No raw SQL/customer-ID list is persisted as the handoff.
- [x] **PASS** `12_PHASE_3_HANDOFF_CONTRACT.md` matches actual behavior.

## I. APIs

- [x] **PASS** `GET /api/historical/options` passes.
- [x] **PASS** `GET /api/historical/overview` passes.
- [x] **PASS** `POST /api/historical/analyses` passes and returns 201.
- [x] **PASS** `GET /api/historical/analyses` passes.
- [x] **PASS** `GET /api/historical/analyses/{id}` passes.
- [x] **PASS** Unknown ID returns 404.
- [x] **PASS** Invalid inputs return stable 4xx responses.
- [x] **PASS** List and string bounds are enforced.
- [x] **PASS** Response models reject invalid output.
- [x] **PASS** OpenAPI documents the five endpoints.
- [x] **PASS** **Critical** Public responses expose no SQL, stack traces, absolute paths, internal DB errors, raw customer rows, or PII.
- [x] **PASS** All Phase 1 endpoints remain compatible.

## J. Frontend

- [x] **PASS** Overview Phase 1 content still works.
- [x] **PASS** Overview historical section uses real API data.
- [x] **PASS** Overview remains concise and responsive.
- [x] **PASS** Historical Analysis navigation is enabled.
- [x] **PASS** All filter controls load real options.
- [x] **PASS** Form payload matches API contract.
- [x] **PASS** Client and server validation messages are usable.
- [x] **PASS** Result KPIs use server values.
- [x] **PASS** Positive/unlabeled explanation is visible.
- [x] **PASS** Trends/breakdowns/profiles render accessibly.
- [x] **PASS** Recent analyses can be reopened.
- [x] **PASS** Loading, empty, zero-match, error, and retry states work.
- [x] **PASS** Successful retry restores global backend status.
- [x] **PASS** Data-derived text uses safe DOM rendering.
- [x] **PASS** No person-level results table exists.
- [x] **PASS** Narrow-width browser validation passes.

## K. Performance and operations

- [x] **PASS** Options/overview/broad/narrow/reopen timings were recorded on a populated database where practical.
- [x] **PASS** Expensive query plans were inspected.
- [x] **PASS** No N+1 aggregate pattern exists.
- [x] **PASS** No 570K-row API response or Python/browser materialization exists.
- [x] **PASS** No 5M demographic scan is introduced.
- [x] **PASS** Warm POC targets are met or deviations are documented with evidence.
- [x] **PASS** Locked/unavailable database errors are sanitized and recoverable.
- [x] **PASS** Application starts with the documented command.

## L. Tests and documentation

- [x] **PASS** `python -m pip check` passes.
- [x] **PASS** Full pytest suite passes with exact count recorded.
- [x] **PASS** `python -m compileall -q app scripts tests` passes.
- [x] **PASS** README documents setup, migration, endpoints, semantics, UI, tests, and limitations.
- [x] **PASS** Implementation summary is current.
- [x] **PASS** Progress tracker is complete.
- [x] **PASS** Known limitations are explicit.
- [x] **PASS** Final changed-file list and status are recorded.

## Final decision

Record:

- Critical failures: None.
- Other failures/partials: None. The approximate overview and broad-analysis warm
  performance targets are exceeded, but the deviation is measured, explained,
  recoverable through visible synchronous loading, and explicitly allowed by the
  checklist's evidence/documentation condition.
- Residual risks by severity: Medium — broad synchronous analysis takes about one
  minute and overview repeat was 9.50s on the reference machine. Low — one local
  SQLite writer, synthetic-data quality limits, and snapshots do not auto-refresh.
- Full test result: 158 passed in 54.73s; no warnings reported.
- Full-data validation status: PASS — direct read-only SQL reconciled headline,
  monthly, broad/narrow cohort, conversion, invariant, and saved-snapshot values.
- Go / Conditional Go / No-Go for Phase 3: Go.
- Reasoning: All Critical and non-Critical acceptance items pass with concrete
  automated, full-data, runtime, query-plan, documentation, and browser evidence.
  Phase 3 should retain the explicit synchronous-performance risk and honor the
  frozen `analysis_run_id` reconstruction/reconciliation contract.

## Acceptance rerun evidence — 2026-08-21

- Base/resulting HEAD: `c6c9f41ea257aa33ae196b75cc8f76f8419431e7`.
- Checklist status: 115 PASS, 0 failed/partial/not-tested checklist items.
- `python -m pip check`: `No broken requirements found.`
- `python -m pytest -q`: 158 passed in 54.73s; no warnings reported.
- `python -m compileall -q app scripts tests`: passed with no output.
- `git diff --check`: passed; informational LF-to-CRLF notices only.
- `python scripts/validate_data.py --json`: overall `OK` in 11.694s;
  customers 125,000, campaign sales 570,000, demographics 5,000,000,
  zero invalid campaign-customer references, zero PU consistency violations,
  and all 21 required indexes present.
- Git LFS/SHA-256: all three frozen dataset hashes match; no `data/` worktree
  modification is present.
- Scope scan: no model artifact, training/scoring dependency or implementation,
  demographic query in the historical-analysis path, or enabled later-phase
  navigation was found. The sole historical-service `person_id` token is the
  explicit prohibited-output-key guard.
- Decision remains **Go for Phase 3**, subject to the recorded synchronous
  performance and snapshot limitations.
