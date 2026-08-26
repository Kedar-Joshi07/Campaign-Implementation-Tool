# Step 2 — Current-Source Canonical Scoring Lifecycle

Use the HEAD produced by Step 1. Do NOT begin Phase 6.

## Objective

Support this lifecycle correctly:

```text
same model + Source A → Run A COMPLETED/current
Source changes to B
same model + Source B → Run B COMPLETED/current
Run A remains historical COMPLETED evidence
```

## Current defects

- Canonical checks may use `verify_current_source_match=False`.
- A partial unique index allows only one COMPLETED run per model forever.

## Canonical definition

A run is current/canonical only when all are true:

```text
status = COMPLETED
score count reconciled
model/artifact/feature provenance valid
demographic_import_id matches current source
demographic_source_checksum matches current source
demographic snapshot count matches current source
demographic min/max person_id match current source
```

A completed run for an old source is historical, not current.

## Historical completed runs

Allow multiple COMPLETED runs for the same model when tied to different demographic sources. Do not delete/downgrade old runs merely because the source changed.

## Index/schema correction

Remove or replace:

```text
UNIQUE(model_run_id) WHERE status='COMPLETED'
```

Preferred minimal design:
- allow multiple COMPLETED runs per model;
- determine current/canonical in service/repository logic using current provenance;
- block submission only when a CURRENT canonical completed run exists for that model/current source.

Avoid fragile JSON-expression uniqueness unless strongly justified. If a migration is needed, keep it transactional, idempotent, and data-preserving.

## Repository/service helpers

Add/refine helpers such as:

```text
find_completed_runs_for_model(...)
find_current_canonical_run_for_model(...)
```

Do not choose canonical by newest timestamp alone.

## Submission behavior

For POST `/api/models/{model_run_id}/score`:

- current canonical run exists → 409
- only stale completed runs exist → allow 202
- active compute job → 409
- unscoreable model → existing behavior

Canonical decisions must use current-source matching.

## Tests

Add tests for same-source duplicate blocking, changed-source rescoring, historical run preservation, same-model multiple COMPLETED runs, canonical resolver source matching, newer stale run not winning over an older current-matching run, legacy no-provenance noncanonical behavior, global heavy-job exclusion, training regression, and migration/index preservation.

Run full regression/compile/pip/diff.

## Report

Report old uniqueness problem, new canonical definition, schema/index changes, historical preservation, same-source and changed-source submission behavior, canonical resolver results, tests, and unresolved issues.

STOP.
