# Stage 14B_09 — integration closure

Recorded 2026-10-08. Starting/working HEAD: `336875c30fc32b00323d916ecc45b232016168a1`; candidate: **UNCOMMITTED**. Preceding stage: 14B_08 bounded descriptive assurance. The worktree contains the uncommitted 14B_00–08 implementation and this Stage 09 closure. No commit, push, deployment, canonical database migration, campaign send, or full-5M run was performed.

## Decision

**BOUNDED_INTEGRATION_GO** for the explicit v3 descriptive buyer-similarity path and preserved v1/v2 contracts. This is not predictive-model approval, full-five-million-row certification, demo qualification, or remote-CI approval. Stage 08 measured weak product separation and unstable bounded bootstrap membership; its `NO_GO_FOR_PREDICTIVE_OR_PRODUCT_SPECIFIC_CLAIMS` remains in force. Unsupported products and exact counts remain data-driven, and the 10,000 demo criterion was not relaxed.

## End-to-end proof

`tests/test_lookalike_v3_integration_closure.py` imports 200 synthetic attributed buyers and 10 synthetic prospects through the official customer, sales, and demographics importers into a disposable schema-33 database. With no calibration artifact, the real FastAPI lifespan/worker takes an unprepared preflight through profile fitting, score generation, exact current preflight, a completed 10-member search, immutable result detail/history, and a governed email-channel CSV containing 10 rows and similarity—not propensity—fields. An identical second search reuses the exact snapshot; one profile and one scoring generation remain published. Chrome opens the saved result, sees descriptive explanation and currentness, and exposes its Download control. This is a bounded fixture, not a canonical-data result or a performance measurement.

## Requirement and call-path reconciliation

| Boundary | Evidence and outcome |
|---|---|
| Schema/registry and migration | Current schema is 33. Frozen schema-32 assertions retain their historical table set; fresh schema-33 has exactly one additive `buyer_similarity_export_events` table. Schema-32-to-33 migration preserves legacy export SQL and foreign keys. Historical v1/v2 rows and probability scores were not rewritten. |
| API/options and explicit mode | Unversioned `/api/export-profiles` and `/api/potential-customer-search/options` return the original 10 profiles. Explicit `?include_similarity=true` exposes the additional 20 v3 profiles; the new business form requests it. V3 request/registry validation requires version `3` and similarity semantics. The advanced probability form still sends the v2 shape and defaults to its recorded 0.70 choice; legacy BROAD remains 0.60 and explicit v2 0.50 remains distinct. |
| Context, product support, identity | Exact product IDs, supported attributed-buyer cohorts, source checksums, profile-set/method fingerprints, and mode-specific context and cache identities are exercised by the 14B_01–05 focused suites and the import-to-HTTP integration. No unsupported-product fallback or cross-mode cache reuse was accepted. |
| Queue, fencing, retry, readiness | The Phase 11 coordinator dispatches version `3` to the fenced similarity executor, not the Phase 10 probability worker. Existing attempt/lease and retry tests passed in the uninterrupted bounded suite. Separate similarity readiness is exposed by health/options; absence of probability calibration does not become similarity failure. Missing exact v3 preparation is represented as not prepared and can be built by the worker. |
| Score/attestation/preflight | Stage 04 scoring and attestation tests and Stage 05 exact preflight tests passed. The real worker published one verified generation; subsequent preflight was CURRENT and selected exactly the same 10 fixture prospects as materialization. No raw score was converted to a probability. |
| Snapshot/history/export/feedback | Stage 07 membership, export, and feedback tests passed. V3 result reopen uses the supplied artifact root consistently for currentness and download eligibility; history uses the same root. The integration browser confirmed the real Download control. Similarity exports and feedback lineage stay separate from probability calibration/retraining. |
| Frontend/legacy compatibility | 12 v3 Chrome tests, 17 legacy business-form Chrome tests, and 52 other Phase 11 Chrome tests passed. The legacy options retry/availability mocks were made query-aware without changing their assertions. The bounded main suite passed end to end, including Phase 9/10/11 API and historical tests. |

## Exact verification results

| Command or check | Result |
|---|---|
| `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_lookalike_v3_baseline_compatibility.py tests/test_lookalike_v3_contract_migration.py tests/test_buyer_similarity_cohort_service.py tests/test_buyer_similarity_profile_service.py tests/test_buyer_similarity_scoring_service.py tests/test_lookalike_v3_preflight_search.py tests/test_lookalike_v3_snapshot_export_feedback.py tests/test_buyer_similarity_assurance_service.py --maxfail=1` | 72 passed in 195.51 s before final Stage 09 compatibility edits; the later complete bounded suite covers these unmarked tests again. |
| Targeted historical/current schema tests | 4 passed in 22.14 s; v32 and v33 exact table sets are separately asserted. |
| Targeted options and v3 service tests | 15 passed in 91.11 s. |
| `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_lookalike_v3_business_ui.py tests/test_lookalike_v3_integration_closure.py --maxfail=1 --tb=short` | 12 passed in 116.59 s, real local Chrome against disposable fixtures. |
| `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -m browser tests/test_phase11_business_search_form.py --maxfail=1 --tb=short` | 17 passed, 43 deselected in 123.40 s. |
| Remaining `test_phase11_*.py` files with `-m browser --maxfail=1 --tb=short` | 52 passed, 249 deselected in 133.64 s. |
| `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -m 'not cleanroom and not full5m and not performance and not browser' --maxfail=1 --tb=short` | **1,128 passed, 132 deselected in 2,931.86 s** in one uninterrupted final run. Earlier fail-fast runs exposed the schema inventory and legacy profile regressions and were superseded by this pass. |
| `python scripts/validation/run_cleanroom_phase1_to_phase7.py --report-path docs/evidence/lookalike_v3/09_PHASE1_TO_7_CLEANROOM.md --json-path docs/evidence/lookalike_v3/09_PHASE1_TO_7_CLEANROOM.json` | PASS; deterministic generation, imports, model/scoring, audience/campaign/export, drift, and cleanup stages all PASS on bounded disposable data. |
| Scoped `python -m ruff check` of schema, results, submission, router, and the new integration/browser/snapshot tests; `git diff --check`; `python -m pip check` | Pass. `git diff --check` prints only existing README line-ending warnings. |

The broader `ruff check app` plus selected v3 tests is **not green**: it reports 15 findings in pre-existing/earlier-stage files, including unused imports, pytest fixture imports, and an unexercised undefined-name path. Including the historical Phase 11 fixture-import test also reports its existing F401/F811 fixture-pattern findings; it is not included in the scoped lint pass. These are disclosed rather than treated as a Stage 09 lint pass. Standalone `node --check` could not run because Node is not installed; Chrome executed and parsed the changed JavaScript in the 81 passing browser tests. No remote exact-SHA CI, 5M certification, predictive outcome validation, or 20-scenario browser qualification was performed in this stage.

## Changed Stage 09 surfaces and current hashes

Stage 09 added the real import→HTTP→Chrome integration test, corrected v3 result/history artifact-root projection, restored unversioned legacy profile catalogs with explicit v3 opt-in, separated schema-32 and current schema-33 table inventories without changing original assertions, and updated the two query-aware browser mocks. It also clarifies the current contract in the root/index documentation. The broader dirty tree includes prior 14B stages and was preserved.

Current working-file Git object hashes (not a commit SHA): `app/database/schema.py` `4a0757400a03214ed113a456749ad394d006f6de`; `app/services/potential_customer_search_submission_service.py` `830b4a7a165444d066354731a46dfb86ad2cb924`; `app/services/phase11_results_service.py` `8f03b4cc1cd14094f5c1c5b45d306caa531ac490`; `app/routers/potential_customer_search.py` `e81d3a179b65133d5f6994f6655e724374ca8e6a`; `frontend/js/business-search-form.js` `0550b46c26b9968c7c92c59c62b9f6f5281f291e`; `tests/test_lookalike_v3_integration_closure.py` `f4f6aee0906dce73ee636f27068927a2ec4b81c1`.

Machine-readable result: [09_INTEGRATION_CLOSURE.json](09_INTEGRATION_CLOSURE.json). Bounded Phase 1–7 report: [09_PHASE1_TO_7_CLEANROOM.md](09_PHASE1_TO_7_CLEANROOM.md). Next prompt is 14B_15 only on operator direction; this Stage 09 result does not pre-certify its fault/recovery gate.
