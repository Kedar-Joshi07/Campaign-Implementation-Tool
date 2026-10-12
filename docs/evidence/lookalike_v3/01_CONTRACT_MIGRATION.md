# Stage 14B_01 — v3 contract, registry, API, and schema migration

## Outcome

Stage 14B_01 is **GO** at the uncommitted candidate on `main`. The trusted
starting and current HEAD is
`336875c30fc32b00323d916ecc45b232016168a1`; Stage 14B_00 is the preceding
GO baseline. No commit, push, deployment, training, scoring, scenario run, or
operator-database mutation was performed.

The application now allocates schema 32 once and exposes an explicit,
mode-discriminated v3 product-buyer-similarity contract alongside unchanged
v1/v2 probability behavior. The machine-readable shared interface for later
stages and optional lanes is
[`01_FROZEN_INTERFACE.json`](01_FROZEN_INTERFACE.json).

## Implemented contract

- V3 uses `selection_contract_version="3"`, membership version `3`, score
  semantics `PRODUCT_BUYER_SIMILARITY`, score method
  `BUYER_PROFILE_DISTANCE_V1`, cumulative `>=` selection, and
  `ANY_SELECTED_PRODUCT_MAX_V1`.
- The only accepted similarity minima are `.90`, `.80`, `.70`, `.60`, and
  `.50`; `.70` is the declared new-v3 default. Booleans, integer percentages,
  strings, NaN, infinity, unknown semantics, unknown versions, and mixed
  probability/similarity fields fail closed.
- Omitted-version behavior remains pinned to v1. V2 discrete probability
  buckets, `BROAD -> .60`, explicit `.50`, default `.70`, and all legacy
  response/read contracts remain unchanged.
- Similarity readiness is separate from optional probability readiness.
  Before similarity intelligence exists, preflight returns the exact
  demographic count and `null` similarity counts rather than a false zero.
- A v3 submission transactionally persists a durable queued run and attempt.
  The probability coordinator explicitly cannot claim v3 work. Profile and
  five-million-row build execution belong to Stages 14B_02–14B_05.
- The current v2 business form is deliberately unchanged. The frozen C3
  interface requires an isolated v3 component first and integrates it only in
  Stage 14B_06.

## Schema 32

Migration 32 adds isolated registries for buyer-similarity profiles, profile
artifacts, score generations, generation stages, staged scores, immutable
published scores, v3 result snapshots, and similarity preflight cache. Search
runs and attempts receive discriminator-consistent v3 identity fields.

Database constraints and triggers enforce:

- v1/v2/v3 fields cannot be mixed;
- one published profile exists per exact immutable profile identity;
- generation staging writes require the current owner and fencing token;
- published score rows cannot be updated or deleted; and
- attempt creation copies the correct immutable contract identity.

Historical migration SQL was not edited. Existing constrained tables are
rebuilt only by the new migration and retain IDs, foreign keys, indexes,
triggers, rows, and artifact references.

## Migration evidence

| Proof | Result |
|---|---|
| Fresh database to schema 32 | PASS; integrity `ok`, zero FK violations |
| Populated schema-31 v1/v2 fixture to 32 | PASS; IDs, counts, and semantics preserved |
| Repeated initialization | PASS; idempotent |
| Injected migration failure | PASS; schema stayed 31 and no partial v3 publication remained |
| Invalid direct SQL | PASS; mixed modes, publication collision, unfenced staging, and published mutation rejected |
| API migration/compatibility | PASS; explicit v3 works and preserved v1/v2 responses remain green |

The available canonical database is 7,574,577,152 bytes and stored at schema
26. It was opened read-only; it was not migrated or modified. A disposable
copy was attempted through the full 26-to-32 chain, but the older migration-27
full integrity pass exceeded the bounded 15-minute Stage 14B_01 check. The
process was stopped, its transaction had rolled the copy back to schema 26,
and the verified disposable directory was removed.

This report does **not** claim a completed uninterrupted 26-to-32 canonical
copy run. The migration chain is instead supported by two independent proofs:
the previously certified exact canonical 26-to-31 copy migration in
[`13_6_PRE14_STABILIZATION.json`](../recovery_hardening/13_6_PRE14_STABILIZATION.json),
and this stage's populated schema-31-to-32 migration proof. The operator source
remained untouched throughout.

## Verification

| Command/gate | Result |
|---|---|
| `pytest tests/test_lookalike_v3_contract_migration.py tests/test_lookalike_v3_baseline_compatibility.py tests/test_selection_contract_registry.py -q` | 26 passed in 58.63 s |
| `pytest tests/test_phase11_api_backward_compatibility.py tests/test_phase11_search_result_registry.py tests/test_database_schema.py -q` | 97 passed in 383.75 s |
| Corrected focused browser compatibility rerun | 10 passed, 50 deselected; current frontend diff is empty |
| Ruff 0.15.20 over changed Python files | All checks passed |
| `python -m compileall -q app` | PASS |
| JSON parsing and `git diff --check` | PASS |

The initial full browser-module run passed 55 tests and found five assertions
caused by an attempted out-of-scope v3 default-form switch. That change was
fully reverted rather than weakening the existing assertions; all ten affected
tests then passed, and there is no frontend change in this stage.

Acceptance rows A01–A06 remain passed from Stage 14B_00 and were compatibility
regression-checked. A07 (schema/migration) and A08 (mixed-request rejection)
pass in this stage. A09–A45 are owned by later stages and are not claimed here.

## Impact and rollback boundary

Schema changes are additive and isolated under version 32. Historical raw
scores, probability/calibration artifacts, runs, snapshots, exports, and the
20 scenario definitions were neither converted nor reinterpreted. The
canonical source files and operator database were not changed.

The supported application rollback boundary is a pre-migration backup restored
with the schema-31 application before any schema-32 writes. Automatic downgrade
is not supported, and old binaries must not write a schema-32 database.

## Limitations and next stage

This stage freezes and enforces the registry/API/schema contract; it does not
claim learned-profile quality, similarity scoring correctness, full-five-million
readiness, UI integration, export readiness, scenario qualification, demo
readiness, or predictive lift. Those remain separate gates.

The next sequential stage is
`14B_02_PRODUCT_BUYER_COHORTS_AND_SOURCE_ALIGNMENT.md`. It has not been started.
