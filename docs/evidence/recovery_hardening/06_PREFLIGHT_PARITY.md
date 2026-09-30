# Step 06 — Exact preflight and materialization parity

Date: 2026-09-29
Starting commit: `f437efd3be9e6d4945b0ee12bff91ccce2697088`
Disposition: **GO**

## Defects reproduced

- Preflight and calibrated materialization maintained separate SQL predicate
  implementations.
- Preflight enforced the persisted `propensity_bucket`, while materialization
  used only numeric score bounds. A row assigned to a different discrete bucket
  could therefore be counted differently from the materialized result.
- The preflight cache key omitted explicit catalog, current source, scoring run,
  bucket boundary contract, filter-branch, and selection-mode identities.
- TOP_N preflight returned only the full qualifying intersection. It did not
  distinguish the eventual selected count `min(qualifying, N)`.
- The v2 result-cache identity did not bind the targeting catalog or calibrated
  selection contract version.

## Implemented contract

- Added one calibrated selection contract shared by preflight and the actual
  member iterator. It owns:
  - discrete propensity bucket definitions;
  - inclusive/exclusive boundary metadata;
  - demographic, rank, score, calibration, and bucket SQL predicates.
- Both paths now require the exact persisted bucket and the exact numeric branch
  boundaries. Bucket semantics are:
  - `0.90`: `[0.90, 1.00]`;
  - `0.80`: `[0.80, 0.90)`;
  - `0.70`: `[0.70, 0.80)`;
  - `0.60`: `[0.60, 0.70)`;
  - `0.50`: `[0.50, 0.60)`.
- OR branches use SQL `UNION` during preflight and the globally ordered k-way
  merge during materialization. Both emit/count each person once.
- Preflight now reports both:
  - `qualifying_count`: exact filtered population before selection limit;
  - `selected_count`: eventual materialized count.
- `intersection_count` remains as a backward-compatible alias for the qualifying
  count. Demo readiness uses `selected_count`, so a TOP_N request below 10,000
  cannot be represented as demo-ready merely because its qualifying pool is
  larger.
- The public response additionally binds catalog version, current source identity
  hash, normalized branch hash, selection contract, selection mode, and target.
- Preflight cache contract v2 hashes:
  - criteria and normalized filter branches;
  - catalog version;
  - exact current source import IDs and checksums;
  - generation and scoring run IDs;
  - calibration artifact ID;
  - propensity bucket and exact bounds;
  - calibrated selection contract version;
  - selection mode and target count.
- Result cache contract v3 adds catalog version and calibrated-selection contract
  identity while retaining the full generation fingerprint, bucket, calibration,
  normalized criteria, branches, and selection semantics.
- The scenario qualification script now records qualifying and selected counts
  explicitly. The canonical scenario definitions were not changed.

## Parity matrix

The controlled fixture proves exact preflight-selected count equals immutable
snapshot row count for:

- every lower/upper bucket boundary, including `0.90` and `1.00`;
- ALL_MATCHING;
- TOP_N smaller than the qualifying population;
- TOP_N larger than the qualifying population;
- overlapping OR branches;
- an empty filtered bucket;
- a deliberately bucket-mislabeled score, proving no `>= lower` shortcut;
- calibration replacement and cache invalidation;
- cache-key changes for every semantic/currentness component;
- a larger 10,051-member qualifying fixture.

## Commands and results

- `python -m compileall -q app tests/test_preflight_materialization_parity.py scripts/validation/preflight_demo_readiness_scenarios.py` — passed.
- `python -m pytest tests/test_preflight_materialization_parity.py -q` — **14 passed**.
- `python -m pytest tests/test_preflight_materialization_parity.py tests/test_phase11_smart_reuse_engine.py tests/test_phase11_result_snapshot_materialization.py -q` — parity plus existing reuse/materialization batch **47 passed** before the final additional discrete-bucket case; the final parity file was rerun independently afterward.
- `python -m pytest tests/test_search_recovery_calibration_feedback.py tests/test_intelligence_attestation_currentness.py -q` — **29 passed**.
- `python -m pytest tests/test_phase11_business_search_form.py -q -k exact_preflight_api` — **1 passed, 59 deselected**.
- `python -m pytest tests/test_frontend.py -q` — **46 passed**.
- `git diff --check` — passed; only pre-existing line-ending notices were emitted.

No canonical five-million-row scoring/import run was required or performed. The
larger controlled parity fixture validates the qualification threshold without
altering canonical data or scenario definitions.

## Remaining risk

This prompt certifies selection/count parity and cache identity. It does not
certify the next prompt's orchestration, retry, or broader runtime behavior.
