# 19.1 independent fresh-v3 functional gate

Verdict: **V3_FRESH_BOUNDED_GO** for a local, single-node buyer-similarity POC only. Native headed UI, canonical 5M, predictive outcome value, legacy full-fresh probability, fresh remote CI and overall release are not certified by this result.

## Execution and actual effects

Starting HEAD remained `9bea771940f930504ee8635c7b14fc988a37568c`; changes are uncommitted. `scripts/validation/run_post14b_fresh_v3.py` created an ignored disposable root under `output/post14b_closure/q/` and ran `tests/test_post14b_fresh_v3_gate.py` in the isolated pinned venv. The final run passed 3 tests in 42.86 seconds. Its versioned `sources/v1` CSVs contained 230 synthetic customers, 630 attributed sales (three overlapping products with 210 distinct buyers apiece), and 200 separate synthetic contactable prospects. Production initialization/import recorded all three source identities. The DB initially had zero buyer profiles and generations.

The real `app.main` lifespan and Phase 11 coordinator handled an HTTP v3 create request. The worker built frozen buyer cohorts and support-aware V2 partition, published three `BUYER_PROFILE_DISTANCE_V1` profiles, scored 200 prospects per product (600 score evaluations), published three attested score generations, completed exact preflight, immutable result snapshot, history and governed email export. Export included buyer similarity, not propensity. A governed feedback item was retained against an immutable member, with recalibration `NOT_AVAILABLE` and no probability artifact. A second exact request reused the snapshot without creating new profiles/generations. A production demographics replacement import then made the old similarity preflight `STALE` with no selected count. The bounded count remained below 10,000; it is not demo-ready by assertion. An unsupported P4 preflight was rejected without creating a run.

The first execution reproduced a real bug: multi-product score callbacks reset `processed_count` from the previous product, causing `Phase11RegistryValidationError` and a failed run. The repair maps each product's 200 scored rows to a cumulative 600-evaluation work counter, computes percentage across all products, and labels the unit `score evaluations` while active. The terminal result resets the unit to `people`. The new test verifies monotonic durable scoring events and 600/600 evaluations. The first path-length issue was Windows-specific QA-root depth; the runner now uses a shorter dedicated path, not a production artifact change.

## Negative boundaries and regression

- Wrong QA root, missing lock, over-2,000 and zero-population fixture: rejected before import.
- No published artifact at start; unsupported product rejected before run creation; source replacement made previous preflight stale, rather than falsely complete/current.
- Existing tampered-snapshot export/feedback fail-closed test, shared heavy generation after source change, and shutdown/restart fencing: 3 passed in 59.82 seconds.
- `tests/test_phase11_run_lifecycle_progress.py` and `tests/test_phase11_attempt_execution_fencing.py`: 29 passed in 69.85 seconds.
- Workflow YAML validation: PASS. `.github/workflows/fresh-v3-bounded-validation.yml` is a separate, reviewable, bounded manual workflow and was **not dispatched**. Existing `full-validation.yml` and its campaign-group rejection are unchanged.

## Scope decision

The approved scope for this evidence is a local single-node descriptive buyer-similarity POC with strict source/currentness, support and immutable-result governance. It does not certify purchase probability, prospective response/lift, true automatic profile retraining, production distribution/auth/activation, or actual campaign sending. The prior manual full-fresh probability workflow remains **BLOCKED_BY_DATA**: the canonical history lacks three independent campaign-connected groups. The previously recorded 5M v3 performance and 20-scenario counts remain recorded prior gates, not results of this fixture. Changing overall release policy or required remote checks requires operator authority; overall release remains **NO-GO / pending**. Next: 19.2 isolated QA fixtures and comprehensive no-5M guard, then 19.3 native headed browser.
