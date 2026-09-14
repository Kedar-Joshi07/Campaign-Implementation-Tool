# Phase 10 API and Phase 9 Bridge

Generated: 2026-09-14

Prompt: `Prompts/phase10_campaign_intelligence_orchestration_prompt_pack/09_STEP_09_PHASE10_API_AND_PHASE9_BRIDGE.md`

## Step result

`PASS_STEP_09_PHASE10_API_AND_PHASE9_BRIDGE`

Phase 10 orchestration is now exposed through business-safe Campaign Planner
endpoints. A business user can inspect the preparation plan, start or reuse
targeting intelligence, poll progress, and retry a terminal/stale preparation
without supplying a model, scoring run, artifact, job, or generation ID.

## API surface

All endpoints are scoped to
`/api/campaign-planner/contexts/{targeting_context_id}`:

| Method | Path suffix | Behavior |
|---|---|---|
| GET | `/intelligence-plan` | Returns readiness, the no-PII Modeling Context identity, business message, and four-stage reuse summary. It performs no analytical mutation. |
| POST | `/targeting-intelligence/prepare` | Idempotently joins exact active work, returns an exact verified READY result, binds a reusable generation synchronously, or persists/submits one durable parent. |
| GET | `/targeting-intelligence/preparation` | Returns status, stage, monotonic progress, business message, retry/readiness flags, and reuse summary. Analytical IDs and hashes exist only below `technical_details`. |
| POST | `/targeting-intelligence/preparation/retry` | Rejects active/READY conflicts and starts a new exact parent for NOT_STARTED, BLOCKED, FAILED, or STALE state. The Step 8 resolver resumes from the highest verified reusable stage. |

The existing Phase 9 GET/PUT/DELETE `/targeting-intelligence` routes are
unchanged. Manual raw-scoring linkage remains an advanced compatibility route;
the normal Phase 10 preparation route has no request body and therefore cannot
require a raw scoring ID.

Active/terminal progress polling reads the durable parent's persisted reuse
plan. It does not rerun compatibility scans, imports, analysis, training,
scoring, or rank preparation.

## Readiness and currentness rules

READY is fail-closed and is reported only when all of these agree:

- current Campaign Context-derived Modeling Context hash;
- current full intelligence request key, including source and policy identity;
- context binding, parent orchestration, and generation lineage;
- a verified READY generation;
- reusable historical analysis, model artifact, full-universe scoring, rank,
  and analytics; and
- the Phase 9 `source_scoring_run_id` matching the READY orchestration source.

A Modeling Context dimension change returns STALE and cannot reuse the old
binding as READY. Delivery channel remains outside Modeling Context identity;
changing only delivery channel reuses the same verified generation. Repeated
preparation of an existing READY result atomically republishes its verified
Phase 9 source link, covering an intentional advanced unlink without rerunning
analysis, training, scoring, or rank work.

## Phase 9 bridge

Step 8 READY finalization remains the single atomic publication boundary. It
updates the Phase 10 context binding and the corresponding Phase 9
`campaign_targeting_contexts.source_scoring_run_id` only after exact generation
and analytical lineage verification.

The TestClient certification proved the unchanged downstream sequence:

1. create Campaign Context;
2. save business targeting criteria;
3. inspect an all-BUILD intelligence plan;
4. prepare and poll to READY;
5. resolve the existing Phase 9 targeting-intelligence endpoint;
6. build the existing Target Group preview;
7. page the existing Target Group search;
8. save an immutable Target Group and create its Campaign draft; and
9. reopen the same Campaign draft.

The resulting campaign uses the exact verified Phase 10 scoring run. Responses
on the plan/progress surface contain no customer/person/contact fields.

## Error contract

- missing contexts return 404 with a stable business message;
- invalid path/request or corrupted persisted identity returns 422;
- Phase 9 preview remains a 409 conflict while intelligence is not ready or is
  stale;
- retry returns 409 when preparation is already active or READY; and
- expected and unexpected Phase 10 server failures return 500 with
  `Targeting intelligence could not be prepared. Please retry this step.`

Unexpected exception text, tracebacks, paths, SQL, raw values, and PII are
logged server-side only and are not returned to the caller. The optional nested
technical message is constrained to Step 8's sanitized exception-class value.

## Verification

| Gate | Result |
|---|---|
| Final Step 9 focused TestClient suite | PASS - 3 tests in 24.52s |
| Step 8/9 plus Phase 9 bridge regression | PASS - 34 tests in 94.88s |
| Final all Phase 10 tests plus application health/startup contract | PASS - 83 tests in 110.01s |
| Ruff changed-file checks | PASS |
| Python compilation of changed API/schema/router modules | PASS |
| Diff whitespace/error check | PASS (line-ending notices only) |
| Production imports/training/scoring | Not run |

All training, scoring, rank, preview, search, save, and draft proof ran against
bounded temporary SQLite fixtures and temporary model artifacts. No production
or repository runtime database was modified.

## Stop boundary

Step 9 stops after the HTTP contracts, exact readiness projection, retry/error
boundary, verified Phase 9 source publication, and TestClient end-to-end bridge
certification. It does not implement Step 10+ frontend orchestration UI,
lifecycle cleanup, observability, performance, system-browser certification,
CI, or freeze work.

`STOP_AFTER_STEP_09`
