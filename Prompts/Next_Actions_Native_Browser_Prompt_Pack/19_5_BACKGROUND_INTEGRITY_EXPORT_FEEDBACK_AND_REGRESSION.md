# Prompt 19.5 — background correctness and retained behavior closure

## Common execution contract

Repository: `Kedar-Joshi07/Campaign-Implementation-Tool`. Audited baseline: `9bea771940f930504ee8635c7b14fc988a37568c`. Schema at that baseline: 33. Work on the actual current checkout or a verified descendant; never reset newer work to this SHA. Run `git rev-parse HEAD`, `git status --short`, and read applicable `AGENTS.md`. Record starting/candidate SHA and local diff identity when uncommitted. Preserve unrelated changes and all previous evidence.

Read this pack's `00_README_START_HERE.md`, `01_GUARDRAILS_SCOPE_AND_ORDER.md`, and `02_PENDING_REGISTER_AND_BASELINE.md` first. Discover actual paths with `rg`; suggested new paths are not existing commands. Complete implementation, tests and evidence, not just a plan. If a dependency is genuinely missing, report the exact blocked work while continuing independent tasks.

Keep v1/v2 probability semantics, calibrated artifacts, historical readers/exports, BROAD=.60, explicit v2 .50, default v2 .70 and probability governance intact. Keep v3 PRODUCT_BUYER_SIMILARITY, BUYER_PROFILE_DISTANCE_V1, inclusive minima .50/.60/.70/.80/.90, ANY/max selected-product policy, support floors 200/160/40, support-aware split V2, currentness and immutable lineage. Preserve original 20-scenario JSON and current 10,000 demo gate. Never change scores, filters, products, data or pass criteria to force counts or a GO.

All mutation/testing uses a dedicated disposable database, artifact root, browser profile and downloads directory on loopback. No operator DB import/replacement/migration, actual campaign sending, contact uploads or deployment. No commits, pushes, PRs, workflow dispatch or branch-setting changes unless authorized in the execution session. Preparatory code/test work continues without that remote authority; do not invent remote success.

Browser functionality scope excludes canonical 5M scoring, calibration rescoring of 5M, canonical bulk import and 5M performance certification. It uses bounded synthetic fixtures and real application/backend workers. No mocked successful API responses or fake worker completions as primary proof. The full browser prompt defines a hard row cap and fail-closed guard. Any future canonical-scale recertification is a separate opt-in stage, never invoked by browser/controller defaults.

Evidence must distinguish actual native headed browser execution, automated browser checks, backend-only tests, retained-component harness checks, fixture results, recorded earlier 5M results and fresh remote CI. No PII/secrets/raw worker tokens in shared evidence. Keep screenshots/traces of the synthetic QA environment locally for inspection; do not automatically save browser screenshots to ChatGPT Library.

Completion response: actual SHA/tree identity; files changed; defects reproduced and fixed; schema/API/data impact; exact commands/results; coverage/evidence pointers; statuses PASS/FAIL/BLOCKED/NOT_RUN; preserved contracts; remaining limitations; stage GO/NO-GO; concrete next action. Runtime, native UI, fresh bounded v3, recorded 5M, legacy probability, predictive claims, scoped POC and overall release are separate verdicts.


## Work and acceptance

Correlate native browser actions with actual request/run/attempt/job IDs, durable DB state and files. Verify queue versus processing timing, truthful materialized counts, heartbeat/lease claim/release/takeover, duplicate submissions, dependency rejoin, ready-intelligence reuse and restart. Screenshots alone are insufficient.

Use bounded isolated fault cases. Imports are atomic; latest-source checks invalidate incompatible profiles/generations/cache/snapshots even if callbacks fail. Prove no partial file/registry completion, count mismatch, duplicate publication, missing identity or rewritten history. Invalid feature rows remain separately counted. Repeated same-source preflight/download/rerun must not create unnecessary scoring.

For each registered available download profile/version, inspect the native downloaded file: analytics versus contact-only headers, lineage, deterministic order/dedup, CSV formula protection, synthetic consent/identifier/hash/DNC exclusions, audit counts and abort/retry. Analytical selected count can differ from exportable contacts and must reconcile. No provider traffic or campaign sending. Finalize is only a local state transition.

Feedback uses actual CSV/JSON uploads and immutable membership. Prove validation, transaction rollback/idempotence and mode/source/product lineage for accepted and malformed/oversized/duplicate/wrong-person/stale batches. V3 similarity is not probability raw-score input. A separate valid bounded v1/v2 fixture tests existing fit/evaluation isolation and truthful promotion/WAITING_FOR_DATA without changing canonical history or claiming true profile learning.

Retain unversioned v1/v2 API behavior, discrete bands, BROAD=.60, explicit .50, default .70, membership readers and legacy export headers. Ready v3 does not require probability calibration. Keep declared profile-distance and support-aware split contracts. Run affected locked bounded unit/API/Phase 9/10/11/browser regressions, syntax/lint/compile/diff and DB integrity/FK checks; avoid repeated broad runs without new changes.

Deliver 19_5_BACKGROUND_INTEGRITY.md/json mapping UI actions to independent DB/file proof, regression results and zero canonical-scale dispatch. GO requires actual invariants, not relaxed thresholds. Continue 19_6.
