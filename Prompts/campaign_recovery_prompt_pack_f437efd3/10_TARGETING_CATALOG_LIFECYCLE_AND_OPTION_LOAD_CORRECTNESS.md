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
