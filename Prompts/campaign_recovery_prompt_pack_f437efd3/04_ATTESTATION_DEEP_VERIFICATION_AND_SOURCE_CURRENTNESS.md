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
