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
