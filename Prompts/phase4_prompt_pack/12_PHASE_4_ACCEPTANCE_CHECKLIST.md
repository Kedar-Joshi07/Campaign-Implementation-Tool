# Phase 4 Acceptance Checklist

Any failed **Critical** item = No-Go for Phase 5.

## Baseline
- [x] **Critical** Phase 3 baseline SHA verified.
- [x] Full Phase 3 regression recorded.
- [x] Role-policy-v2 Bagging artifact verified.
- [x] Source datasets unchanged.

## Scope
- [x] FastAPI/Python/sqlite3 preserved.
- [x] HTML/CSS/Vanilla JS preserved.
- [x] No Redis/Celery/Kafka/etc.
- [x] **Critical** No 5M scoring.
- [x] **Critical** No propensity table.
- [x] No Audience Explorer implementation.
- [x] No Campaign Builder/export.
- [x] No customer/person linkage.
- [x] Frozen 11-feature contract unchanged.

## Schema v4
- [x] **Critical** additive/idempotent migration.
- [x] Populated DB preserved.
- [x] Rollback tested.
- [x] jobs constraints/indexes correct.
- [x] no model_runs regression.
- [x] no propensity_scores.

## Jobs
- [x] **Critical** one active training job maximum.
- [x] QUEUED→RUNNING→COMPLETED works.
- [x] failure transitions work.
- [x] stale active jobs fail on startup.
- [x] terminal states guarded.
- [x] progress monotonic/bounded.
- [x] public messages safe.

## Background execution
- [x] **Critical** training not executed synchronously in HTTP request.
- [x] bounded executor max_workers=1.
- [x] lazy executor.
- [x] separate worker DB connections.
- [x] no FastAPI BackgroundTasks for training.
- [x] shutdown handled.

## Phase 3 reuse
- [x] **Critical** existing train_and_persist_model remains authoritative.
- [x] no duplicate feature/model/evaluation logic.
- [x] CLI remains functional without progress callback.
- [x] Bagging remains PRIMARY.
- [x] Elkan remains CHALLENGER_1.
- [x] Naive remains DIAGNOSTIC_CONTROL.

## APIs
- [x] POST train returns 202.
- [x] second active train returns 409.
- [x] job status works.
- [x] model list/detail/options work.
- [x] OpenAPI correct.
- [x] 404/422/sanitized 500 correct.
- [x] pagination bounded.

## Data safety
- [x] **Critical** no customer/person ID lists.
- [x] no PII.
- [x] no raw validation scores/matrices.
- [x] no SQL/traceback.
- [x] no absolute local path.

## Model detail
- [x] v2 roles decoded correctly.
- [x] candidate metrics/deltas/flags present.
- [x] artifact verification present.
- [x] legacy v1 remains legacy.

## UI
- [x] **Critical** Model Training enabled.
- [x] Audience Explorer disabled.
- [x] Campaigns disabled.
- [x] completed analysis selection works.
- [x] fixed role cards correct.
- [x] job submit/progress/result work.
- [x] comparison works.
- [x] diagnostic clearly marked.
- [x] challenger advisory supported.
- [x] recent models work.
- [x] no hardcoded metrics/person table/scoring controls.

## Failure/restart
- [x] executor/worker/Phase3/artifact failure -> FAILED.
- [x] stale jobs -> FAILED on startup.
- [x] race accepts at most one job.
- [x] missing artifact reflected safely.

## Regression
- [x] Full pytest passes.
- [x] pip check passes.
- [x] compileall passes.
- [x] diff check passes.
- [x] data validation OK.
- [x] Phase 1/2/3 regressions pass.

## Full-data evidence
- [x] real options loaded.
- [x] real training job submitted asynchronously.
- [x] real job completed.
- [x] real model_run_id returned.
- [x] Bagging selected.
- [x] challenger/control metrics available.
- [x] artifact verified.
- [x] UI walkthrough complete.

## Final decision
Critical failures: none.
Other partials: none.
Full test result: 266 passed, 1 warning.
job_id: 3.
model_run_id: 7.
selected model: BAGGING_PU.
artifact verification: verified=true, sha256=a6f50f3391997bec539f1371306a81d314079020686b588a28b3c44815a1a210.
restart test: startup stale QUEUED/RUNNING reconciliation to FAILED validated.
concurrency test: near-simultaneous submit admits one active job, second returns conflict.
residual risks: single-worker bounded throughput and local SQLite single-node constraints remain by design.
- **Go / Conditional Go / No-Go for Phase 5:** Go.
- Reasoning: all Critical items passed, boundary constraints are preserved, hardening scenarios were validated, and full-data asynchronous workflow completed with governed model/detail evidence.

## Phase 4 Finalization / Pre-Phase-5 Corrections

- Corrective baseline SHA verified at start: `21bf610b2aabcf2faabee98a82fcb6e637893fb3`.
- Phase 5 handoff baseline reference corrected to prevent accidental Phase 3 checkout for Phase 5 kickoff.
- Model detail API feature-contract metadata corrected to validate and report real persisted contract shape.
- Model API tests now use authoritative frozen contract constants/shape (not synthetic contract fields).
- Worker/executor submission failure HTTP status corrected from 409 to 500 with sanitized message.
- Optional candidate-level progress timing refinement intentionally deferred to avoid invasive model-engine changes.

Corrective verification:

- Focused suite: `53 passed, 1 warning`.
- Full suite: `268 passed, 1 warning`.
- pip check: pass.
- compileall: pass.
- git diff --check: no whitespace/conflict markers (CRLF warnings only).
- data validation: overall_status=OK; customers=125000; campaign_sales=570000; demographics=5000000.
- model_run_id=7 verification: status COMPLETED, selected BAGGING_PU, policy/evaluation versions 2/2, artifact verified true, feature-contract version 1 + authoritative SHA + all 11 features, no customer/person/validation-score/raw-SQL/absolute-path leakage.
