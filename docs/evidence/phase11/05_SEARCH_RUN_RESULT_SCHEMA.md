# Phase 11 Step 5 — Search Run and Result Snapshot Registry

Date: 2026-09-16

Prompt: `Prompts/phase11_business_workflow_omnichannel_smart_reuse_prompt_pack/05_STEP_05_PHASE11_SCHEMA_SEARCH_RUN_AND_RESULT_SNAPSHOT_REGISTRY.md`

Frozen Phase 10 baseline: `881b5a652e869af1415547de452b9cccd2c18293`.

## Result

`PASS_STEP_05_SEARCH_RUN_RESULT_SCHEMA`

Schema 17 adds three separate registries: business submissions, reusable immutable result-snapshot metadata, and search-result export audit. The existing Campaign tables, finalization rules, and export audit semantics are unchanged. Repository methods provide transactional persistence only; no frontend SQL, orchestration, membership materialization, or download engine is introduced in this step.

The prompt references schema 15 as the upgrade baseline. Step 4 already introduced schema 16, so Step 5 correctly extends the sequential 15→16→17 migration chain instead of replacing or bypassing Step 4. Both upgrade paths and migration rollback are tested.

## Implementation inventory

| Artifact | Responsibility |
|---|---|
| `app/database/phase11_schema.py` | Exact column authorities, three table definitions, ten indexes, identity/terminal/history/lineage triggers |
| `app/database/schema.py` | Version 17, migration registration, expected-table inventory, required-index integration, re-exported Phase 11 column authorities |
| `app/services/phase11_result_contracts.py` | Versioned status/source/currentness/storage/membership contracts and bounded finite, canonical, contact-PII-free metadata JSON/hash validation |
| `app/repositories/campaign_result_registry_repository.py` | Distinct submission inserts; processing/completion/failure; snapshot registration/lookup/currentness; keyset history; export start/finish/audit reads |
| `tests/test_phase11_search_result_registry.py` | Registry, privacy, immutability, state, lineage, rollback, shared-snapshot, history, count, checksum, and upgrade tests |
| Existing Phase 9/10/11 schema tests | Current schema expectations advance to 17 while checking original table/feature/source contracts |
| `README.md` | Current schema and accurate registry-versus-later-integration boundary |

Contract versions: search run 1, result membership 1, result export 1. No dependency or frontend changes were needed.

## A. campaign_search_runs

Exact ordered columns:

`search_run_id, search_run_contract_version, campaign_name, description, planned_launch_date, targeting_context_id, modeling_context_sha256, targeting_criteria_json, targeting_criteria_sha256, filter_branches_json, filter_branches_sha256, selection_mode, target_count, delivery_channel, export_profile, generation_id, analysis_run_id, model_run_id, scoring_run_id, result_snapshot_id, result_source, status, selected_count, created_at, started_at, completed_at, processing_seconds, created_by_user_id, safe_error_message`.

Every call to `create_search_run` inserts a new record. There is intentionally no uniqueness constraint on submission criteria, campaign name, context, or snapshot reference. Two identical requests, or requests with changed campaign/delivery metadata, can share one snapshot while retaining separate search-run IDs and lineage.

Statuses are exactly `QUEUED`, `PROCESSING`, `COMPLETED`, `BLOCKED`, `FAILED`. Repository completion requires PROCESSING; failure/blocking can terminate queued or processing runs. Completed/blocked/failed records cannot be mutated or deleted. Submitted business fields, criteria/branch JSON and hashes, selection, channel/profile, creation/start timestamps, and nullable future user reference are immutable even while processing.

The three result sources are `EXACT_RESULT_REUSE`, `INTELLIGENCE_REUSE`, `NEW_INTELLIGENCE_BUILD`. They are persisted provenance labels, not instructions to launch work. Completed runs require snapshot/generation/analysis/model/scoring references, a valid source, reconciled selected count, completion time, and elapsed processing seconds. Processing seconds measure elapsed submission-to-completion time, including queue time; they are not a CPU timing claim.

Failure/block messages are fixed safe text; raw exceptions, file paths, or contact identifiers are not accepted as error-message inputs. Date, timestamp, positive-ID, count, bounded-text, channel/profile, selection, and JSON-shape validation occurs before writes. ALL_MATCHING has null target count; TOP_N requires a positive integer count. Criteria selection cannot disagree with the separately recorded selection.

Canonical JSON uses sorted keys, compact separators, ASCII escaping, and finite values. Stored hashes cover the entire canonical payload. Branches must contain 1–49 objects. Nested contact/membership identity keys are rejected; channel/profile changes do not alter criteria/branch hashes. Exact Phase 9 normalization/mapping and cache-key composition remain Step 9 responsibilities rather than being duplicated here.

## B. campaign_result_snapshots

Exact ordered columns:

`result_snapshot_id, result_membership_contract_version, generation_id, targeting_criteria_sha256, filter_branches_sha256, selection_mode, target_count, result_cache_key_sha256, resolved_count, storage_format, storage_uri, snapshot_sha256, created_at, last_verified_at, last_used_at, currentness_state`.

The unique lowercase 64-character cache-key SHA supplies the exact-key lookup index. A duplicate registration is rejected rather than silently modifying or duplicating snapshot identity. Zero-count snapshots are valid; TOP_N resolved counts cannot exceed the requested count.

Snapshot identity, generation, selection, hashes, artifact location/format, resolved count, and creation time are immutable. Only verification/use timestamps and currentness state can change. The registry cannot be deleted. Currentness vocabulary is CURRENT, STALE, UNVERIFIED.

No contact PII or person membership is stored in snapshot metadata. The future membership contract permits only `person_id, propensity_score, percentile_bucket, decile, rank_band`. Registry URIs must be portable `artifacts/results/result_snapshot_<digits>/members.<extension>` paths, preventing absolute paths, traversal, and contact-bearing filenames. Supported registry format descriptors are CSV_GZIP, JSONL_GZIP, PARQUET; this does not add Parquet dependencies or choose the Step 11 materialization format.

Repository registration accepts an already validated artifact descriptor. It does not write, inspect, checksum, or certify a file. That is explicitly the Step 11 service boundary, with Step 9 performing live exact compatibility/reuse validation. A metadata cache-key lookup alone is never represented as a successful cache hit.

## C. campaign_result_export_events

Exact ordered columns:

`export_event_id, search_run_id, snapshot_id, export_contract_version, export_profile, profile_version, status, selected_count, deliverable_count, undeliverable_count, row_count, csv_sha256, started_at, completed_at, currentness_state, safe_error_message`.

A new table preserves existing campaign_id/finalization semantics. Events require a completed search, its exact snapshot reference and selected count, and a source-supported profile from the backend registry. A download profile is recorded separately from membership; changing it does not change analytical identity.

Statuses are RUNNING, COMPLETED, FAILED, ABORTED. SQL and repository guards require:

- selected = deliverable + undeliverable;
- emitted rows cannot exceed deliverable count;
- COMPLETED rows = deliverable, checksum present, completion currentness CURRENT, no error;
- terminal timestamps and safe failure/abort messages;
- terminal audit immutability and no audit deletion.

Creation/completion reject stale snapshot or generation lifecycle metadata. Failed/aborted events can record partial counts without claiming success. Full live provenance checks, streaming, CSV safety, disconnect handling, and post-artifact validation are composed in Step 13, not claimed as already implemented here.

## Referential integrity and indexes

RESTRICT foreign keys preserve references to context, generation, snapshot, analysis, model, scoring, and search identity. Search-to-snapshot guard triggers verify generation, modeling-context hash, criteria/branch hashes, selection/target, resolved count, and generation-owned analysis/model/scoring IDs. A mismatch aborts the write, rolling back both search completion and snapshot usage touch.

SQL triggers protect immutable identities and terminal history. Repository publication/completion operations use BEGIN IMMEDIATE transactions; no frontend controls or constants own SQL. Snapshot/export readiness checks are bounded metadata checks; they do not replace Phase 10 live currentness validation.

Ten new explicit indexes cover newest-first searches, search status/generation/snapshot/context, snapshots by generation/creation time, and export history by search/snapshot/status. The UNIQUE cache-key constraint additionally supplies its lookup index. History ordering uses created_at DESC then ID DESC, with matching timestamp/ID keyset cursors rather than assuming ID order equals timestamp order.

## Validation

Initial targeted suite:

`pytest -q tests/test_phase11_search_result_registry.py tests/test_phase11_contactability_identifier_extension.py tests/test_database_schema.py tests/test_phase9_schema.py tests/test_phase10_schema_registry_repository.py`

**81 passed in 162.28s.**

Final checkpoint, including the added history-cursor case:

`pytest -q tests/test_phase11_search_result_registry.py tests/test_database_schema.py tests/test_phase3_schema.py tests/test_phase4_schema_jobs.py tests/test_phase5_schema.py tests/test_phase6_schema.py tests/test_phase9_schema.py tests/test_phase10_schema_registry_repository.py tests/test_data_api.py tests/test_health.py tests/test_phase11_contactability_identifier_extension.py tests/test_phase11_omnichannel_profile_contracts.py`

**145 passed in 253.88s.** These overlap the initial suite; they are not 226 unique tests. All cases ran sequentially, including repeated submission tests (no parallel agents, pools, or prompt processes).

`python -m compileall -q app scripts tests`: passed.

Text-file `git diff --check` passed; new untracked registry/test/evidence files were also checked for trailing whitespace with no matches. Binary gzip inputs were excluded from the whitespace check. Normal Windows CRLF-to-LF notices are not errors.

Independent SHA-256 checks confirm the feature file remains `b3e3f382080b480751080da4b1a03c9fdb3ed25fc7740e9490723a2c880234be` and the Step 4 canonical gzip remains `27d8e2a978458a095e16fc51a682e1f3373e41b663a4e61defa47e2d1bdf8b1d`. Existing worktree changes from preceding steps were preserved, not staged or reverted.

Coverage includes exact schema/FKs/indexes, direct repeated migration idempotence, 15/16 upgrades, rollback of all schema-17 DDL/version changes, shared immutable snapshots with distinct submissions, all three result-source labels, five search states, selection bounds/empty results, safe terminal failure, JSON privacy/shape/nonfinite rejection, channel/profile validation, cache-key uniqueness, portable artifact paths, terminal/direct-SQL protections, transactional lineage mismatch rollback, stale metadata rejection, export counts/checksum/currentness/abort states, and timestamp-aware bounded history.

This is targeted Step 5 schema/repository validation. It does not claim the later orchestration, artifact materialization, frontend, installed-browser, or full-5M scoring certification has run.

## Local runtime migration evidence

Local schema changed **16→17** only after the test checkpoints passed. Before/after checks verified all 19 legacy table counts and byte-derived hashes of all 15 non-large metadata tables remain identical. Application/schema metadata is excluded from row-hash equality because its version/timestamp necessarily changes. The four large analytical/source tables were checked by counts; the migration contains no DML against them.

Key preserved counts:

| Table | Rows |
|---|---:|
| customers | 125,000 |
| campaign_sales | 570,000 |
| demographics | 5,000,000 |
| propensity_scores | 10,000,000 |
| historical_analysis_runs | 3 |
| model_runs / scoring_runs / jobs | 2 / 2 / 7 |
| data_import_runs | 4 |
| campaigns / campaign_export_events | 4 / 2 |
| campaign_targeting_contexts | 5 |
| saved_audiences / phase9_saved_target_groups | 3 / 2 |

All three new runtime registries have **0 rows**, with no new-table foreign-key issues. **67/67 required indexes** are present. No fake fixture records/artifacts were written to the canonical database. Step 4 canonical source provenance and existing stale-score history are unchanged.

No generation/import, canonical training/scoring/ranking, Campaign mutation, artifact creation, commit, or push ran in Step 5. The only local runtime write was the additive schema migration and creation of its empty registries/indexes/triggers.

## Stop boundary

`STOP_AFTER_STEP_05`

Step 6 and later prompts require the user's next instruction. Step 9 supplies exact orchestration/cache validation, Step 11 supplies actual immutable membership artifacts, and Step 13 supplies governed download streaming.
