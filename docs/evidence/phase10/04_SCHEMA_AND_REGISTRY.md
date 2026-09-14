# Phase 10 Schema, Registry, and Repositories

Generated: 2026-09-14

Prompt: `Prompts/phase10_campaign_intelligence_orchestration_prompt_pack/04_STEP_04_PHASE10_SCHEMA_REGISTRY_AND_REPOSITORIES.md`

## Step result

`PASS_STEP_04_SCHEMA_REGISTRY_AND_REPOSITORIES`

SQLite schema version 15 adds three focused Phase 10 persistence tables and a
transactional repository. Migration is additive and idempotent. No existing
analytical table is rebuilt, rewritten, truncated, or deleted.

## Schema version and tables

| Item | Result |
|---|---|
| Previous Phase 9 schema | v14 |
| Current schema | v15 |
| Migration | `_migrate_to_version_15` |
| Runtime database | `data/campaign_poc.db`, verified at v15 |

### `phase10_intelligence_generations`

The immutable READY registry stores:

- generation, compatibility, historical-window, multi-product,
  training-eligibility, automated-training, lifecycle, rank, and analytics
  contract/policy versions;
- exact intelligence-key, Modeling Context, historical-filter, feature,
  artifact, and score-semantics SHA-256 identities;
- canonical valid JSON for Modeling Context, historical filters, and score
  semantics;
- exact customer, campaign-sales, and demographic import IDs/checksums;
- exact analysis, model, and scoring IDs;
- READY status, lifecycle state, creation, verification, and usage timestamps.

All analytical/import IDs are mandatory positive foreign keys. Therefore an
incomplete row cannot be registered as READY. The repository additionally
verifies completed analysis -> model -> scoring linkage, exact source import
identity, model/scoring artifact identity, and scoring feature/model-role
identity before insertion or verification.

### `phase10_orchestration_runs`

The durable workflow table stores exact context/intelligence hashes, Phase 9
targeting context, status, technical stage, monotonic progress, business and
technical messages, canonical reuse-plan JSON, analytical/generation/child-job
IDs, lifecycle timestamps, and a bounded safe error.

Allowed statuses are `QUEUED`, `RUNNING`, `READY`, `BLOCKED`, and `FAILED`.
Cross-column constraints enforce:

- QUEUED = progress 0 with no start/completion timestamp;
- RUNNING = progress 1..99 with a start and no completion timestamp;
- READY = progress 100, complete timestamps, and complete
  generation/analysis/model/scoring IDs;
- BLOCKED/FAILED = terminal timestamp and progress below 100; and
- FAILED requires a safe error message.

A partial unique index on `intelligence_key_sha256` for QUEUED/RUNNING rows
prevents duplicate exact active orchestration at the database boundary.

### `phase10_context_bindings`

One current row per Phase 9 `targeting_context_id` maps the business context to
its Modeling Context SHA, orchestration, optional generation, binding status,
and timestamps. Multiple targeting contexts can reference the same verified
generation. READY bindings require a generation in both schema and repository
validation.

## Indexes

Schema v15 adds indexed lookup paths for:

- generation Modeling Context and intelligence key;
- generation lifecycle state;
- analysis, model, and scoring IDs;
- orchestration Modeling Context and intelligence key;
- unique active orchestration by intelligence key;
- orchestration targeting context; and
- binding generation, orchestration, and Modeling Context.

All indexes are included in the central required-index registry and are created
idempotently by migration and index initialization.

Generation intelligence keys are intentionally non-unique because immutable
SUPERSEDED/STALE history may coexist with a replacement generation. Lookup is
deterministic and lifecycle-aware. Uniqueness is enforced only for active
orchestration, where duplicate work would be unsafe.

## Repository behavior

`app/repositories/phase10_intelligence_repository.py` provides:

- READY generation insert, exact-key/context lookup, fetch, canonical
  payload/lineage verification, verification touch, usage touch, lifecycle
  update, and lifecycle listing;
- atomic create-or-return-existing active orchestration;
- atomic QUEUED -> RUNNING, monotonic RUNNING stage updates, RUNNING -> READY,
  and active -> BLOCKED/FAILED transitions;
- immutable recorded analytical IDs during progress/READY transitions;
- context binding upsert/fetch/touch with cross-record Modeling Context and
  READY-generation alignment;
- no-PII generation reference counts for bindings, active orchestration, Saved
  Audiences, Phase 9 Saved Target Groups, Campaigns, and export events.

Input validation requires positive IDs, bounded nonblank text, valid lowercase-
normalized hexadecimal SHA-256 values, canonical finite JSON objects, and valid
states. JSON containing contact/identity keys such as `person_id`,
`customer_id`, name, address, phone, or email is rejected at the repository
boundary.

The repository performs state-sensitive writes inside immediate transactions.
Progress cannot decrease, terminal rows cannot transition again, and an
already-recorded analytical ID cannot be silently replaced.

## Phase 9 upgrade and preservation proof

The focused migration test constructs an actual v14 schema with a preservation
sentinel and a Phase 9 targeting-context row, upgrades twice, and proves:

- schema ends at v15;
- the sentinel and Phase 9 row remain unchanged;
- all three Phase 10 tables exist and remain empty; and
- a forced v15 migration failure rolls back both its table creation and schema
  version, leaving the database at v14.

The project runtime database was initialized twice at v15 and verified with
zero foreign-key violations. Its Phase 10 tables are empty, as expected before
orchestration begins. Legacy counts before and after the idempotency check were
unchanged:

| Table | Rows |
|---|---:|
| `data_import_runs` | 3 |
| `customers` | 125,000 |
| `campaign_sales` | 570,000 |
| `demographics` | 5,000,000 |
| `historical_analysis_runs` | 2 |
| `model_runs` | 2 |
| `jobs` | 7 |
| `scoring_runs` | 2 |
| `propensity_scores` | 10,000,000 |
| `audience_rank_boundaries` | 200 |
| `saved_audiences` | 3 |
| `audience_analytics_snapshots` | 2 |
| `campaigns` | 4 |
| `campaign_export_events` | 2 |
| `campaign_targeting_contexts` | 4 |
| `phase9_saved_target_groups` | 2 |
| `phase10_intelligence_generations` | 0 |
| `phase10_orchestration_runs` | 0 |
| `phase10_context_bindings` | 0 |

## Verification

| Gate | Result |
|---|---|
| Step 4 plus affected schema/Phase 10 suites | PASS - 67 passed in 20.87s |
| Full repository regression | PASS - 604 passed in 555.15s |
| Fresh v15 exact tables/columns/indexes | PASS |
| v14 -> v15 additive/idempotent upgrade | PASS |
| Forced migration rollback | PASS |
| Repository constraint/state/lineage tests | PASS |
| Runtime v15 initialization twice | PASS |
| Runtime `PRAGMA foreign_key_check` | PASS - 0 violations |
| Python compilation | PASS |
| Diff whitespace/error check | PASS |
| Import/training/scoring/rank work | Not run |

## Stop boundary

Step 4 creates persistence and repository primitives only. It does not perform
compatibility selection, training-eligibility policy decisions, model/scoring
resolution, rank preparation, orchestration submission, Phase 9 binding, or UI
work. Those remain assigned to subsequent sequential prompts.

`STOP_AFTER_STEP_04`
