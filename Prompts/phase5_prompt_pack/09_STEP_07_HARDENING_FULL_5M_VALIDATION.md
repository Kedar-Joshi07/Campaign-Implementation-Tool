# Step 7 — Hardening and Real 5M Validation

## Full regression

Run pip check, full pytest, compileall, diff check, data validation.

## Preflight evidence

Record DB file size, free disk, demographic count, model artifact SHA, feature SHA, selected candidate.

## Real path

Use a valid completed v2 Bagging model (never hard-code production ID). Launch through actual API/job path: POST score → 202 job → poll → scoring_run → COMPLETED → detail.

## Exact 5M reconciliation

For current POC dataset require:

```text
demographic_snapshot_count = 5,000,000
scored_person_count = 5,000,000
score rows = 5,000,000
duplicate person IDs = 0
invalid demographic FK = 0
nonfinite = 0
score < 0 = 0
score > 1 = 0
```

## Bounded-memory/keyset evidence

Record chunk_size, chunk_count, largest chunk rows, transformed chunk memory estimate. Prove scoring loop no OFFSET and no whole-universe objects.

## Direct re-score

Deterministic bounded sample → refetch exact features → verified artifact → re-score → compare. Record sample size and max absolute difference.

## Hardening

Controlled failed scoring run, synthetic stale restart, training-vs-scoring and scoring-vs-scoring races.

## Scope scan

Confirm no individual score API, Audience Explorer, band/percentile, audience selection, campaign/export/activation, identity linkage.

## Documentation

Update README, `docs/PHASE_5_IMPLEMENTATION_SUMMARY.md`, tracker, acceptance, Phase 6 handoff. Final committed HEAD becomes Phase 6 baseline.

Any Critical failure = No-Go Phase 6.
