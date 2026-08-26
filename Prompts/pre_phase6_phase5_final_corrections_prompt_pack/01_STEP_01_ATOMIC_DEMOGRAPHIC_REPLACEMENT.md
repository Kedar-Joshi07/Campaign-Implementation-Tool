# Step 1 — Failure-Atomic Demographic Replacement

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`
Required starting SHA: `eeed03d052cc75987cc8926b088d906ae0fb7ccc`

Do NOT begin Phase 6.

## Objective

Make demographics replacement failure-safe so a failed import can NEVER leave the live `demographics` table partially changed.

Current risk:

```text
Source A live
→ replacement with Source B starts
→ live table updated batch-by-batch
→ batches commit
→ later batch fails
→ live table becomes hybrid A/B
→ import marked FAILED
```

This must be eliminated.

## Baseline gate

Run:

```text
git rev-parse HEAD
git status --short
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
python scripts/validate_data.py --json
```

## Required design

Use staging or an equivalently atomic design:

```text
source files
→ full structural preflight
→ staging table
→ bounded batch insert into staging
→ full validation/reconciliation
→ single atomic transaction
→ replace live demographics
→ mark import COMPLETED
```

Strong invariant:

```text
success => live demographics exactly equals new source
failure => live demographics exactly equals previous source
```

The live table must remain unchanged until the replacement source is fully loaded and validated.

## Failure rules

If any failure occurs during CSV read, row validation, staging insert, checksum, completeness validation, or final swap:

```text
existing demographics unchanged
new import record = FAILED
```

No hybrid state.

## Staging guidance

Use a temporary/dedicated staging table mirroring `demographics`. Preserve person_id uniqueness and existing row validation. Do not build a new general ETL platform.

Before live replacement verify:

```text
staged count == rows_inserted
distinct staged person_id == staged count
rows_rejected == 0
source checksum present
```

Because `propensity_scores.person_id` references demographics, preserve historical scores and referential integrity. Do NOT delete historical propensity scores.

If direct DELETE/INSERT is blocked by retained FKs, use an atomic staging-to-live strategy that safely updates existing IDs, inserts new IDs, and handles source-absent IDs without corrupting retained score history.

Only mark the new demographics import COMPLETED after the live replacement transaction succeeds.

## Tests

Add tests for:

1. valid replacement succeeds;
2. invalid header leaves old rows unchanged;
3. invalid row leaves old rows unchanged;
4. simulated failure after multiple staging batches leaves old rows unchanged;
5. simulated final-swap failure rolls back completely;
6. successful replacement exactly matches source IDs/count;
7. checksum recorded only on correct completed import;
8. failed import never becomes authoritative completed provenance;
9. historical propensity scores are preserved;
10. customers/campaign_sales are unaffected.

Run full pytest, compileall, pip check, diff check.

## Report

Report starting SHA, files changed, old failure mode, new staging/atomic architecture, transaction boundary, FK strategy, failure-test results, success reconciliation, provenance timing, full tests, and unresolved issues.

STOP.
