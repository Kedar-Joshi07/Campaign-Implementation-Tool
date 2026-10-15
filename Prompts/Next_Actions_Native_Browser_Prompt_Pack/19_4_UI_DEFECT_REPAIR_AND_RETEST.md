# Prompt 19.4 — repair observed UI/backend defects and recertify

## Common execution contract

Repository: `Kedar-Joshi07/Campaign-Implementation-Tool`. Audited baseline: `9bea771940f930504ee8635c7b14fc988a37568c`. Schema at that baseline: 33. Work on the actual current checkout or a verified descendant; never reset newer work to this SHA. Run `git rev-parse HEAD`, `git status --short`, and read applicable `AGENTS.md`. Record starting/candidate SHA and local diff identity when uncommitted. Preserve unrelated changes and all previous evidence.

Read this pack's `00_README_START_HERE.md`, `01_GUARDRAILS_SCOPE_AND_ORDER.md`, and `02_PENDING_REGISTER_AND_BASELINE.md` first. Discover actual paths with `rg`; suggested new paths are not existing commands. Complete implementation, tests and evidence, not just a plan. If a dependency is genuinely missing, report the exact blocked work while continuing independent tasks.

Keep v1/v2 probability semantics, calibrated artifacts, historical readers/exports, BROAD=.60, explicit v2 .50, default v2 .70 and probability governance intact. Keep v3 PRODUCT_BUYER_SIMILARITY, BUYER_PROFILE_DISTANCE_V1, inclusive minima .50/.60/.70/.80/.90, ANY/max selected-product policy, support floors 200/160/40, support-aware split V2, currentness and immutable lineage. Preserve original 20-scenario JSON and current 10,000 demo gate. Never change scores, filters, products, data or pass criteria to force counts or a GO.

All mutation/testing uses a dedicated disposable database, artifact root, browser profile and downloads directory on loopback. No operator DB import/replacement/migration, actual campaign sending, contact uploads or deployment. No commits, pushes, PRs, workflow dispatch or branch-setting changes unless authorized in the execution session. Preparatory code/test work continues without that remote authority; do not invent remote success.

Browser functionality scope excludes canonical 5M scoring, calibration rescoring of 5M, canonical bulk import and 5M performance certification. It uses bounded synthetic fixtures and real application/backend workers. No mocked successful API responses or fake worker completions as primary proof. The full browser prompt defines a hard row cap and fail-closed guard. Any future canonical-scale recertification is a separate opt-in stage, never invoked by browser/controller defaults.

Evidence must distinguish actual native headed browser execution, automated browser checks, backend-only tests, retained-component harness checks, fixture results, recorded earlier 5M results and fresh remote CI. No PII/secrets/raw worker tokens in shared evidence. Keep screenshots/traces of the synthetic QA environment locally for inspection; do not automatically save browser screenshots to ChatGPT Library.

Completion response: actual SHA/tree identity; files changed; defects reproduced and fixed; schema/API/data impact; exact commands/results; coverage/evidence pointers; statuses PASS/FAIL/BLOCKED/NOT_RUN; preserved contracts; remaining limitations; stage GO/NO-GO; concrete next action. Runtime, native UI, fresh bounded v3, recorded 5M, legacy probability, predictive claims, scoped POC and overall release are separate verdicts.


## Work and acceptance

Consume the actual 19_3 defect/control ledger. Classify UI behavior, payload validation, background lifecycle, counts/currentness, artifacts/exports, accessibility/layout, browser/environment and genuinely unimplemented future capabilities. Do not invent defects or redesign the product without evidence.

For each implemented-feature defect capture exact reproduction, expected versus actual result, browser/network/DB/file lineage, severity and affected modes. Fix the root cause narrowly in actual frontend/backend/shared contracts. Preserve probability compatibility, similarity semantics, no-5M guard, fixture isolation and hidden navigation. Do not enable retained views in production as a shortcut, alter displayed counts, bypass validators, suppress errors or fabricate coordinator success.

Add an independent reproduction test. Run relevant unit/API checks; rerun the actual native control through its event handler and assert persisted side effects. Cover the corrected positive path and its negative guard. Changes to common filters/currentness/cache/profile/scoring require broader versioned regression and an impact assessment for earlier scale evidence. Do not automatically rescore 5M from this stage.

Environment failures remain BLOCKED: missing native executable/display or denied browser launch is not functional GO. Fix ordinary configuration within authority, document any real permission requirement, and continue independent backend checks. Headless/cloud substitution does not satisfy a headed-native certificate.

Avoid uncontrolled retries that hide flaky behavior. Record original failure and explained remediation. After fixes, regenerate inventory, account for new/removed controls, rerun affected cases and final business smoke, and close retained-component coverage. A disabled control is not positive-action PASS; test valid prerequisites or leave blocked.

Output the defect ledger, changed files, tests, before/after evidence and uncovered items. Repeat 19_3 where required; continue 19_5 only after coverage closes.
