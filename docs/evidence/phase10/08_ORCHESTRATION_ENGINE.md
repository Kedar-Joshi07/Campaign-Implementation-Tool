# Phase 10 Durable Reuse-or-Build Orchestration Engine

Generated: 2026-09-14

Prompt: `Prompts/phase10_campaign_intelligence_orchestration_prompt_pack/08_STEP_08_DURABLE_REUSE_OR_BUILD_ORCHESTRATION.md`

## Step result

`PASS_STEP_08_DURABLE_REUSE_OR_BUILD_ORCHESTRATION`

Phase 10 now has a persistent parent workflow whose lifecycle, exact requested
intelligence identity, progress, reuse plan, analytical lineage, child-job IDs,
business messages, terminal state, and campaign bindings are durably stored in
`phase10_orchestration_runs` and `phase10_context_bindings`.

## Durable parent and executor safety

`prepare_phase10_orchestration` derives the Modeling Context from a persisted
Phase 9 Campaign Context, builds the exact requested intelligence key, performs
a read-only asset inspection, persists the complete reuse/build plan, and only
then submits work.

The requested key includes the normalized Modeling Context and resolved
historical window; current customer, campaign-sales, and demographic import
identities/checksums/counts; the feature, role, evaluation, training,
eligibility, score-semantics, rank, analytics, lifecycle, generation, and
orchestration contracts; and fixed automated-training settings. Delivery
channel remains excluded, so campaign contexts that differ only by delivery
channel share the same analytical generation.

The process-safe top-level worker is submitted to the existing bounded
`ProcessPoolExecutor(max_workers=1)`. The parent never submits and waits for a
model, scoring, or rank child on that executor. Instead it creates the existing
durable model/scoring child jobs and invokes their synchronous workers/cores
inside the parent. This preserves child lifecycle and progress evidence without
the nested single-worker deadlock.

The detailed Phase 10 table is intentionally the persistent parent-job
authority rather than adding a second generic `jobs` representation. It can
express the required READY, BLOCKED, and FAILED distinction, exact reuse plan,
context/intelligence hashes, generation lineage, and shared-context bindings;
the existing `jobs` table continues to own the actual training and scoring
children.

## Pre-work reuse plan

Before analytical mutation, all four decisions are persisted as `REUSE` or
`BUILD`:

- analysis: exact current Historical Analysis compatibility;
- model: exact Step 6 model/artifact compatibility;
- scoring: exact full-universe Step 7 compatibility; and
- rank: all 100 boundaries plus current canonical analytics readiness.

The plan is conservative and fail-closed. Missing/incompatible upstream state
forces dependent stages to BUILD. Once work completes, the same record is
updated to the actual executed plan before READY finalization.

## Idempotency and generation sharing

- The active-intelligence-key uniqueness constraint and transactional
  create-or-get operation prevent duplicate active parent workflows.
- A repeated exact request joins the existing QUEUED/RUNNING orchestration and
  is not resubmitted.
- Every joining campaign context receives a durable PREPARING binding.
- Final READY publication atomically updates every matching context attached
  to the parent, including each Phase 9 `source_scoring_run_id`.
- A READY context is returned without new work only after scoring, rank, and
  analytics currentness are revalidated.
- If rank/analytics became stale after an earlier READY result, a new
  lightweight parent reuses scoring and repairs rank only.
- A current exact generation for a new campaign context is validated and bound
  synchronously, without queueing training or scoring.
- Different delivery channels with the same Modeling Context and current
  sources share one generation.

This prevents duplicate full-universe scoring for both repeated requests and
concurrent contexts sharing an exact intelligence identity.

## Stages, business labels, and monotonic progress

The engine implements the required technical stages and business labels:

| Progress range | Technical stage | Business label |
|---|---|---|
| 0-10 | `CHECKING_COMPATIBILITY` | Checking available targeting intelligence |
| 10-20 | `RESOLVING_HISTORICAL_CONTEXT` | Checking verified past campaign history |
| 20-25 | `CHECKING_TRAINING_ELIGIBILITY` | Confirming enough past examples |
| 25-45 | `RESOLVING_MODEL` | Preparing targeting intelligence |
| 45-50 | `VALIDATING_MODEL` | Verifying targeting quality |
| 50 | `RESOLVING_SCORING` | Checking potential-customer coverage |
| 50-89 | `SCORING_POTENTIAL_CUSTOMERS` | Matching the full potential-customer universe |
| 90-98 | `PREPARING_TARGET_GROUP` | Preparing Target Group insights |
| 98-99 | `VERIFYING_FINAL_CURRENTNESS` | Final verification |
| 100 | `READY` | Targeting intelligence ready |

Model child progress maps into the parent model range. Scoring child progress
maps monotonically into 50-89, reserving 90-98 for rank/analytics preparation
and 99 for final currentness verification. Repository constraints reject
regression in progress and conflicting analytical IDs.

## Terminal behavior and recovery

Insufficient historical observations or an ineligible cohort becomes BLOCKED
with the governed business message. It is not represented as a technical
failure and creates no model, scoring, or partial READY generation.

Unexpected errors become FAILED with a stable retry message. Only the exception
class is retained as technical detail; exception text, paths, SQL, contact data,
and person/customer identities are not exposed. BLOCKED/FAILED transitions also
atomically update every attached context binding and clear partial generation
references.

At application startup, active QUEUED/RUNNING parents are listed in deterministic
creation order and resubmitted. A RUNNING parent keeps its monotonic progress,
rechecks durable child/assets, reuses the highest compatible completed analysis,
model, scoring and rank state, and continues forward. A crash after generation
registration but before final publication therefore reuses that verified
generation instead of repeating heavy work.

## Regression coverage

Step 8 tests use temporary SQLite databases and artifact directories. Real
training, scoring, rank, and analytics operations run only against bounded
fixture data.

Covered cases include:

- first all-BUILD orchestration through READY;
- persisted plan verification before the worker starts;
- required stage labels and monotonic progress;
- child scoring progress mapping into 50-89;
- explicit failure if any nested child executor submission is attempted;
- same-key active create-or-get and no duplicate submission;
- concurrent same-key contexts joining one parent;
- two delivery channels sharing one generation and exact scoring source;
- exact READY idempotency with no new job/scoring/generation;
- stale analytics detected behind an earlier READY binding and rank-only repair;
- demographics-only drift planning and executing analysis/model REUSE with
  scoring/rank BUILD;
- restart from a persisted post-model stage with no retraining;
- current exact generation binding to a new context with all-REUSE;
- insufficient history ending BLOCKED with no partial READY state;
- changed context/source identity ending in a sanitized FAILED state;
- deterministic startup discovery/resubmission; and
- the Phase 10 parent using the same bounded single-worker executor while all
  child submission functions remain unused.

## Verification

| Gate | Result |
|---|---|
| Final Step 8 focused suite | PASS - 3 tests in 20.24s |
| Step 7/8 combined focused suite | PASS - 8 tests in 52.52s |
| Final affected orchestration/model/scoring/repository/startup suite | PASS - 71 tests in 54.93s |
| Full repository regression after final changes | PASS - 630 tests in 468.76s |
| Ruff changed-file checks | PASS |
| Python compilation | PASS |
| Diff whitespace/error check | PASS (line-ending notices only) |
| Production imports/training/scoring | Not run |

## Stop boundary

Step 8 ends after the durable orchestration service, process worker, executor
submission path, shared READY publication, and startup reconciliation hook. It
does not implement the Step 9 HTTP API/progress response contract, Phase 9 API
bridge tests, or any Step 10+ UI, lifecycle, observability, performance, browser,
CI, or freeze work.

`STOP_AFTER_STEP_08`
