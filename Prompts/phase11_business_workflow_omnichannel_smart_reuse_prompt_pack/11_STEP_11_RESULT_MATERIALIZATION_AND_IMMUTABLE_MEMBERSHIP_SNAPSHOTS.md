# Step 11 — Result Materialization & Immutable Membership Snapshots

## Objective
Persist exact selected analytical membership for history and future closed-loop learning.

Preferred POC format:
compressed Parquet if adding pyarrow is justified and dependency validation passes.
Fallback: deterministic compressed CSV/JSONL if Parquet introduces unacceptable dependency cost.

Choose one format and freeze `RESULT_MEMBERSHIP_CONTRACT_VERSION=1`.

Required membership fields only:
- person_id
- propensity_score
- percentile_bucket
- decile
- rank_band

Optional non-PII analytical fields may be included only with explicit rationale.
Do not store:
name, email, phone, postal/street address.

Storage layout example:
`artifacts/results/result_snapshot_000001/members.parquet`
`artifacts/results/result_snapshot_000001/manifest.json`

Manifest:
- snapshot ID
- contract version
- row count
- file SHA
- generation/scoring/model/analysis IDs
- criteria/branch hashes
- creation time
- storage format/schema

Write safely:
- temp file
- fsync/close where applicable
- checksum/row validation
- atomic rename/publish
- DB registry commit only after artifact validates

If DB insert fails after artifact creation, recover/clean orphan safely.
If artifact write fails, no COMPLETED snapshot row.

Repeated exact search reuses the existing snapshot; do not duplicate file.

Add validator/CLI or service function that verifies snapshot schema/count/checksum and no PII columns.

Evidence:
`docs/evidence/phase11/11_RESULT_SNAPSHOTS.md`

STOP.
