# Step 2 — Atomic Live Swap + Import Provenance Completion

Use the HEAD from successful Step 1.

Do not begin Phase 6.

## Problem

The demographic replacement now stages safely and performs the live table mutation transactionally, but the successful live swap COMMIT happens before `data_import_runs` is updated to:

```text
status = COMPLETED
source_checksum = <new source>
```

A process/power failure between those two commits could expose the new live demographic source while the authoritative latest COMPLETED import metadata still describes the old source.

## Required invariant

The final live replacement and successful import provenance transition must be one SQLite transaction:

```text
BEGIN IMMEDIATE
    apply staged source to live table
    reconcile live vs staged
    update the same import_id to COMPLETED
    persist rows_read/rows_inserted/rows_rejected
    persist source_checksum
    persist completed_at
COMMIT
```

If anything fails before COMMIT:

```text
live source = previous source
new import must not be COMPLETED
```

After an abrupt SQLite/process recovery:
- either both new live source and new COMPLETED provenance are visible;
- or neither is visible.

Never one without the other.

## Refactor guidance

Prefer:

```text
_finish_import_run_on_connection(connection, ...)
```

for the raw metadata UPDATE.

Keep `_finish_import_run(database_path, ...)` as a wrapper for failure/other paths.

Add a combined function conceptually like:

```text
_apply_atomic_demographic_replace_and_complete_import(...)
```

that opens one write connection, executes `BEGIN IMMEDIATE`, calls the staging→live replacement, then calls the connection-level completion UPDATE before transaction exit.

Avoid a second success `_finish_import_run()` after this combined transaction.

Failure handling may still record `FAILED` in a later transaction after rollback.

## Staging cleanup

Dropping the staging table may happen after the atomic transaction.

A crash after successful commit but before staging cleanup is acceptable because live data + provenance are consistent. Add safe orphan staging cleanup if practical, but do not turn this into a generic ETL platform.

## Generalize the publication guarantee to all three authoritative datasets

The same provenance principle must hold for `customers` and `campaign_sales`, because
Step 4 will use their completed import records as the historical source-of-truth.

Do not leave customer/campaign live publication as incremental committed batches followed
by a separate success-metadata transaction.

Use bounded staging for all authoritative imports:

```text
source
→ staging batches (commits allowed because staging is not authoritative)
→ full validation/reconciliation
→ BEGIN IMMEDIATE
   publish staging to live target
   mark the same import_id COMPLETED
   persist checksum/counters/completed_at
  COMMIT
```

Required invariants for customers, campaign_sales, and demographics:

```text
success => live table and COMPLETED provenance describe the same source
failure/crash-before-commit => previous live source remains authoritative
```

For a fresh empty target, publish staging atomically into the empty live table.
For replacement:
- customer replacement must preserve the existing rule that it is blocked while campaign rows exist;
- campaign replacement must atomically replace campaign rows without changing customers;
- demographic replacement must preserve historical propensity-score referential integrity.

This deliberately removes the Phase 1 partial-live-import limitation for authoritative
imports. Do not load the full source into Python memory.

## Tests

Required:

1. mutation succeeds but completion metadata helper raises → live data rolls back.
2. completion metadata UPDATE itself fails → live data rolls back.
3. success exposes both new live source and COMPLETED checksum.
4. failure handler records FAILED after the atomic transaction rolls back.
5. previous completed provenance remains authoritative after failure.
6. historical propensity scores remain intact.
7. existing staging-batch and final-swap rollback tests remain green.
8. startup/reopen after a successful transaction sees matching live source + provenance.

Run full regression, compileall, pip check, diff check and data validation.

STOP with a report.
