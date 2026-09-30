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
