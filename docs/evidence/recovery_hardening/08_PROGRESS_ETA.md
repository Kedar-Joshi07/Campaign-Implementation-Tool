# Step 08 — Truthful progress, durable heartbeat, Phase 10 propagation, and ETA

## Starting SHA and working tree

Starting SHA: `f437efd3be9e6d4945b0ee12bff91ccce2697088`.

The working tree already contained the sequential, uncommitted recovery-hardening
changes from Steps 01–07. Step 08 preserved those changes and did not commit or
push.

## Defects reproduced

1. Phase 11 exposed a generic early intelligence-check state while durable Phase
   10 work had more precise analysis, model, scoring, and rank stages.
2. The old heartbeat path represented liveness as repeated progress messages,
   which could flood append-only progress history and overwrite useful stage
   context.
3. The runtime had no durable workload classification, so historical ETA samples
   could mix direct reuse, validation reuse, new builds, exact-result reuse, and
   new materialization.
4. Search creation did not append a transactional initial `QUEUED` event.
5. UI copy could show `0` processed with an unknown total, did not show queue
   position, and did not distinguish current from stale worker heartbeats.
6. Terminal API projections included a continuously changing heartbeat age,
   making otherwise immutable blocked/failed responses differ between reads.
7. Stale-attempt retry terminalized the old attempt without appending its
   meaningful `FAILED` transition before creating the next queued attempt.

## Root cause

Phase 11 treated Phase 10 as one opaque dependency and used a combined progress
update as its heartbeat. ETA lookup was keyed only by stage. There was therefore
no way to preserve the underlying Phase 10 stage while independently refreshing
liveness, nor to select timing samples from comparable work.

## Implemented progress and heartbeat contract

- Schema version 26 adds durable `workload_class` to the search runtime and an
  index over progress-event workload, stage, and time.
- An `AFTER INSERT` trigger on immutable search attempts appends the initial
  `QUEUED` event inside the same transaction as attempt creation. Retries receive
  their own attempt-scoped queued event.
- Explicit user-visible stages now cover:
  - `QUEUED`;
  - `CHECKING_CURRENT_INTELLIGENCE`;
  - `WAITING_FOR_HEAVY_SLOT`;
  - `PHASE10_ANALYSIS`;
  - `PHASE10_MODEL`;
  - `PHASE10_SCORING`;
  - `PHASE10_RANK_ANALYTICS`;
  - `CHECKING_RESULT_CACHE`;
  - `SELECTING_POTENTIAL_CUSTOMERS`;
  - `MATERIALIZING_RESULT`;
  - `VERIFYING_RESULT`;
  - `COMPLETED`.
- Phase 10 stage, progress, and business message are mapped from its persisted
  orchestration response. Phase 11 never advances progress from elapsed time.
- A fenced heartbeat operation updates only runtime/attempt liveness and state
  version. It does not modify stage, progress, business message, meaningful
  update time, or append a progress event.
- Potentially long Phase 10 calls, member iteration/materialization, snapshot
  writing, and manifest/checksum validation execute under the heartbeat guard.
- Meaningful progress changes append events; unchanged heartbeat ticks do not.
- Completion, safe failure/blocking, and stale-attempt terminalization append
  their terminal events. A stale retry records old-attempt `FAILED` before the
  new-attempt `QUEUED` event.
- Every mutable heartbeat and progress write is protected by the immutable
  attempt number and opaque execution lease fence.

## Workload-qualified ETA

Runtime and event history classify work as:

- `PENDING_CLASSIFICATION`;
- `DIRECT_INTELLIGENCE_REUSE`;
- `PHASE10_REUSE_WITH_VALIDATION`;
- `NEW_INTELLIGENCE_BUILD`;
- `EXACT_RESULT_REUSE`;
- `NEW_RESULT_MATERIALIZATION`;
- `TOP_N_MATERIALIZATION`.

Stage-duration samples are keyed by `(workload_class, stage_code)`. ETA uses a
bounded p50–p90 range only after at least three comparable samples; otherwise it
returns `UNAVAILABLE` with `INSUFFICIENT_STAGE_HISTORY`. Queue wait is projected
separately and is never included in processing ETA.

## API and UI behavior

The additive progress projection exposes workload class, heartbeat age/state,
attempt timing, and the existing bounded ETA fields. Heartbeat freshness is live
only for active lifecycle states; terminal results remain stable and report it as
not applicable.

The progress panel now shows:

- queue position while queued;
- the persisted stage and source-derived percent;
- processed/total counts only when meaningful;
- `Processed count will appear when measurable selection begins` instead of a
  misleading `0 of unknown`;
- qualified ETA only when sufficient comparable history exists;
- current/stale heartbeat guidance for active work.

## Tests added or changed

- transactional initial queued event and heartbeat event de-duplication;
- monotonic progress and fenced terminal transitions;
- real 10+ second Phase 10 scoring wait retaining `PHASE10_SCORING`, `61%`, and
  a live advancing heartbeat without duplicate scoring events;
- long materialization heartbeat retaining `MATERIALIZING_RESULT` without fake
  progress or duplicate history;
- p50–p90 ETA unavailable with insufficient history;
- direct-reuse and new-materialization histories isolated by workload class;
- queue time excluded from processing time and retry clocks reset;
- stale-attempt `FAILED` followed by next-attempt `QUEUED` event ordering;
- stable terminal API projection;
- static UI assertions for queue, freshness, stalled guidance, and unknown-count
  copy;
- fresh/current schema expectations updated to version 26.

## Commands and results

- Focused new acceptance tests: `3 passed in 26.42s`.
- Lifecycle and terminal API compatibility follow-up: `13 passed in 35.96s`.
- Backend certification across lifecycle, concurrency, smart reuse, performance
  gates, Phase 10 retry/rejoin, attempt fencing, and schema migrations:
  `75 passed in 233.70s`.
- Terminal API plus static frontend contract: `2 passed in 16.14s`.
- A broader mixed run completed `116 passed`; its one API equality failure was
  fixed and re-certified above. Its 25 errors were test-environment setup errors
  because Python Playwright is not installed, not application assertions.
- Ruff over all Step 08 Python implementation/test files: passed.
- `git diff --check`: passed; only pre-existing CRLF normalization warnings were
  emitted for unrelated prior-step files.

## Environment limitations and remaining risks

- Python Playwright is not installed in the active environment, so the existing
  Playwright-backed UI suites could not start. No dependency was installed by
  this prompt. Static UI contract checks passed.
- ETA intentionally remains unavailable until three comparable completed-stage
  samples exist. This is a truthfulness property, not a missing fallback.
- SQLite timestamps have second precision; liveness tests therefore also assert
  the monotonic runtime state version.

## Acceptance

**GO for Step 08.** Durable state now distinguishes queued, actively analyzing,
modeling, scoring, waiting for capacity, selecting/materializing, verifying,
completed, and stalled work. Heartbeats remain live without inventing progress or
overwriting later stages, and ETA is shown only from qualified workload-specific
history.

## Recommended next prompt

`09_V2_SCORE_SEMANTICS_MEMBERSHIP_CONTRACT_RESULTS_UI.md`.
