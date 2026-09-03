# Hardening Step 3 — Consistent Export Snapshot & True Mid-Export Drift

## Problem
Pre-export and post-export currentness checks are good, but streaming bytes cannot be
retracted if provenance changes after the response begins.

Freeze an explicit:
`CAMPAIGN_EXPORT_SNAPSHOT_CONTRACT_VERSION = "1"`

## Required semantics
At export start:
1. validate finalized/current campaign
2. resolve exact source/import/model/scoring provenance token
3. begin one consistent SQLite read snapshot/transaction for member/contact reads
4. all rows in the export must come from that same snapshot
5. never mix old/new source data

Preferred semantics:
- file is valid against the provenance snapshot approved at export start
- if authoritative currentness changes during export, record that safe fact in aggregate
  export metadata
- future exports from the now-stale campaign are blocked
- current file remains internally consistent/reproducible against start snapshot

If the product instead requires current-file invalidation on mid-run drift, do not pretend
streaming can retract bytes. Use a secure ephemeral spooled/temp artifact that is fully
validated before response starts and deleted immediately after use. It must never be a
persistent server-side PII artifact.

If needed, add only small additive audit fields/schema version, e.g.:
- export_snapshot_contract_version
- start_provenance_sha256
- source_changed_during_export
- completion_currentness_state

No PII and no 5M table rebuild.

## True concurrency test
On a DB copy:
1. start a sufficiently large export
2. wait until STARTED and at least one chunk is processed
3. mutate authoritative source provenance from another connection
4. continue export
5. verify chosen snapshot contract
6. prove no mixed-provenance output
7. prove future export is blocked

This must be a true mid-export mutation, not drift-before-export. STOP.
