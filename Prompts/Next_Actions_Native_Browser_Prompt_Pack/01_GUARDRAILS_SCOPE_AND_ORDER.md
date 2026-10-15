# Guardrails, scope, and dependencies

## Common execution contract

Repository: `Kedar-Joshi07/Campaign-Implementation-Tool`. Audited baseline: `9bea771940f930504ee8635c7b14fc988a37568c`. Schema at that baseline: 33. Work on the actual current checkout or a verified descendant; never reset newer work to this SHA. Run `git rev-parse HEAD`, `git status --short`, and read applicable `AGENTS.md`. Record starting/candidate SHA and local diff identity when uncommitted. Preserve unrelated changes and all previous evidence.

Read this pack's `00_README_START_HERE.md`, `01_GUARDRAILS_SCOPE_AND_ORDER.md`, and `02_PENDING_REGISTER_AND_BASELINE.md` first. Discover actual paths with `rg`; suggested new paths are not existing commands. Complete implementation, tests and evidence, not just a plan. If a dependency is genuinely missing, report the exact blocked work while continuing independent tasks.

Keep v1/v2 probability semantics, calibrated artifacts, historical readers/exports, BROAD=.60, explicit v2 .50, default v2 .70 and probability governance intact. Keep v3 PRODUCT_BUYER_SIMILARITY, BUYER_PROFILE_DISTANCE_V1, inclusive minima .50/.60/.70/.80/.90, ANY/max selected-product policy, support floors 200/160/40, support-aware split V2, currentness and immutable lineage. Preserve original 20-scenario JSON and current 10,000 demo gate. Never change scores, filters, products, data or pass criteria to force counts or a GO.

All mutation/testing uses a dedicated disposable database, artifact root, browser profile and downloads directory on loopback. No operator DB import/replacement/migration, actual campaign sending, contact uploads or deployment. No commits, pushes, PRs, workflow dispatch or branch-setting changes unless authorized in the execution session. Preparatory code/test work continues without that remote authority; do not invent remote success.

Browser functionality scope excludes canonical 5M scoring, calibration rescoring of 5M, canonical bulk import and 5M performance certification. It uses bounded synthetic fixtures and real application/backend workers. No mocked successful API responses or fake worker completions as primary proof. The full browser prompt defines a hard row cap and fail-closed guard. Any future canonical-scale recertification is a separate opt-in stage, never invoked by browser/controller defaults.

Evidence must distinguish actual native headed browser execution, automated browser checks, backend-only tests, retained-component harness checks, fixture results, recorded earlier 5M results and fresh remote CI. No PII/secrets/raw worker tokens in shared evidence. Keep screenshots/traces of the synthetic QA environment locally for inspection; do not automatically save browser screenshots to ChatGPT Library.

Completion response: actual SHA/tree identity; files changed; defects reproduced and fixed; schema/API/data impact; exact commands/results; coverage/evidence pointers; statuses PASS/FAIL/BLOCKED/NOT_RUN; preserved contracts; remaining limitations; stage GO/NO-GO; concrete next action. Runtime, native UI, fresh bounded v3, recorded 5M, legacy probability, predictive claims, scoped POC and overall release are separate verdicts.


## Evidence authority and gates

| Gate | Meaning | Required evidence |
|---|---|---|
| BASELINE_RECONCILED | actual current code/source/status known | current SHA + issue register |
| V3_FRESH_BOUNDED_GO | new disposable v3 pipeline works from source import | real workers + lineage + counts |
| NO_5M_GUARD_GO | native QA cannot start canonical-scale compute | pre-dispatch rejection + counters |
| BUSINESS_NATIVE_UI_GO | all current business controls/states exercised | installed headed browser + backend evidence |
| RETAINED_COMPONENT_UI_GO | hidden retained controls tested separately | labeled isolated harness + real modules/API |
| BACKGROUND_INTEGRITY_GO | queue/retry/currentness/artifact/export invariants pass | actual state/file/DB transitions |
| SCOPED_V3_POC_GO | approved local v3 scope has passed required gates | explicit scope + all scoped evidence |
| LEGACY_PROBABILITY_FULL_FRESH_NO_GO | canonical history cannot satisfy its isolation rules | unchanged rejection, no bypass |
| PREDICTIVE_CLAIMS_UNVALIDATED | no supported conversion/lift/product-discrimination claim | factsheet + missing-data protocol |
| OVERALL_RELEASE_GO | all requirements of actually approved release scope pass | exact SHA + approved scope + CI/manual |

Without an explicit applicable release-scope decision, report scoped local v3 readiness separately and retain the preexisting overall release NO-GO. A test workflow implementation does not approve a policy change.

## Native QA restrictions

Never use the operator's default `data/campaign_poc.db`, canonical gzip population, existing live browser profile or real contacts. Launch app/server/browser from isolated roots. Test-only expected row counts may match fixtures; demo thresholds/business constants must not be changed. A small selected population may honestly show `demo_ready=false` while the function works.

Default QA limit: 2,000 demographic rows. Upper hard ceiling for a named 10K-qualification fixture: 20,000. Each job checks actual authoritative row count and isolated DB/source/target root before dispatch and again in the worker. Guard indirect v3 generation, old scoring APIs, Phase 10 prepare, calibration publication/rescore and feedback paths. A cap rejection occurs before expensive execution and is a recorded test failure for an unexpected attempted job. No full5m marker, canonical scoring runner or LFS population download is reachable from default QA launch.

Existing controlled executors/fixtures may help setup or fault injection but cannot stand in for real production workers in the primary browser proof. Do not use browser route.fulfill to fake successful business/API responses. Never alter the UI's displayed counts with evaluate/set innerHTML and then call it a pass.

## Sequential dependency map

19_0 → 19_1/19_2 → 19_3 → findings loop 19_4 → 19_5 → 19_6 → 19_7 → 20.
19_1 and 19_2 may be prepared independently with isolated write ownership; 19_3 requires both integrated. Final CI follows code fixes, not an earlier executable. Every fix reruns affected controls and a final business smoke; broad tests are repeated only when changes justify it.

Optional probability/data-learning and canonical-scale stages require their stated inputs and independent authorization. Do not insert them into the browser denominator, make them automatic, or require them to simulate a UI button's bounded behavior.

## Verification limits

The goal is exhaustive coverage of inventoried implemented controls, conditional alternatives and declared state transitions. It is not a mathematical claim of every possible interaction permutation. A currently hidden retained view is not user-accessible merely because a test harness can render it. Hidden navigation is not RBAC. Do not introduce a login/authentication redesign into this local POC task.
