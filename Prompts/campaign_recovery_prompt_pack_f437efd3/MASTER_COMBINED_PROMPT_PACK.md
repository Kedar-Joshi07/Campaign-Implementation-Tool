# Campaign Implementation Tool — Recovery Hardening Prompt Pack

**Canonical baseline supplied by operator:** `f437efd3be9e6d4945b0ee12bff91ccce2697088`

This pack is designed to address the blockers, incomplete implementations, correctness defects, governance gaps, and certification gaps found in the fine-comb review of the Phase 11 recovery work.

## Why the pack is sequenced this way

Do not start with the zero-customer model problem. First make execution safe:

1. CI/API/mobile correctness
2. stale-worker fencing
3. true dependency retry
4. attestation and source currentness
5. import invalidation
6. preflight parity
7. fast reuse + timing
8. progress/ETA
9. v2 score semantics
10. catalog lifecycle
11. calibration isolation
12. feedback-learning semantics
13. business selection-policy decision
14. chosen conditional implementation path
15. fault/restart certification
16. canonical performance
17. 20-scenario qualification and real runs
18. documentation/evidence cleanup
19. final CI/release gate

## Files

- `00_MASTER_GUARDRAILS_AND_EXECUTION_ORDER.md`
- `01_EXACT_SHA_CI_API_COMPATIBILITY_AND_MOBILE_FIX.md`
- `02_DURABLE_ATTEMPT_FENCING_LEASES_AND_STALE_WORKER_PROTECTION.md`
- `03_TRUE_PHASE10_DEPENDENCY_RETRY_AND_REJOIN.md`
- `04_ATTESTATION_DEEP_VERIFICATION_AND_SOURCE_CURRENTNESS.md`
- `05_IMPORT_INVALIDATION_GENERATION_CALIBRATION_AND_PREFLIGHT_CURRENTNESS.md`
- `06_PREFLIGHT_EXACTNESS_CACHE_IDENTITY_AND_MATERIALIZATION_PARITY.md`
- `07_DIRECT_REUSE_FAST_PATH_HEAVY_GATE_AND_TIME_ACCOUNTING.md`
- `08_PROGRESS_HEARTBEAT_PHASE10_STAGE_PROPAGATION_AND_ETA.md`
- `09_V2_SCORE_SEMANTICS_MEMBERSHIP_CONTRACT_RESULTS_UI.md`
- `10_TARGETING_CATALOG_LIFECYCLE_AND_OPTION_LOAD_CORRECTNESS.md`
- `11_CALIBRATION_TRAIN_CALIBRATE_TEST_ISOLATION_AND_GOVERNANCE.md`
- `12_FEEDBACK_RECALIBRATION_PSI_AND_TRUE_MODEL_LEARNING_BOUNDARY.md`
- `13_ZERO_CUSTOMER_ROOT_CAUSE_AND_SELECTION_POLICY_DECISION_GATE.md`
- `14A_KEEP_ABSOLUTE_PROBABILITY_MODEL_IMPROVEMENT_PATH.md`
- `14B_VERSIONED_SELECTION_CONTRACT_V3_IF_APPROVED.md`
- `15_FAULT_INJECTION_RESTART_CONCURRENCY_AND_CRASH_RECOVERY_MATRIX.md`
- `16_PERFORMANCE_AND_5M_CANONICAL_CERTIFICATION.md`
- `17_20_SCENARIO_PREFLIGHT_REAL_RUN_AND_DEMO_READINESS.md`
- `18_DOCUMENTATION_EVIDENCE_BASELINE_AND_HOUSEKEEPING.md`
- `19_FULL_REGRESSION_CI_RELEASE_GATE_AND_FINAL_NO_GO_GO_REPORT.md`

## Execution rules

Run one prompt at a time. Review the result before moving on. A later prompt may depend on schema/API invariants introduced by an earlier prompt.

**Prompt 13 is an explicit policy gate.** Do not run both 14A and 14B. Run the one matching the approved business decision.

If any step returns NO-GO, fix that step before continuing unless the prompt explicitly permits a documented limitation.

## Operator checklist after every prompt

Record:
- new HEAD SHA if you commit;
- failing/passing tests;
- database migration version;
- whether canonical data was mutated;
- evidence artifact path;
- unresolved risks.

The pack deliberately prohibits fabricated counts, silent threshold changes, demographic filter widening, duplicate customers, and evidence claims from unexecuted paths.

---

# Prompt 00 — Master guardrails, dependency graph, and execution order


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


## Mission

Act as the senior staff engineer, database engineer, ML-governance reviewer, QA lead, and release engineer for the Phase 11 recovery effort. This prompt does not authorize broad implementation. Its purpose is to establish the exact baseline, dependency graph, and invariant set that every later prompt must respect.

## Known audit findings to verify, not blindly trust

The prior fine-comb review found the following candidate problems:

- exact-SHA GitHub CI is red;
- API backward-compatibility expectations conflict with additive v2 status fields;
- a 390px Result Detail browser test overflows horizontally;
- Phase 11 Retry does not restart a failed Phase 10 dependency;
- stale-worker attempt fencing/leases are absent;
- `record_deep_verification_attestation()` is shallower than its name/evidence suggests;
- direct attested reuse may not compare generation source checksums/import IDs with the latest authoritative imports;
- exact preflight can claim currentness without a full currentness gate;
- all approved 0.50+ calibrated probability buckets currently have zero members;
- the feedback loop cannot bootstrap from zero v2 audiences;
- the global Phase 10 heavy-work lock covers cheap direct reuse;
- `processing_seconds` includes queue time;
- the Phase 10 wait can repeatedly heartbeat at 3% without meaningful stage progress;
- initial append-only progress history may be missing;
- ETA stage history is not workload-classified;
- Retry UI uses `crypto.randomUUID()` without the fallback used elsewhere;
- model/calibration/test campaign-group isolation is incomplete;
- the "FeedbackRetrainingWorker" recalibrates existing scores rather than retraining the feature model;
- PSI compares selected feedback audiences to the full 5M population;
- v2 stores calibrated probability in a field/contract named `propensity_score` under membership contract v1;
- v2 Results still surface legacy Match Strength and raw-score summaries;
- an existing stale targeting catalog version may be returned without re-promotion to current;
- README/evidence baselines are stale.

## Required work

Create `docs/evidence/recovery_hardening/00_BASELINE_AND_INVARIANTS.md` containing:

### A. Baseline
Record:
- HEAD SHA;
- schema version;
- application version;
- current CI status for the exact SHA if available locally or through repository metadata;
- Python/package lock identity;
- canonical database path only as a sanitized repository-relative path;
- counts of current Phase 10/11 tables without exposing PII.

### B. Dependency graph
Document the call chain for:
- Search submission -> coordinator -> Phase 11 orchestration -> Phase 10 -> result materialization -> completion;
- Retry -> attempt creation -> coordinator -> dependency ownership;
- Import -> source checksums -> generation currentness -> attestation -> calibration -> preflight -> result reuse;
- Feedback -> adaptive gate -> challenger -> calibration publication.

### C. Invariants
Freeze these invariants:
1. one visible `search_run_id` may have many immutable attempts;
2. only the currently leased attempt may mutate visible run/runtime state;
3. terminal attempts remain immutable;
4. currentness must be proven against the latest authoritative imports, not merely against values stored on the candidate generation;
5. direct reuse may bypass heavy validation only when a durable attestation covers the same immutable lineage **and** current authoritative source identity;
6. a retry of a dependency-owned failure must retry/rejoin the dependency, not immediately reproduce the same terminal state;
7. preflight and actual materialization must use the same selection semantics and lineage;
8. v1 raw-score semantics and v2 calibrated-probability semantics must never be conflated;
9. no demo qualification rule can be silently weakened;
10. evidence must be generated at the SHA it claims to certify.

### D. Prompt execution graph
Recommended order:
`01 -> 02 -> 03 -> 04 -> 05 -> 06 -> 07 -> 08 -> 09 -> 10 -> 11 -> 12 -> 13`, then either the approved `14A` or `14B`, then `15 -> 16 -> 17 -> 18 -> 19`.

Do not implement substantive fixes in Prompt 00 unless required merely to reproduce/document baseline behavior.

## Acceptance criteria

- Baseline evidence exists and references actual current code.
- Every later prompt has a clear dependency on earlier invariants.
- Any mismatch between the known findings and repository reality is explicitly recorded.
- No code behavior is declared fixed in this step.

Return GO only when the baseline is trustworthy enough for implementation work.

---

# Prompt 01 — Make the exact-SHA baseline green: API compatibility, mobile Result Detail, browser retry key fallback


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

Remove the known deterministic CI failures **without hiding regressions**. Preserve the new v2 functionality while restoring a coherent, explicitly versioned API contract and responsive Result Detail behavior.

## Inspect at minimum

- `.github/workflows/*`
- `app/schemas/potential_customer_search.py`
- `app/routers/potential_customer_search.py`
- `app/services/potential_customer_search_submission_service.py`
- `app/services/phase11_results_service.py`
- `tests/test_phase11_api_backward_compatibility.py`
- `tests/test_phase11_results_history_detail.py`
- all tests asserting exact status payload keys
- `frontend/js/business-search-status.js`
- `frontend/js/run-progress.js`
- relevant Result Detail HTML/CSS
- responsive/browser tests

## Workstream A — API contract

Reproduce the failing legacy status-contract test.

Determine the intended public contract from:
- existing route versioning;
- OpenAPI schemas;
- previous Phase 11 compatibility evidence;
- current v2 additions.

Implement one coherent approach:

**Preferred:** preserve a stable legacy/v1 projection where legacy clients/tests require it, and expose additive v2 fields through an explicitly versioned response or clearly versioned endpoint/schema.

Alternative: if repository contracts already explicitly permit additive fields, update tests/docs to reflect that policy, but only if you can prove the compatibility contract really changed intentionally.

Do not simply weaken exact-key assertions because tests fail.

Verify:
- create;
- GET run;
- GET status;
- history;
- result detail;
- OpenAPI generation;
- v1 and v2 request/response round trips.

## Workstream B — responsive Result Detail

Reproduce the 390x844 overflow.

Identify the exact offending DOM element. Typical suspects:
- long SHA/reference text;
- definition-list grid min-width;
- progress metadata;
- buttons/action rows;
- unbreakable IDs;
- code-like technical fields.

Fix the component, not the test viewport.

Test at least:
- 390x844;
- 360x800;
- 768px tablet;
- desktop.

Require `document.documentElement.scrollWidth <= clientWidth` on mobile Result Detail.

## Workstream C — retry idempotency key fallback

Centralize a browser idempotency-key helper. Retry must not directly call `crypto.randomUUID()` when feedback already has a safe fallback.

Use:
- `crypto.randomUUID()` when available;
- `crypto.getRandomValues()` fallback;
- no `Math.random()` fallback.

Use the same helper for retry and feedback where sensible.

## Tests

Add/adjust tests proving:
- v1 contract remains stable or is deliberately versioned;
- v2 fields are available where promised;
- mobile page has no horizontal overflow;
- retry works in a browser context with `randomUUID` unavailable but `getRandomValues` available;
- existing feedback key generation still works.

Run the exact previously failing test groups and the frontend/browser contract suite.

## Evidence

Write:
`docs/evidence/recovery_hardening/01_CI_API_MOBILE.md`

Include failing-before/passing-after test names and the final API contract decision.

## Acceptance gate

GO only when the deterministic exact-SHA failures addressed by this prompt are green. Do not claim repository-wide CI green until Prompt 19.

---

# Prompt 02 — Durable execution lease/fencing for immutable search attempts


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

Eliminate the most serious concurrency defect: a stale worker from Attempt N must never be able to mutate visible state belonging to Attempt N+1.

## Inspect at minimum

- `app/database/search_recovery_schema.py`
- `app/database/phase11_schema.py`
- `app/database/schema.py`
- `app/repositories/campaign_result_registry_repository.py`
- `app/jobs/phase11_search_coordinator.py`
- `app/services/phase11_search_orchestration_service.py`
- `app/services/potential_customer_search_submission_service.py`
- retry/status API
- tests for lifecycle, retry, restart, concurrency

Search repository-wide for all calls to:
- `mark_processing`
- `update_search_progress`
- `bind_current_attempt_lineage`
- `complete_search_run`
- `fail_search_run`
- `retry_search_run`

## Required design

Introduce a durable **attempt execution fence**. Choose a minimal safe design such as:

- immutable `attempt_number`;
- random/opaque `execution_lease_token` generated when an attempt is scheduled/claimed;
- lease owner / claimed-at / heartbeat-at if needed;
- optional monotonic lease generation.

The exact design can differ, but every worker mutation must require the attempt/fence it was given when execution began.

A worker for Attempt 1 must fail closed if:
- `current_attempt_number` became 2;
- lease token changed;
- attempt is no longer PROCESSING;
- visible run is terminal for another attempt.

## Repository contract changes

Change mutation APIs so callers cannot omit the fence accidentally. Prefer explicit parameters such as:
`attempt_number` and `execution_lease_token`.

Guard SQL with predicates that include the fence, e.g. conceptually:

`WHERE search_run_id=? AND current_attempt_number=? AND ...`

and verify the attempt row matches the token/status.

Do not read `current_attempt_number` at write time and then attribute a stale worker's event to the newly current attempt.

## Retry behavior

When a stale PROCESSING attempt is declared failed:
- terminalize that exact old attempt;
- create the next immutable attempt;
- issue a new lease;
- reset visible runtime for the new attempt;
- do not allow the old worker to complete/fail/update progress afterward.

## Event history

Every progress/failure/completion event must record the worker's actual immutable attempt number, never "whatever is current now."

## Migration

Schema change must be:
- additive;
- idempotent;
- backfilled safely for existing attempts/runs;
- transactionally validated;
- covered by upgrade tests from v17/v18/v19/v20/v21 as applicable.

Do not expose lease tokens through business APIs.

## Mandatory adversarial tests

Create deterministic tests for:

1. Attempt 1 starts; becomes stale; retry creates Attempt 2; Attempt 1 calls `update_search_progress` -> rejected.
2. Same scenario; Attempt 1 calls `fail_search_run` -> rejected.
3. Same scenario; Attempt 1 calls `complete_search_run` -> rejected.
4. Same scenario; Attempt 1 tries lineage binding -> rejected.
5. Attempt 2 remains healthy after all stale Attempt 1 writes fail.
6. eight concurrent retries with same idempotency key -> one next attempt.
7. retries with different idempotency keys cannot create multiple simultaneously active attempts.
8. restart recovery does not mint duplicate leases for one active attempt.
9. terminal attempt history remains immutable.
10. lease token is not present in public API/business-safe logs.

## Evidence

Write:
`docs/evidence/recovery_hardening/02_ATTEMPT_FENCING.md`

Include a state-transition diagram and the exact SQL-level fencing invariant.

## Acceptance gate

NO-GO if any mutation path can still act on a run using only `search_run_id` without proving the caller owns the current attempt.

---

# Prompt 03 — Make Retry restart or rejoin the failing Phase 10 dependency


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

A retryable Phase 11 failure caused by Phase 10 must not simply create a new Phase 11 attempt and immediately rediscover the same terminal Phase 10 orchestration.

## Inspect at minimum

- `app/services/phase11_search_orchestration_service.py`
- `app/services/phase10_api_service.py`
- `app/services/phase10_orchestration_service.py`
- `app/repositories/phase10_intelligence_repository.py`
- `app/jobs/phase11_search_coordinator.py`
- structured failure code mapping
- retry API/service
- Phase 10 restart reconciliation tests
- Phase 11 retry tests

## Required behavior

Build a failure-ownership map. At minimum distinguish:

- Phase 11-local transient failure;
- Phase 10 transient FAILED;
- Phase 10 BLOCKED due to business/data insufficiency;
- calibration not ready;
- stale/unresponsive worker;
- permanent validation failure.

For retryable Phase 10 transient failures:

1. Phase 11 retry creates a new immutable/fenced attempt.
2. It inspects the exact Phase 10 orchestration/targeting context.
3. If an appropriate Phase 10 orchestration is already QUEUED/RUNNING, **rejoin it**. Do not create a duplicate.
4. If the exact previous Phase 10 orchestration is FAILED and the failure is retryable, invoke the existing governed Phase 10 retry path or create a new exact orchestration according to Phase 10 contracts.
5. Persist the dependency lineage for observability.
6. Keep Phase 11 PROCESSING/WAITING until Phase 10 becomes READY/BLOCKED/FAILED.
7. Continue to result materialization when READY.
8. If BLOCKED for a non-transient business reason, do not auto-retry endlessly.

Do not make Phase 11 call internal worker functions that bypass Phase 10's repository/API state machine.

## Idempotency/concurrency

Two Phase 11 searches sharing the same modeling context must not create two identical heavy Phase 10 builds merely because they retry simultaneously.

Use durable Phase 10 uniqueness/reuse contracts, not a process-local assumption.

## Failure messages

Surface:
- what dependency failed in business-safe language;
- whether retry is eligible;
- whether the retry is waiting on an already-running dependency;
- a technical reference ID safe for support.

Do not expose raw exceptions.

## Mandatory tests

Include:
- exact reproduction of the previously observed "Retry -> immediate same Phase10 FAILED" bug;
- retry creates/rejoins Phase 10 and later completes when the dependency succeeds;
- concurrent retries share one Phase 10 orchestration;
- Phase 10 BLOCKED remains blocked and does not loop;
- permanent Phase 10 validation failure is not marked retryable;
- restart during Phase 10 retry resumes safely;
- stale worker from prior Phase 11 attempt cannot mutate the retry attempt (uses Prompt 02 fencing).

## Evidence

`docs/evidence/recovery_hardening/03_PHASE10_RETRY_REJOIN.md`

Document the dependency-owned retry state machine.

## Acceptance gate

GO only when a controlled transient Phase 10 failure can be retried from the Phase 11 UI/API and reach completion without manually resetting database state.

---

# Prompt 04 — Make intelligence attestation genuinely trustworthy and source-current


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

A fast reusable intelligence attestation must be a safe replacement for repeated 5M deep validation, not merely a row-count memo.

## Inspect at minimum

- `app/services/intelligence_attestation_service.py`
- `app/services/phase10_scoring_resolution_service.py`
- scoring repositories/integrity validators
- `app/repositories/phase10_intelligence_repository.py`
- `app/services/data_import_service.py`
- generation source/import/checksum fields
- currentness helpers
- calibration publication
- tests for scoring integrity and currentness

## Required attestation identity

The attestation key must bind to immutable lineage including at least:

- generation ID;
- scoring run ID;
- model run/artifact identity;
- feature/scoring contract identity;
- demographic import ID + checksum;
- customer import ID + checksum where required;
- campaign-sales import ID + checksum where required;
- schema/integrity contract version;
- relevant ranking/analytics versions.

Then, **before accepting the attestation as current**, compare those identities with the latest authoritative source imports/currentness contract.

An attestation must never be considered current simply because the generation still contains the same old checksum it had when attested.

## Deep verification

At attestation creation, prove the full expensive properties needed for safe reuse, once:

- expected population count;
- actual score count;
- distinct person count;
- no duplicates;
- no missing demographic people;
- no extra people;
- all scores finite and in allowed range;
- source provenance matches;
- scoring/model lineage matches;
- feature/scoring contract matches;
- rank/analytics readiness where the direct-reuse path depends on it;
- optionally deterministic artifact/scoring verification already supported by existing validators.

Reuse existing authoritative validators rather than reimplementing divergent logic.

Persist:
- verification contract version;
- verified facts/hash;
- verified row count;
- verified-at;
- source identity;
- failure status if verification fails.

Do not promote/create a VERIFIED attestation if any required check fails.

## Invalidation/currentness

On source change, either:
- make currentness comparison fail automatically by latest-import identity; and/or
- explicitly stale dependent attestations/generations.

Prefer correctness that does not depend solely on a best-effort invalidation side effect.

## Performance requirement

Ordinary direct reuse after a VERIFIED current attestation must not re-run the 5M deep scan.

The expensive deep verification belongs to:
- attestation creation/refresh;
- controlled repair;
- explicit certification.

## Tests

Prove:
- duplicate score row -> no VERIFIED attestation;
- missing identity -> no VERIFIED attestation;
- invalid score -> no VERIFIED attestation;
- source import changes after verification -> `has_current_attestation` becomes false;
- unchanged source + unchanged generation -> fast true;
- attestation from old schema/integrity contract is not silently reused;
- direct reuse does not invoke the deep validator on every request.

## Evidence

`docs/evidence/recovery_hardening/04_ATTESTATION_CURRENTNESS.md`

Include before/after call graph and benchmark showing attestation reuse is cheap.

## Acceptance gate

NO-GO if `has_current_attestation()` can return true after an authoritative source changes without a new matching verification.

---

# Prompt 05 — End-to-end invalidation after authoritative imports


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

Make authoritative source replacement propagate safe currentness across targeting catalogs, Phase 10 generations, attestations, calibration artifacts, preflight cache, result snapshots, and exports.

## Inspect at minimum

- `app/services/data_import_service.py`
- `app/services/targeting_option_catalog_service.py`
- generation/currentness repositories
- `app/services/intelligence_attestation_service.py`
- `app/services/propensity_calibration_service.py`
- `app/services/potential_customer_preflight_service.py`
- result snapshot/currentness/export services
- import/migration tests

## Define dependency matrix

For each authoritative dataset:
- customers;
- campaign_sales;
- demographics;

document exactly which downstream artifacts depend on it.

Examples to verify:
- targeting option catalog version;
- modeling context/generation compatibility;
- raw scoring currentness;
- calibration artifact validity;
- preflight cache;
- result snapshot currentness;
- export eligibility.

## Required invalidation semantics

After a successful authoritative import:
- build/re-promote the correct targeting catalog;
- ensure stale catalog versions are not returned as current;
- ensure prior incompatible generation/attestation cannot be direct-reused;
- stale calibrations whose scoring/source identity is no longer valid;
- stale relevant preflight cache entries;
- prevent stale snapshots from being downloaded against a changed demographic source;
- preserve immutable historical records rather than deleting them.

The import itself must remain atomic and truthful. If post-import invalidation/catalog maintenance fails after the authoritative data commit, startup reconciliation must deterministically repair the derived currentness state.

## Preflight currentness

Preflight may return `CURRENT` only if:
- generation is READY/reusable;
- latest sources match;
- required attestation is current;
- promoted calibration belongs to that exact current scoring lineage;
- catalog version is the requested/current allowed version.

Otherwise return an explicit safe state:
`STALE`, `UNVERIFIED`, or `NOT_AVAILABLE` as appropriate.

Do not return zero count as though it were a valid current calibrated count when lineage is stale.

## Tests

Simulate:
1. preflight cache CURRENT;
2. authoritative demographics import changes checksum;
3. same preflight request;
4. old cache cannot be used as current;
5. old direct attestation cannot be reused;
6. old result cannot be downloadable;
7. new catalog becomes current.

Repeat relevant cases for campaign_sales/customers according to actual dependency graph.

Test import checksum returning to a previously seen catalog version and prove that version is correctly re-promoted current.

## Evidence

`docs/evidence/recovery_hardening/05_IMPORT_INVALIDATION.md`

## Acceptance gate

GO only when source replacement cannot leave a logically stale artifact reporting itself as current.

---

# Prompt 06 — Make exact preflight a trustworthy qualification gate


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

Guarantee that preflight and actual v2 result materialization use the same selection contract, current lineage, filters, bucket boundaries, deduplication, and selection semantics.

## Inspect at minimum

- `app/services/potential_customer_preflight_service.py`
- `app/services/phase11_search_orchestration_service.py`
- normalized criteria/filter-branch builders
- propensity bucket definitions
- calibrated score schema/indexes
- TOP_N/ALL_MATCHING behavior
- `scripts/validation/preflight_demo_readiness_scenarios.py`
- scenario pack JSON

## Required properties

### Same lineage
Preflight must bind:
- generation ID;
- scoring run ID;
- calibration artifact ID;
- catalog version/current source identity.

### Same filters
Preflight and actual search must use the same normalized branch representation. Avoid maintaining two subtly different filter implementations.

Prefer extracting a shared predicate/selection contract layer used by:
- exact preflight count;
- calibrated member iterator.

### Same bucket semantics
Prove inclusive/exclusive boundaries exactly:
- 0.90: [0.90, 1.00] according to contract;
- other buckets: [lower, upper) unless the frozen contract says otherwise.

Do not count all >= lower if the actual search selects only one discrete bucket.

### Same OR/dedup semantics
Overlapping branches must count each person once exactly as materialization emits them.

### Selection mode
- `ALL_MATCHING`: preflight intersection count equals eventual resolved count.
- `TOP_N`: report both qualifying population and eventual selected `min(qualifying, N)` clearly.

### Cache identity
Cache key must include every semantic/currentness component needed so a cache entry cannot survive:
- source change;
- generation change;
- calibration change;
- criteria change;
- bucket change;
- contract version change.

## Mandatory parity tests

For controlled fixtures and at least one larger fixture:
- preflight count == materialized snapshot row count;
- overlapping OR branches;
- empty bucket;
- exact lower/upper boundary values;
- ALL_MATCHING;
- TOP_N smaller than qualifying population;
- TOP_N larger than qualifying population;
- source/calibration change invalidates cache.

## Evidence

`docs/evidence/recovery_hardening/06_PREFLIGHT_PARITY.md`

## Acceptance gate

Do not use preflight as the 10,000-customer qualification gate until parity tests prove the count and actual search agree.

---

# Prompt 07 — Separate cheap reuse from heavy work and correct queue/processing timing


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

Prevent cheap exact/direct reuse from waiting behind the global heavy-work slot and make runtime timing fields semantically truthful.

## Inspect at minimum

- `app/services/phase11_search_orchestration_service.py`
- `_PHASE10_HEAVY_GATE`
- `_phase10_state`
- coordinator worker limits/queues
- runtime schema
- ETA/projected status
- Results processing-duration rendering

## Heavy-gate redesign

Current conceptual issue to verify:
`with _PHASE10_HEAVY_GATE: _phase10_state(...)`
means even the cheap attested-generation lookup is serialized.

Refactor so:

1. perform bounded cheap current attested direct-reuse lookup outside the heavy gate;
2. if reusable intelligence exists, continue immediately;
3. only if fallback Phase 10 compatibility/build work is required, acquire the heavy-work gate;
4. after acquiring the gate, recheck whether another worker prepared the intelligence while this worker waited;
5. build only if still needed.

This must be race-safe and must not create duplicate heavy work.

## Timing semantics

Separate:
- queued_at / created_at;
- processing_started_at;
- completed_at;
- queue_seconds;
- processing_seconds;
- total_elapsed_seconds if useful.

Do not compute `processing_seconds` from a timestamp written while still QUEUED.

Retry attempts need the same semantics.

Preserve backward compatibility where possible; if an existing public field's meaning was wrong, document the correction and test it.

## Queue observability

Queue position should be calculated consistently and cheaply for queued runs. Processing duration should begin only after the worker actually claims/starts the attempt.

## Tests

- cheap direct reuse completes while an unrelated heavy build holds the heavy gate;
- two workers race: one builds, the waiter rechecks and reuses;
- no duplicate generation/scoring work;
- queue wait of N seconds does not inflate `processing_seconds`;
- total elapsed can include queue time if exposed;
- retry timing resets per attempt while historical attempt timestamps remain immutable.

## Evidence

`docs/evidence/recovery_hardening/07_FAST_PATH_AND_TIMING.md`

Include a sequence diagram.

## Acceptance gate

GO only if verified reuse does not block behind unrelated heavy compute and processing time excludes queue wait.

---

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

---

# Prompt 09 — Correct v2 calibrated-probability semantics end to end


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

Stop conflating legacy raw model scores with calibrated purchase probabilities.

## Inspect at minimum

- `app/services/phase11_result_snapshot_service.py`
- result membership constants/contracts
- `app/services/phase11_search_orchestration_service.py`
- calibrated member iterator
- `app/services/phase11_results_service.py`
- response schemas
- export templates/profile fields
- frontend Results/Detail rendering
- tests/evidence for v1 snapshots

## Required contract decision

Preserve v1 immutable semantics:
`propensity_score` = legacy/raw score.

For selection contract v2, introduce an explicit versioned membership/result contract rather than storing calibrated probability under a v1 raw-score semantic name.

Preferred v2 analytical membership fields:
- person_id;
- calibrated_purchase_probability;
- probability_bucket;
- percentile/rank fields as actually defined;
- optional raw_propensity_score only if justified and clearly named.

Do not mutate old v1 snapshot files.

Result cache keys and manifests must include the membership/selection contract version.

## Result detail

For v2:
- display "Purchase Propensity" / calibrated probability bucket;
- do not display legacy "Match Strength" as the primary selection description;
- show calibrated probability summary sourced from the promoted calibration/scores;
- if raw score is shown, label it separately.

For v1:
- preserve current legacy labels and raw-score semantics.

## Export

Decide whether downstream export needs calibrated probability. If exposed, use an explicit field name. Do not silently rename existing frozen export columns.

## Migration/backward compatibility

No rewrite of historical snapshots.
Readers must understand both membership versions.

## Tests

- v1 snapshot remains readable and unchanged;
- v2 snapshot uses explicit calibrated field;
- cache cannot confuse v1/v2;
- Results card distinguishes 0.50 and 0.60 buckets even if both historically map to BROAD;
- score summary for v2 reflects calibrated probability, not raw scoring_run min/max/mean;
- old downloads remain byte/schema compatible where frozen.

## Evidence

`docs/evidence/recovery_hardening/09_V2_SCORE_SEMANTICS.md`

## Acceptance gate

NO-GO if a single field named `propensity_score` still means raw score in v1 and calibrated probability in v2 without a versioned schema boundary.

---

# Prompt 10 — Targeting catalog lifecycle, current-version promotion, and option-load hardening


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

Keep the performance benefits of the checksum-keyed catalog while fixing current/stale lifecycle edge cases.

## Inspect at minimum

- `app/services/targeting_option_catalog_service.py`
- `app/services/data_import_service.py`
- normalized product catalog
- options endpoint
- search submission normalization
- catalog/version tests

## Reproduce edge case

A source checksum/catalog version seen previously can become stale after another import, then become authoritative again if the source reverts to that exact checksum.

Current behavior to verify:
- existing row found by version;
- returned immediately;
- `is_current` may remain false.

## Required behavior

`get_or_build_targeting_catalog()` must atomically ensure that the catalog corresponding to the latest authoritative checksums is current, even when the catalog row already exists.

At most one catalog version should be current according to repository policy.

Re-promotion must not unnecessarily rebuild large option payloads if the exact catalog exists and is valid.

Normalize product catalog lifecycle consistently with parent catalog.

## Additional checks

- startup reconciliation repairs a missed post-import catalog refresh;
- options endpoint never returns catalog X as current while submission rejects X because DB still marks it stale;
- historical result rendering can still resolve labels using historical/fallback data;
- no repeated 5M scan on warm option loads.

## Tests

Include:
A -> B -> A checksum lifecycle;
concurrent startup/import refresh;
existing catalog with missing product rows;
warm options performance path;
submission using the returned current version.

## Evidence

`docs/evidence/recovery_hardening/10_CATALOG_LIFECYCLE.md`

## Acceptance gate

GO only if the version returned by the live options endpoint is accepted as current by live submission/preflight validation.

---

# Prompt 11 — Strengthen calibration methodology and leakage controls


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

Prove model training, calibration fitting, and calibration evaluation are separated by an appropriate campaign/group boundary, not merely by customer rows.

## Inspect at minimum

- model training cohort/split code;
- `app/ml/preprocessing.py`
- `app/services/training_cohort_service.py`
- `app/services/propensity_calibration_service.py`
- historical campaign/customer observation lineage
- model-run persisted split metadata
- calibration artifact schema
- tests for deterministic calibration

## First: produce a leakage audit

Document:
- unit of observation;
- customer-to-campaign multiplicity;
- current model train/validation split method;
- how calibration group IDs are assigned;
- whether one campaign can contribute customers to both model training and calibration/test;
- effect of `MIN(campaign_id)` for customers in multiple campaigns.

Do not change methodology until the audit is explicit.

## Required improved split

Design a deterministic grouped strategy that keeps campaign/group leakage bounded according to the actual data model.

A preferred conceptual structure:
- model-training campaign groups;
- calibration-fit campaign groups;
- final calibration-evaluation campaign groups;

with zero overlap where statistically feasible.

If the available dataset is too small to support a three-way campaign-group split with both outcome classes, fail transparently and document the insufficiency rather than relaxing the rule silently.

Persist split lineage:
- group IDs/hash;
- counts;
- seed;
- strategy version;
- overlap counts;
- class balance.

## Calibration selection

Continue evaluating sigmoid/isotonic or justified alternatives on a genuine held-out evaluation partition.

Promotion metrics must be calculated on data not used to fit that calibrator.

Do not optimize and report performance on the same records.

## Tests

- deterministic split for fixed seed/data;
- zero group overlap;
- both classes required in each needed subset;
- multi-campaign customer handling is deterministic and documented;
- candidate selection metric uses held-out evaluation only;
- impossible split fails safely.

## Evidence

`docs/evidence/recovery_hardening/11_CALIBRATION_ISOLATION.md`

Include old-vs-new methodology, not just passing tests.

## Acceptance gate

GO only when the promoted calibration's reported evaluation metrics are based on a genuinely held-out grouped evaluation set.

---

# Prompt 12 — Correct feedback learning semantics, PSI comparison, and challenger governance


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

Make the feedback loop statistically and operationally honest.

## Inspect at minimum

- `app/services/phase11_feedback_service.py`
- `app/jobs/feedback_retraining_worker.py`
- calibration publication
- model training job infrastructure
- feedback/retraining DB schema
- UI labels/docs

## Workstream A — rename semantics

If the worker only fits a new calibration over existing raw scores, rename public/internal concepts from "retraining" to **recalibration** unless a true model retraining path is implemented.

Preserve migration/backward compatibility for stored table/column names where renaming them would be destructive; business/API labels should be truthful.

## Workstream B — PSI

Audit current PSI:
feedback-selected audience score distribution versus full 5M base distribution.

Determine whether this is a valid like-for-like drift test. If not, replace it with a comparison whose populations have the same selection basis.

Possible safe designs:
- score distribution of a current comparable scoring population versus reference scoring population;
- same campaign-selection policy across time;
- use another drift metric only if justified.

Persist enough reference lineage to reproduce the drift calculation.

Do not use a metric simply because it produces a trigger.

## Workstream C — adaptive gate

Keep governed minimum label/class/run floors, but make the "new information" rule statistically coherent.

Avoid creating a new WAITING decision row on every tiny feedback batch if that causes unbounded noisy history; if needed, design bounded event/state semantics while preserving auditability.

## Workstream D — true model learning boundary

Produce a documented distinction between:
1. recalibration of an existing scoring model;
2. true model retraining using new feedback.

If true retraining is implemented in this prompt, it must:
- create a new model_run;
- follow frozen feature/governance contracts;
- evaluate challenger vs incumbent;
- rescore the current demographic universe;
- create new generation lineage;
- require promotion gates.

If that is too large/risky for this step, do not fake it. Create an explicit future-work contract and keep automatic feedback behavior named recalibration.

## Tests

- PSI/reference population correctness;
- deterministic drift calculation;
- recalibration promotion/non-regression;
- non-finite metrics rejected;
- startup recovery;
- public labels do not claim model retraining if none occurred.

## Evidence

`docs/evidence/recovery_hardening/12_FEEDBACK_LEARNING.md`

## Acceptance gate

GO when automatic feedback behavior is statistically defensible and named truthfully.

---

# Prompt 13 — Zero-customer blocker: root-cause package and business-policy decision gate


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

Resolve the zero-customer problem scientifically without silently weakening the approved targeting contract.

## Current condition to re-verify

Prior evidence reported calibrated purchase probabilities approximately:
- min 0.065;
- max 0.079;

while approved v2 buckets start at 0.50.

Recompute this from the canonical database/current promoted calibration. Do not trust stale evidence.

## Required diagnostics

Produce:
- calibrated probability quantiles: min, p1, p5, p10, p25, p50, p75, p90, p95, p99, max;
- raw-score quantiles;
- purchase/outcome base rate used for calibration;
- reliability table/calibration curve data;
- bucket population counts for existing approved buckets;
- top-percentile population sizes;
- expected precision/lift where statistically supported;
- model ROC-AUC/AP/lift with proper held-out lineage from Prompt 11;
- whether a 50% individual purchase probability is statistically plausible in this problem.

## Decision options

Create:
`docs/evidence/recovery_hardening/13_SELECTION_POLICY_DECISION.md`

Present at least these policy options without implementing them silently:

### Option A — keep 0.50+ absolute-probability buckets
Implication: current system remains NO-GO until model/data produce such probabilities.

### Option B — versioned lower absolute-probability buckets
Example ranges must be derived from observed distribution and business interpretation, not invented for demo convenience.

### Option C — versioned percentile/top-X% targeting
Selection based on relative ranking while still displaying calibrated purchase probability.

### Option D — versioned lift/risk-band targeting
Only if statistically justified and understandable to business users.

For each option document:
- semantics;
- risks;
- required UI changes;
- migration/contract changes;
- demo implications;
- whether exact 10K qualification is feasible without filter widening.

## No-shortcut rule

Do not:
- alter v2 thresholds;
- relabel percentiles as probabilities;
- multiply probabilities;
- change calibration merely to force higher numeric values;
- fabricate feedback;
- lower the 10K qualification minimum;
- submit nonqualifying searches.

## Output

This prompt is a mandatory human/business decision gate.

End by stating which implementation prompt should be run next:
- **14A** if the decision is to keep current absolute-probability contract and improve data/model only;
- **14B** if explicit approval is given for a new versioned percentile/probability selection contract.

Do not choose on behalf of the operator.

---

# Prompt 14A — Conditional path: keep 0.50+ absolute purchase-probability contract


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


## Run only if

The operator/business explicitly chooses to retain the current absolute-probability bucket semantics.

## Objective

Improve model/data quality through governed methods without altering selection thresholds or calibration truth.

## Required work

1. Audit historical outcome quality, attribution definition, leakage, class balance, campaign coverage, and recency.
2. Determine whether the current feature set can plausibly discriminate sufficiently.
3. Evaluate legitimate model improvements compatible with the POC governance:
   - feature engineering from existing allowed fields;
   - campaign-aware training;
   - class/PU-learning improvements;
   - challenger models already allowed by repository policy;
   - better historical labels or additional governed outcome data.
4. Use proper train/calibration/test separation from Prompt 11.
5. Promote only if challenger gates are met.
6. Rescore full current demographic universe.
7. publish a new calibration and attestation.
8. rerun exact bucket distribution.

## Hard rule

If calibrated probabilities still do not enter approved buckets, report NO-GO. Do not distort the calibration to make numbers look larger.

## Tests/evidence

Create:
`docs/evidence/recovery_hardening/14A_MODEL_IMPROVEMENT.md`

Include incumbent vs challenger held-out metrics, calibration, probability distribution, and whether 10K+ exact scenarios are possible.

## Acceptance gate

GO only if the improved **honestly calibrated** model creates business-approved qualifying populations.

---

# Prompt 14B — Conditional path: implement an explicitly approved versioned selection contract v3


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


## Run only if

The operator/business has explicitly approved one of the alternatives documented in Prompt 13.

Record the approval/selected semantics in:
`docs/evidence/recovery_hardening/13_SELECTION_POLICY_DECISION.md`

Do not run this prompt without that decision.

## Objective

Implement the approved new targeting semantics as a **new versioned contract** while preserving v1 and v2 behavior and historical artifacts.

## Required architecture

Add:
- selection contract version 3;
- explicit schema/API fields whose names match the approved semantics;
- deterministic bucket/range/percentile definitions;
- exact preflight implementation;
- materialization implementation using the same shared predicate/selection layer;
- result cache identity updates;
- snapshot/membership contract update if field semantics change;
- Results/Detail labels;
- API/OpenAPI docs;
- scenario preflight support.

## Compatibility

- v1 raw-score searches unchanged;
- v2 absolute calibrated-probability searches unchanged;
- v3 explicit new semantics only for new requests;
- no automatic migration of historical runs.

## Tests

Boundary tests, preflight/materialization parity, history reopening, result-cache separation, UI labels, export compatibility, and exact scenario qualification.

## Evidence

`docs/evidence/recovery_hardening/14B_SELECTION_V3.md`

## Acceptance gate

GO only if a business user cannot confuse v3 semantics with absolute purchase probability and all historical versions remain interpretable.

---

# Prompt 15 — Fault injection and crash/restart certification


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

Prove the recovered runtime survives the failures that originally caused stuck 3%, stale retries, duplicate work, and unsafe terminal transitions.

## Build a deterministic fault matrix

Inject failures at least at:

1. after search row creation but before scheduling;
2. after attempt lease claim;
3. during direct-reuse validation;
4. while waiting for heavy slot;
5. during Phase 10 analysis/model/scoring/rank stages;
6. after Phase 10 becomes READY but before Phase 11 observes it;
7. during cache lookup;
8. during member selection;
9. during snapshot file write;
10. after file fsync but before DB publication;
11. after snapshot registration but before completion;
12. during export;
13. during feedback ingestion;
14. during recalibration publication;
15. process restart while attempts are QUEUED/PROCESSING;
16. stale worker resumes after retry creates a new attempt.

## Required guarantees

- no orphan active run without recoverable durable state;
- no two active attempts for one run;
- no stale worker writes;
- no duplicate immutable snapshot for one exact cache identity except safely reconciled race;
- no partial published file treated as current;
- no retry loop;
- no loss of idempotency;
- restart reconciliation is bounded;
- safe business error messages;
- logs contain technical context without PII/secrets.

## Tests

Prefer deterministic synchronization barriers/events over sleeps.

Run concurrency tests repeatedly enough to expose races.

Include SQLite lock/contention behavior appropriate for the POC.

## Evidence

`docs/evidence/recovery_hardening/15_FAULT_MATRIX.md`

Include a matrix:
fault point -> durable state -> startup/retry action -> expected terminal state -> test.

## Acceptance gate

NO-GO if any injected crash can cause an old attempt to mutate a newer attempt or produce an unowned permanent PROCESSING state.

---

# Prompt 16 — Canonical 5M performance and non-mutating certification


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

Certify performance on the canonical 5M database after correctness fixes, without contaminating business evidence.

## Measure separately

### Warm read paths
- targeting options;
- Results history 20;
- status/detail;
- exact preflight cached;
- exact result reuse lookup;
- snapshot validation.

### Write/compute paths
Where business qualification permits:
- search creation acknowledgement;
- coordinator scheduling latency;
- exact-result reuse completion;
- new materialization for a qualifying controlled scenario;
- feedback ingestion;
- calibration/preflight refresh.

If a path cannot be ethically executed because no scenario qualifies, state **NOT EXECUTED**. Do not substitute a different metric and call it certified.

## Budgets

Use existing repository budgets where already frozen. If no budget exists, record measurement without inventing a pass threshold.

## Query plans

Capture `EXPLAIN QUERY PLAN` for:
- calibrated bucket count;
- preflight intersection filters;
- queue positions;
- history;
- normalized product lookup;
- current catalog version;
- snapshot/cache lookup.

Check for N+1 regressions.

## Resource behavior

Record:
- elapsed time;
- peak memory if practical;
- DB size changes;
- lock errors/timeouts;
- number of queries for history/options where tests instrument them.

## Evidence

Update/create:
`docs/evidence/recovery_hardening/16_CANONICAL_PERFORMANCE.json`
`docs/evidence/recovery_hardening/16_CANONICAL_PERFORMANCE.md`

Do not overwrite older historical evidence without preserving its baseline.

## Acceptance gate

GO only for operations actually executed and within frozen budgets. Keep unexecuted operations explicitly uncertified.

---

# Prompt 17 — Revalidate all 20 scenarios and run only genuinely qualified searches


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

Produce truthful demo readiness after runtime/model/selection-contract fixes.

## Inputs

Use the repository's canonical 20-scenario pack unchanged.

Do not alter:
- age;
- income;
- states;
- education;
- employment;
- family;
- resident-type filters;
- scenario IDs/names;
- 10,000 exact-customer qualification rule.

Use the approved selection contract resulting from Prompt 13/14.

## Step A — exact preflight

For each scenario record:
- scenario ID/name;
- normalized criteria hash;
- catalog version;
- generation ID;
- scoring run ID;
- calibration artifact ID if applicable;
- selection contract version;
- demographic count;
- selection/bucket population;
- exact intersection;
- demo_ready;
- safe currentness state.

Qualification requires:
- current/verified lineage;
- exact count >= 10,000;
- no widened filters.

## Step B — controlled real runs

Submit only qualifying scenarios.

For each real run capture:
- run ID;
- attempt;
- creation acknowledgement time;
- queue time;
- processing time;
- result source;
- progress stage sequence;
- ETA behavior if available;
- exact selected count;
- snapshot ID/checksum;
- preflight count vs materialized count;
- reuse/build explanation.

Any mismatch between exact preflight and actual ALL_MATCHING result is a blocker.

## Step C — TOP_N demonstration

Only after showing the full exact qualifying count, optionally rerun the same scenario under approved `TOP_N=250` semantics to demonstrate activation capacity. Keep this a separate run/contract.

## Step D — demo order

Recommend a live demo order only from scenarios that actually qualified. Do not preserve an old preferred order if some are not qualified.

## Evidence

`docs/evidence/recovery_hardening/17_20_SCENARIO_READINESS.json`
`docs/evidence/recovery_hardening/17_20_SCENARIO_READINESS.md`

## Acceptance gate

GO for demo only if at least the desired set of scenarios qualify and their actual materialized counts match exact preflight.

---

# Prompt 18 — Documentation, evidence truthfulness, and repository housekeeping


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

Remove stale claims and make repository documentation accurately describe the code being certified.

## Required fixes

Audit repository-wide for stale:
- schema versions;
- baseline SHAs;
- test counts;
- CI status;
- "all defects addressed" claims;
- selection semantics;
- probability vs raw-score terminology;
- retraining vs recalibration terminology;
- performance certification claims;
- 2c7f63 references presented as current.

At minimum inspect:
- `README.md`
- `docs/evidence/demo_readiness/*`
- Phase 10/11 evidence
- prompt-pack baseline docs
- OpenAPI/app description
- architecture/current-version sections.

## Evidence policy

Historical evidence files may remain historical if clearly labeled with their original SHA/date.

Do not rewrite a historical report to pretend it was produced at the latest SHA.

Create a new current release evidence index:
`docs/evidence/recovery_hardening/README.md`

It should map each Prompt 00-19 to:
- evidence file;
- tested SHA;
- status;
- remaining limitations.

## Housekeeping

Check:
- accidental output artifacts;
- local DBs/large files;
- ignored canonical outputs referenced as if committed;
- duplicate stale prompt packs;
- dead temporary code;
- TODO/FIXME related to this recovery;
- generated browser screenshots/evidence naming;
- repository hygiene CI.

Do not delete historical evidence or prompt packs just to make the tree smaller unless clearly redundant and safe.

## Acceptance gate

GO only if a new engineer can read README/current evidence and correctly understand:
- schema version;
- selection versions;
- what is certified;
- what is still a limitation;
- exact tested SHA.

---

# Prompt 19 — Full regression, CI release gate, and final certification


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

Perform the final release-quality audit. This prompt must not paper over failures.

## Precondition

Prompts 01-18 applicable to the chosen business policy have been completed.

## Required validation

### Static/format
- Python compile;
- focused + repository lint according to existing policy;
- JS syntax/lint;
- `git diff --check`;
- schema migration validation.

### Tests
Run the broadest bounded repository test suite practical under the project's frozen CI policy.

Must include:
- migrations/imports;
- Phase 9/10 compatibility;
- Phase 11 registry/smart reuse;
- retry/fencing;
- restart/fault matrix;
- API contracts;
- browser/mobile;
- feedback/recalibration;
- preflight parity;
- selection v1/v2 and v3 if implemented;
- export;
- performance gates that are non-destructive or explicitly authorized.

Do not substitute a collection of focused tests for repository CI while calling it "full CI."

### Exact-SHA CI

Ensure GitHub CI (or the repository's canonical CI environment) is green at the exact candidate SHA.

Record run ID, jobs, conclusions, and SHA matching.

### Database integrity

On an appropriate canonical copy:
- `PRAGMA integrity_check`;
- foreign key check;
- active orphan searches/jobs;
- duplicate active attempts;
- attempt/runtime mismatch;
- stale current catalogs;
- invalid current attestations;
- multiple promoted calibrations where prohibited;
- preflight cache currentness consistency;
- snapshot/currentness consistency.

### Security/data safety

Confirm:
- no PII in analytical snapshot membership unless explicitly governed;
- safe error responses;
- no lease tokens in public response/log evidence;
- path traversal defenses;
- CSV formula mitigation still intact;
- feedback upload bounds.

## Final report

Create:
`docs/evidence/recovery_hardening/19_FINAL_RELEASE_GATE.md`

Include a table for every previously identified issue:
- issue;
- status FIXED / PARTIAL / BLOCKED / ACCEPTED LIMITATION;
- code/evidence;
- tests;
- residual risk.

Also produce:
`docs/evidence/recovery_hardening/19_FINAL_RELEASE_GATE.json`

## Decision rules

Return **GO** only if:
- exact candidate CI is green;
- no correctness blocker remains;
- currentness/fencing/retry invariants hold;
- business selection policy is explicitly approved;
- demo claims are supported by actual current evidence.

If model/business data still prevents qualifying scenarios, runtime may be technically releasable but **demo-readiness must remain NO-GO**. State these separately.

Never convert a limitation into a pass merely because it is inconvenient.
