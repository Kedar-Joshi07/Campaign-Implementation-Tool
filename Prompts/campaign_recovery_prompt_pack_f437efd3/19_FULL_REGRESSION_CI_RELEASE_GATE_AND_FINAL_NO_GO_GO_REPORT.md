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
