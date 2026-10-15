# Prompt 19.2 — bounded native-QA fixtures and fail-closed compute guard

## Common execution contract

Repository: `Kedar-Joshi07/Campaign-Implementation-Tool`. Audited baseline: `9bea771940f930504ee8635c7b14fc988a37568c`. Schema at that baseline: 33. Work on the actual current checkout or a verified descendant; never reset newer work to this SHA. Run `git rev-parse HEAD`, `git status --short`, and read applicable `AGENTS.md`. Record starting/candidate SHA and local diff identity when uncommitted. Preserve unrelated changes and all previous evidence.

Read this pack's `00_README_START_HERE.md`, `01_GUARDRAILS_SCOPE_AND_ORDER.md`, and `02_PENDING_REGISTER_AND_BASELINE.md` first. Discover actual paths with `rg`; suggested new paths are not existing commands. Complete implementation, tests and evidence, not just a plan. If a dependency is genuinely missing, report the exact blocked work while continuing independent tasks.

Keep v1/v2 probability semantics, calibrated artifacts, historical readers/exports, BROAD=.60, explicit v2 .50, default v2 .70 and probability governance intact. Keep v3 PRODUCT_BUYER_SIMILARITY, BUYER_PROFILE_DISTANCE_V1, inclusive minima .50/.60/.70/.80/.90, ANY/max selected-product policy, support floors 200/160/40, support-aware split V2, currentness and immutable lineage. Preserve original 20-scenario JSON and current 10,000 demo gate. Never change scores, filters, products, data or pass criteria to force counts or a GO.

All mutation/testing uses a dedicated disposable database, artifact root, browser profile and downloads directory on loopback. No operator DB import/replacement/migration, actual campaign sending, contact uploads or deployment. No commits, pushes, PRs, workflow dispatch or branch-setting changes unless authorized in the execution session. Preparatory code/test work continues without that remote authority; do not invent remote success.

Browser functionality scope excludes canonical 5M scoring, calibration rescoring of 5M, canonical bulk import and 5M performance certification. It uses bounded synthetic fixtures and real application/backend workers. No mocked successful API responses or fake worker completions as primary proof. The full browser prompt defines a hard row cap and fail-closed guard. Any future canonical-scale recertification is a separate opt-in stage, never invoked by browser/controller defaults.

Evidence must distinguish actual native headed browser execution, automated browser checks, backend-only tests, retained-component harness checks, fixture results, recorded earlier 5M results and fresh remote CI. No PII/secrets/raw worker tokens in shared evidence. Keep screenshots/traces of the synthetic QA environment locally for inspection; do not automatically save browser screenshots to ChatGPT Library.

Completion response: actual SHA/tree identity; files changed; defects reproduced and fixed; schema/API/data impact; exact commands/results; coverage/evidence pointers; statuses PASS/FAIL/BLOCKED/NOT_RUN; preserved contracts; remaining limitations; stage GO/NO-GO; concrete next action. Runtime, native UI, fresh bounded v3, recorded 5M, legacy probability, predictive claims, scoped POC and overall release are separate verdicts.


## Work and acceptance

Implement the reusable isolated launcher, fixtures, inspector and guard required by 19_3. Read the coverage contract and full browser prompt first.

Launch actual app.main/frontend/lifespan/coordinator/model/scoring/export/feedback services from a disposable source copy or properly isolated worktree. All DB, catalog, artifacts, logs, downloads and browser profiles resolve inside the QA root. Prove default PROJECT_ROOT and worker roots cannot write to the source checkout or operator runtime. Set DATABASE_PATH and fixture expected-count configuration before importing the app. Never change business floors or production defaults.

Default fixture: at most 2,000 prospects. Named 10K qualification fixture: at most 20,000. Check actual rows, not summary metadata. Provide enough distinct historical buyers and overlap for 200/160/40, fixed-seed positive/unlabeled events, separate identities, missing/unknown/boundary categories and every required synthetic contact/consent variant. Empty, sparse-product and stale-source fixtures exercise real states. Freeze manifests and independent expectations before training; do not tune weights, seeds or canonical filters for counts.

Guard before dispatch and inside each real worker. Admit only isolated roots/DBs, loopback QA mode and authoritative population within manifest cap≤20,000. Cover direct model score, v3 generation, Phase 10 prepare, calibration publication/rescore, feedback and startup resume. Wrappers may validate/observe and then delegate to actual workers; no fabricated completion or successful response.

Test over-cap/canonical/wrong-root rejection without creating 5M rows or launching work. A controlled metadata/admission fixture may indicate 5M; rejection must precede the worker body. Real bounded tables are independently counted so metadata cannot hide a larger population. Test a queued forbidden job in an isolated startup fixture. Do not mutate operator jobs.

Separate production business app from labeled retained-component harness. Load actual retained markup/controllers/APIs with test-only navigation; keep production hidden routes unchanged. The older controlled Step 19 executor is not primary proof.

Provide deterministic scoped reset, state waits, owned-process cleanup, source/copy hashes and admitted-population counters. Deliver QA_FIXTURE_MANIFEST, NO_5M_GUARD_EVIDENCE and actual launch/reset/resume commands. Meaningful guard/isolation tests must pass before native mutation tests start.
