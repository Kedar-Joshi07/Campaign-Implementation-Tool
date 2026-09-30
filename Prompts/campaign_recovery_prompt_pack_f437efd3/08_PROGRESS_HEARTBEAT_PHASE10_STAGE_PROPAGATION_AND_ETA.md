# Prompt 08 — Truthful progress, durable heartbeat, Phase 10 stage propagation, workload-class ETA


# Common execution contract

**Canonical starting SHA:** `f437efd3be9e6d4945b0ee12bff91ccce2697088`

You are working on the repository **Campaign Implementation Tool**. Treat the current codebase, database schema, tests, migrations, and committed evidence as authoritative only after you verify them yourself. Do not assume prior summaries are correct merely because they exist in `docs/evidence`.

Before changing anything:

1. Run `git rev-parse HEAD` and confirm the starting commit is `f437efd3be9e6d4945b0ee12bff91ccce2697088` or a documented descendant created by an earlier prompt in this pack.
2. Run `git status --short`. Do not overwrite unrelated local changes. If prior pack steps created changes, preserve them and identify the exact prior step/commit.
3. Read the files named in this prompt plus adjacent callers, tests, migrations, API schemas, and frontend consumers. Search the whole repository for every symbol you modify.
4. Reproduce the current behavior with focused tests before changing it when practical.
5. Keep changes additive and narrowly scoped. Do not rewrite frozen Phase 1-10 behavior unless a defect proven by this pack requires it.
6. Preserve synthetic-data truthfulness. Do **not** fabricate customers, widen targeting filters, lower approved probability thresholds, duplicate people, change scenario definitions, or invent evidence to make a demo pass.
7. Preserve existing immutable lineage. Never rewrite historical attempts, snapshots, calibration artifacts, feedback batches, or audit events in place.
8. Never persist tracebacks, raw exception text, filesystem paths, secrets, contact PII, or unbounded payloads into business-safe runtime fields.
9. Every mutable worker write must be concurrency-safe and transactionally guarded.
10. Do not mark a requirement complete just because code exists. Prove the behavior through tests and, where requested, canonical/runtime evidence.
11. If a required business-policy decision is not encoded in the repository, stop that policy change and produce a decision document instead of silently choosing.
12. Do not commit or push unless explicitly instructed by the operator. At the end, report changed files, tests run, results, remaining risks, and the next prompt to run.

## Required completion format

End the run with:

- **Starting SHA**
- **Working tree state before**
- **Defects reproduced**
- **Root cause**
- **Files changed**
- **Schema/API/contract changes**
- **Tests added or changed**
- **Commands run**
- **Pass/fail results**
- **Evidence artifacts produced**
- **Known remaining risks**
- **GO / NO-GO for this prompt**
- **Recommended next prompt**


## Objective

Replace the "alive but stuck at 3%" experience with truthful, source-derived stage progress without fabricating smooth percentages.

## Inspect at minimum

- Phase 11 runtime/progress repository
- `app/services/phase11_search_orchestration_service.py`
- Phase 10 orchestration stage/progress
- coordinator heartbeat behavior
- result materialization loop
- snapshot validation
- `app/services/phase11_run_lifecycle_service.py` if present
- `frontend/js/run-progress.js`
- status/results UI
- progress/ETA tests

## Required progress model

Create explicit stages such as:
- QUEUED;
- CHECKING_CURRENT_INTELLIGENCE;
- WAITING_FOR_HEAVY_SLOT;
- PHASE10_ANALYSIS;
- PHASE10_MODEL;
- PHASE10_SCORING;
- PHASE10_RANK_ANALYTICS;
- CHECKING_RESULT_CACHE;
- SELECTING_POTENTIAL_CUSTOMERS;
- MATERIALIZING_RESULT;
- VERIFYING_RESULT;
- COMPLETED.

Use actual Phase 10 persisted stage/progress when waiting on Phase 10. Do not map elapsed wall time to fake progress.

A heartbeat may keep `progress_percent` unchanged while updating `heartbeat_at`, but `status_message` should truthfully identify the underlying stage.

## Heartbeat coverage

The attempt must continue heartbeating during all potentially long operations:
- heavy Phase 10 wait/build;
- large member selection;
- snapshot writing/compression;
- checksum/manifest validation;
- other blocking collaborators.

Avoid a heartbeat thread that overwrites a later stage with `CHECKING_INTELLIGENCE`.

Use fencing from Prompt 02 on heartbeat writes.

## Append-only history

Ensure an initial QUEUED progress event is inserted transactionally with search/attempt creation.

Every meaningful stage transition should append an event. Repeated heartbeats may update runtime without flooding event history; define the rule explicitly.

## Workload-class ETA

Classify at least:
- DIRECT_INTELLIGENCE_REUSE;
- PHASE10_REUSE_WITH_VALIDATION;
- NEW_INTELLIGENCE_BUILD;
- EXACT_RESULT_REUSE;
- NEW_RESULT_MATERIALIZATION;
- TOP_N_MATERIALIZATION if materially distinct.

Historical ETA samples must be grouped by meaningful workload/stage class, not only `stage_code`.

Use bounded robust estimates such as p50-p90 only when sample size is sufficient. Otherwise return UNAVAILABLE.

Queue waiting must not be folded into processing ETA.

## UI

Surface:
- queue position when queued;
- last meaningful update / heartbeat freshness where useful;
- stage;
- processed / total when known;
- ETA range only when qualified.

Do not display "0 of unknown processed" misleadingly.

## Tests

- long Phase 10 wait shows persisted heartbeat and Phase 10 stage;
- 10+ second test proves stage does not stay silently 3% with no useful status;
- long materialization continues heartbeat;
- initial event exists;
- progress monotonic;
- ETA unavailable with insufficient history;
- different workload classes do not contaminate each other's history;
- queue time excluded.

## Evidence

`docs/evidence/recovery_hardening/08_PROGRESS_ETA.md`

## Acceptance gate

GO only if a user can distinguish "queued", "actively building/scoring", "materializing", and "stalled" without fabricated progress.
