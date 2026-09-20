# Phase 11 Final Acceptance

Generated: 2026-09-20

## Current decision

`PROVISIONAL_GO_AWAITING_DOCUMENTATION_SHA_CI`

All product, data, privacy, reuse, persistence, browser, full-5M, regression, hygiene, and implementation-SHA CI gates are green for trusted implementation SHA `feb18146499bf5a2856b1680b3f658d27db34482`. The decision becomes final `GO` only after the documentation/freeze candidate containing this report passes exact-head GitHub CI.

## Functional acceptance

- Normal business navigation is exactly Home, Find Potential Customers, and Results; legacy UI and APIs are hidden, not removed.
- The single business form persists a distinct immutable run for every intentional submission and preserves frozen Phase 9 context/targeting and Phase 10 orchestration semantics.
- Smart reuse validates an exact immutable snapshot first, otherwise reuses compatible Phase 10 intelligence, otherwise builds only missing analytical layers.
- Search history and membership snapshot identity remain separate; repeated requests preserve history while sharing a valid exact snapshot.
- Atomic result materialization is deterministic, bounded, contact-PII-free, immutable, currentness-aware, and restart-safe.
- All ten backend-owned omnichannel profiles enforce truthful source availability, exact allowlists, row-level consent/contactability/targetability, bounded streaming, and aggregate-only audit.
- Home, Results, Result Detail, and JSON APIs expose business metadata and analytical lineage without contact PII.
- There is no all-permutation precompute. The optional atomic-segment index was benchmarked and deliberately not adopted.
- Schema version 18 preserves future RBAC and feedback/retraining seams without claiming either capability is implemented.

## Certification gates

| Gate | Result |
|---|---|
| Step 17 bounded Phase 11 service/repository/API | PASS — 200 passed |
| Step 17 browser UI contract | PASS — 61 passed |
| Step 17 bounded performance | PASS — 1 passed |
| Retained Phase 1–10 bounded regression | PASS — 655 passed |
| Phase 11 A/B clean-room | PASS — 10/10 scenarios twice; matching canonical SHA |
| Installed-Chrome end-to-end | PASS — all required flows and all 10 profiles |
| Dynamic control/state coverage | PASS — 549 observations; 0 reachable NOT_RUN |
| Responsive/accessibility | PASS — 5 viewports; no horizontal overflow; no unnamed controls |
| Browser telemetry | PASS — 0 console/page/request/critical HTTP errors |
| Full 5M scoring | PASS — 5,000,000 rows and distinct people |
| Full-scale score integrity | PASS — zero duplicate, invalid, missing, extra, or lineage-invalid rows |
| Smart-reuse full-scale scenarios | PASS — new build, exact reuse, intelligence reuse, delivery reuse |
| Deterministic canonical source regeneration | PASS — exact gzip SHA `27d8e2a978458a095e16fc51a682e1f3373e41b663a4e61defa47e2d1bdf8b1d` |
| Step 20 full pytest | PASS — 966 passed |
| Step 21 bounded repository regression | PASS — 855 passed, 111 deselected |
| Step 21 bounded Phase 11 CI command | PASS — 261 passed, 4 deselected locally |
| Phase 1–7 and Phase 10 clean-room regression | PASS |
| SQLite integrity | PASS — `ok` |
| Compile, dependency, diff, repository, and Git LFS hygiene | PASS |
| Exact implementation-SHA GitHub CI | PASS — run `#20`, ID `35330170690`, 5/5 jobs |
| Exact documentation/freeze-SHA GitHub CI | PENDING |

## Exact implementation-SHA CI

- Workflow: `CI`
- Head SHA: `feb18146499bf5a2856b1680b3f658d27db34482`
- Run: `#20`, ID `35330170690`
- URL: <https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool/actions/runs/35330170690>
- Conclusion: `success`

| Required job | Job ID | Result |
|---|---:|---|
| Repository Hygiene | `105552449618` | SUCCESS |
| Python Validation | `105552595728` | SUCCESS |
| Tests | `105552806689` | SUCCESS |
| Clean-Room Phase1-7 | `105552806711` | SUCCESS |
| Frontend Contract / bounded Phase 9+10+11 | `105552806646` | SUCCESS |

The run was selected through GitHub's Actions API with exact `head_sha=feb18146499bf5a2856b1680b3f658d27db34482`, not by branch-latest inference.

## Full-scale trusted lineage

| Item | Exact result |
|---|---|
| Clean Step 20 baseline | `a137b71e33ab37d7551880c927c05318a599939d` |
| Browser | Google Chrome `153.0.8010.48` |
| Canonical demographic rows/columns | `5,000,000` / `40` |
| Generation / analysis / model / scoring | `1` / `4` / `3` / `3` |
| Full scoring rows/distinct | `5,000,000` / `5,000,000` |
| Search 3 source/snapshot | `NEW_INTELLIGENCE_BUILD` / snapshot `1` |
| Search 4 | `EXACT_RESULT_REUSE`, same snapshot, zero membership-source calls |
| Search 5 | `INTELLIGENCE_REUSE`, same generation/model/scoring, snapshot `2` |
| Searches 6–8 | SMS/WhatsApp/Paid Social delivery reuse of snapshot `2` |

No application, frontend, data, or generator file changed between the clean Step 20 baseline and the CI-green implementation SHA. Post-certification changes are limited to evidence, validation scripts, CI configuration, and its pinned browser-test dependency lock.

## Release boundaries

- Full 5M work remains outside normal CI.
- Normal CI runs bounded Phase 11 contract/UI/cache/profile tests and uses the installed system Chrome with a pinned browser-test-only dependency lock.
- UI visibility is not RBAC or API authorization.
- The POC stops at governed target-list download; no activation/send integration exists.
- Future activation/feedback/retraining columns are nullable lineage seams only.

## Finalization condition

Replace the provisional decision with `PHASE_11_FROZEN_GO` only after the documentation candidate's exact SHA and all five required GitHub jobs are recorded as successful in the freeze report.
