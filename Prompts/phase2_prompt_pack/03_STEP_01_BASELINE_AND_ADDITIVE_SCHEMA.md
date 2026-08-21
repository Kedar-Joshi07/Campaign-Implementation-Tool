# Step 1 — Baseline Verification and Additive Phase 2 Schema

## Objective

Start Phase 2 from the accepted commit, prove Phase 1 remains healthy, and add the minimum idempotent schema/migration support required to persist historical analysis runs.

Do not implement analytics queries, new APIs, or UI behavior in this step.

## Required work

### 1. Baseline evidence

Record in `11_PROGRESS_TRACKER.md`:

- `git rev-parse HEAD`
- `git status --short`
- current branch and remote relationship
- Python version
- `python -m pip check`
- full baseline test result, expected to be 77 passing tests at the specified base
- current schema version and Phase 1 table counts when a populated database is available

If tests fail before changes, diagnose and stop. Do not hide a pre-existing failure in Phase 2 work.

### 2. Migration architecture

Extend the existing database module without replacing its established connection/schema behavior.

Implement a small ordered migration mechanism that:

1. Determines the stored schema version.
2. Initializes the Phase 1 base tables when starting from an empty database.
3. Applies each missing migration exactly once in order.
4. Runs each migration transactionally.
5. Updates `app_metadata.schema_version` only after its migration succeeds.
6. Is safe to call repeatedly during startup, scripts, and tests.
7. Rejects a database whose recorded version is newer than the application understands.

Keep it explicit. A dictionary/list of versioned Python migration functions or SQL statements is sufficient; do not add a migration framework.

### 3. `historical_analysis_runs`

Add the Phase 2 table defined in the freeze. Use database-level constraints where practical.

Recommended concrete shape:

```sql
CREATE TABLE historical_analysis_runs (
    analysis_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL
        CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    conversion_definition TEXT NOT NULL
        CHECK (conversion_definition IN (
            'ATTRIBUTED_PURCHASE', 'ANY_PURCHASE', 'RESPONSE'
        )),
    filters_json TEXT NOT NULL,
    results_json TEXT,
    observation_count INTEGER NOT NULL DEFAULT 0
        CHECK (observation_count >= 0),
    selected_customer_count INTEGER NOT NULL DEFAULT 0
        CHECK (selected_customer_count >= 0),
    positive_customer_count INTEGER NOT NULL DEFAULT 0
        CHECK (positive_customer_count >= 0),
    unlabeled_customer_count INTEGER NOT NULL DEFAULT 0
        CHECK (unlabeled_customer_count >= 0),
    positive_customer_rate REAL,
    error_message TEXT,
    CHECK (
        positive_customer_rate IS NULL
        OR positive_customer_rate BETWEEN 0 AND 1
    )
)
```

Add a newest-first listing index such as `(created_at DESC, analysis_run_id DESC)`.

Do not store raw customer IDs, SQL text, or person-level result rows in this table.

### 4. Phase 2 query indexes

Add only simple indexes already justified by frozen filters:

- `campaign_sales(campaign_channel)`
- `campaign_sales(product_category)`
- `campaign_sales(campaign_type)`

Do not add a speculative wide composite index in this step. That decision belongs to Step 7 after query-plan and timing evidence.

### 5. Initialization integration

Ensure all normal initialization paths bring the database to schema version 2, including:

- application startup/first database access
- `scripts/init_db.py`
- tests using temporary databases

Preserve the Phase 1 required-index verification semantics while extending them cleanly for Phase 2 indexes.

## Tests

Add tests that prove:

1. A fresh database reaches version 2.
2. A populated version-1 database migrates to version 2 without changing row counts or representative row values in Phase 1 tables.
3. Calling initialization/migrations multiple times is idempotent.
4. The new table columns, constraints, and indexes exist.
5. A failed migration does not advance the stored version.
6. A future/unknown schema version fails clearly.
7. Existing schema/index tests continue to pass.

## Completion criteria

- Phase 1 baseline is recorded.
- Schema version is 2.
- Migration is additive and idempotent.
- Phase 1 rows and APIs are unchanged.
- No historical query/API/UI functionality has been implemented.
- Focused and full tests pass.
- Progress tracker is updated.

Stop after this step.

