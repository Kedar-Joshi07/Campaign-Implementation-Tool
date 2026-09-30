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
