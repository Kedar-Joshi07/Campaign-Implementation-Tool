# STEP 2 — SQLite Foundation and Schema

## Objective
Create the SQLite connection layer, metadata/import tables, and frozen application tables without loading production-sized data yet.

## Prompt to coding agent
Implement only Step 2 of Phase 1.

Read the Phase 1 freeze and current progress first.

### Database connection
Implement `app/database/connection.py` with:
- configured database path
- directory creation if needed
- per-operation SQLite connections rather than one unsafe global connection
- `row_factory = sqlite3.Row`
- `PRAGMA foreign_keys = ON`
- appropriate busy timeout
- attempt `PRAGMA journal_mode = WAL`

Provide a context manager/helper that:
- opens connection
- configures pragmas
- commits on successful write when appropriate
- rolls back on failure
- closes reliably

### Schema management
Implement `app/database/schema.py`.

Create:
1. `app_metadata`
2. `data_import_runs`
3. `customers`
4. `campaign_sales`
5. `demographics`

Use the exact frozen columns from `01_PHASE_1_FREEZE_AND_BOUNDARIES.md`.

### Data typing guidance
Use practical SQLite types:
- identifiers/text/categorical fields: TEXT
- dates: TEXT stored in ISO `YYYY-MM-DD` format
- timestamps: TEXT ISO format
- integer flags/counts: INTEGER
- monetary/numeric continuous fields: REAL

Do not invent database enums.

### Key constraints
- `customers.customer_id` PRIMARY KEY
- `campaign_sales.campaign_sales_id` PRIMARY KEY
- `campaign_sales.customer_id` references `customers.customer_id`
- `demographics.person_id` PRIMARY KEY
- useful NOT NULL constraints on identifiers and essential fields
- flags should be constrained to 0/1 where practical
- `pu_label` constrained to 0/1

Do not create any foreign key between demographics and historical tables.

### Metadata
Set initial metadata values such as:
- schema_version = `1`
- application_version
- database_initialized_at

### Initialization command
Create a script such as:
`python scripts/init_db.py`

Behavior:
- create DB if absent
- create all tables idempotently
- do not delete data
- print/log created/verified schema

Optional explicit reset mode may exist only if clearly named and guarded, e.g. `--reset`, with warning.

### Schema inspection
Create a development/debug function or CLI mode that prints:
- table names
- column names
- indexes
- row counts if any

Do not expose arbitrary SQL execution.

### Tests
Add tests for:
1. database initialization
2. expected tables exist
3. expected customer/campaign/demographic column counts
4. foreign keys enabled
5. campaign sales rejects an invalid `customer_id` when constraints are active
6. re-running initialization is idempotent

Use a temporary SQLite file for tests, never the real POC DB.

### Step completion criteria
- DB initializes from scratch
- all frozen tables exist
- keys/constraints work
- tests pass
- no bulk dataset import yet

Update progress tracker and stop.
