# Phase 11 Step 11 — Result Materialization and Immutable Membership Snapshots

## Outcome

Step 11 is implemented with `RESULT_MEMBERSHIP_CONTRACT_VERSION=1` and the
frozen `CSV_GZIP` storage format.

`pyarrow` is absent from the locked application dependencies. Adding it solely
for this POC path would introduce a large compiled dependency and additional
CI/deployment validation. Deterministic compressed CSV provides streaming
publication and validation with the standard library, so Parquet was not added.

The implementation is in
`app/services/phase11_result_snapshot_service.py`. The callable
`ResultSnapshotMaterializer` plugs directly into the Step 9 search orchestrator.
The public API activation seam remains reserved for Step 16.

## Frozen membership contract

The artifact contains exactly these columns, in this order:

1. `person_id`
2. `propensity_score`
3. `percentile_bucket`
4. `decile`
5. `rank_band`

No optional columns were added. In particular, name, email, phone, postal code,
street/address, channel identifiers, and customer identity are absent. The
validator rejects any missing or additional field and verifies score range,
percentile/decile/rank-band consistency, deterministic global rank order, and
duplicate ordering identity.

The member file is deterministic for identical ordered membership:

- fixed column order;
- UTF-8 and LF line endings;
- shortest round-trip float representation;
- gzip `mtime=0` and an empty embedded filename;
- fixed compression level.

Two different snapshot identities containing the same membership produced
byte-identical `members.csv.gz` files and identical SHA-256 values in the
focused test.

## Layout and manifest

Published layout:

```text
artifacts/results/result_snapshot_000001/members.csv.gz
artifacts/results/result_snapshot_000001/manifest.json
```

The canonical JSON manifest records:

- manifest and membership contract versions;
- snapshot ID;
- row count and member-file SHA-256;
- generation, scoring, model, and analysis IDs;
- targeting-criteria, filter-branch, and exact-result-cache hashes;
- selection mode and target count;
- creation timestamp;
- storage format and exact typed schema.

The manifest is checked against immutable registry/search/generation metadata;
it is not trusted merely because it is adjacent to the member file.

## Safe publication sequence

The production publisher performs these operations sequentially:

1. opens a controlled temporary directory beneath `artifacts/results`;
2. streams membership to `members.csv.gz` without a population-sized list;
3. closes gzip/text/file handles and calls file `fsync`;
4. reopens and validates every row, exact schema, count, ordering, and SHA-256;
5. acquires a short SQLite `BEGIN IMMEDIATE` transaction;
6. resolves the next AUTOINCREMENT snapshot identity under that lock;
7. writes and `fsync`s the manifest;
8. atomically renames the complete temporary directory to its final location;
9. validates the published member file and manifest from the final path;
10. inserts the snapshot registry row through the same transaction and commits.

No snapshot registry row exists before final artifact validation. If insertion
or commit fails, the publisher rolls back and safely removes only the exact
artifact directory it published. An expected snapshot-ID assertion prevents
the numeric directory and database identity from diverging.

## Immutability, exact reuse, and repair

An exact current request is validated and reused by the Step 9 engine; it does
not invoke the membership source or create a second artifact. Concurrent exact
publication detects and reuses a valid committed winner under the database
lock.

Registry identity, resolved count, and member SHA remain immutable. A stale,
missing, or corrupt physical artifact may be repaired only when deterministic
regeneration produces the original registered count and SHA. Different
regenerated membership is refused and cannot overwrite the immutable snapshot.
The registry is returned to `CURRENT` only after both files are published.

## Restart and orphan safety

Caught failures remove their own temporary/final artifacts immediately. The
bounded `recover_orphan_result_artifacts` service handles process-crash residue:

- scans at most a caller-bounded number of entries;
- respects a minimum-age threshold so active publishers are not disturbed;
- removes only `.pending_result_*` or `result_snapshot_<digits>` directories;
- never removes a registered snapshot directory;
- accepts only the known member/manifest filenames and rejects symlinks,
  nested directories, or unrecognized files;
- preserves unrelated operator/application directories.

A final directory published immediately before a process crash is also
reconciled under `BEGIN IMMEDIATE` before its numeric identity is reused.

Runtime result artifacts are ignored by Git; `artifacts/results/.gitkeep`
retains the controlled root.

## Validator

`validate_result_snapshot(...)` is the required service validator. It returns a
bounded safe result rather than exposing filesystem/decoder exceptions. It
checks:

- current READY generation and Modeling Context;
- cache key, criteria/branch hashes, selection, contract, and snapshot identity;
- safe portable path and matching numeric directory;
- exact no-PII storage schema;
- every member's analytical values and order;
- decompressed row count;
- compressed file SHA-256;
- complete manifest equality.

The Step 9 `validate_exact_snapshot(...)` boundary now delegates to this stricter
validator, so exact cache hits require both the member artifact and manifest.

## Repository transaction boundary

`CampaignResultRegistryRepository.register_snapshot_in_transaction(...)` is an
additive transaction-owned insertion boundary. Existing
`register_snapshot(...)` behavior remains intact and delegates to it. This lets
the publisher keep path allocation, atomic publication, validation, database
insert, rollback, and orphan cleanup in one controlled sequence without
weakening READY-generation checks or immutable database triggers.

## Validation

All tests used small temporary SQLite databases and temporary artifact roots.
No canonical result snapshot or 5M membership scan was produced.

| Suite | Result |
|---|---:|
| Step 11 materialization, validation, immutability, recovery | 9 passed in 12.98s |
| Step 9 smart-reuse regression | 19 passed in 22.51s |
| Phase 11 registry/schema regression | 49 passed in 51.50s |
| Phase 11 business-search form non-browser regression | 39 passed, 17 deselected in 60.67s |

Covered Step 11 cases include deterministic bytes, exact manifest lineage,
no-PII field rejection, zero-member snapshots, checksum/count/schema validation,
database-insert failure cleanup, immutable-content refusal, deterministic stale
artifact repair, bounded restart cleanup, and exact-request reuse with one
snapshot/file and two search-history rows.

## No-heavy-work and stop boundary

No canonical import, historical analysis, training, scoring, ranking, Phase 10
build, 5M filtering, export, worker, or server was started. Existing uncommitted
Phase 11 work was preserved. Step 12 and later prompts were not started.

`STOP_AFTER_STEP_11`
