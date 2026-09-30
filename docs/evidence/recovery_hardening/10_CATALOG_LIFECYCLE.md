# Step 10 — targeting catalog lifecycle and option-load correctness

## Starting point and working tree

- Starting SHA: `f437efd3be9e6d4945b0ee12bff91ccce2697088`.
- The working tree already contained the sequential, uncommitted outputs and evidence for recovery-hardening Steps 01–09. They were preserved.
- No commit or push was performed.

## Defects reproduced

The earlier A→B→A happy-path repair existed, but repository inspection exposed four remaining lifecycle defects:

1. Authoritative source checksums were read before the promotion transaction. An import could commit between that read and promotion, allowing an older checksum identity to become current.
2. Normalized product repair and parent-catalog promotion occurred in separate transactions, so their lifecycle was not atomic.
3. `is_current` had no database-level uniqueness rule. Application code intended one winner but the schema permitted multiple current rows.
4. Results history looked up product labels through the current catalog only. A historical run could lose its original product label after a later catalog removed or renamed that product.

## Root cause

Catalog identity, normalized child completeness, and current-version promotion were treated as related operations but were not one transactionally guarded lifecycle contract. Historical runs recorded `catalog_version`, but Results did not use it for label resolution.

## Implemented behavior

### Atomic current-version promotion

- The latest completed checksums for customers, campaign sales, and demographics are read inside `BEGIN IMMEDIATE`.
- If the exact catalog already exists, its checksum identity and JSON payload are validated, its normalized products are verified/repaired, and it is promoted in that same transaction.
- Promotion clears any previous current row before setting the exact winner.
- A warm request does not rewrite the current marker when the exact version is already the sole current row.

### Safe first build and concurrent import handling

- Large context/targeting option extraction runs only when the exact checksum identity has never been materialized.
- The scan runs outside the write transaction to avoid holding the SQLite writer lock during large reads.
- A second `BEGIN IMMEDIATE` re-reads authoritative checksums before insertion. If an import changed while the scan ran, the stale build is discarded and resolution retries against the new identity.
- If another worker created the exact catalog during the scan, the existing catalog is validated and reused instead of rebuilt.
- Retries are bounded to four source transitions and fail closed if imports keep changing continuously.

### Product-catalog lifecycle

- Normalized product rows are compared by exact `(product_id, product_name, product_category)` content, not only by row count.
- Missing, incorrect, or partial product rows are rebuilt from the compact immutable parent catalog JSON without rescanning campaign sales or demographics.
- Repair and parent promotion share one transaction.
- Exact historical product-catalog lookup is supported by `catalog_version`.

### Currentness and submission consistency

- `get_targeting_catalog()` projects `is_current=true` only when both the stored flag and the latest authoritative checksum-derived version agree.
- The options endpoint uses atomic get/build/promotion and returns only the committed winning version.
- Live submission and preflight validation therefore accept the version just returned by live options unless a genuinely newer import intervened.
- Startup and post-import reconciliation continue to call the same idempotent catalog lifecycle, repairing missed post-import refreshes.

### Historical rendering

- Result detail uses the run's recorded catalog version for product labels before falling back to current source data or the product identifier.
- Bounded result history loads all required historical catalog/product pairs in one query, retaining the existing no-N+1 behavior.
- A historical search continues to render `Savings / Banking` after the live source and current catalog move to a different product.

### Persistence enforcement

- Schema version is now `28`.
- A partial unique index, `idx_targeting_option_catalog_current`, enforces at most one row with `is_current=1`.
- Migration 28 deterministically retains the newest existing current row if an older database contains duplicate current markers, then creates the unique index.

## Files changed for Step 10

- `app/database/schema.py`
- `app/database/search_recovery_schema.py`
- `app/services/phase11_results_service.py`
- `app/services/targeting_option_catalog_service.py`
- `tests/test_phase10_schema_registry_repository.py`
- `tests/test_phase11_attempt_execution_fencing.py`
- `tests/test_phase11_future_feedback_lineage.py`
- `tests/test_phase9_schema.py`
- `tests/test_targeting_catalog_lifecycle.py`

The existing startup and post-import callers in `app/main.py`, `app/services/data_import_service.py`, and `app/services/source_currentness_service.py` were inspected and retained because they already invoke the shared reconciliation boundary.

## Tests added

`tests/test_targeting_catalog_lifecycle.py` covers:

- A→B→A checksum lifecycle and exact re-promotion without option rescans;
- a deterministic build/import overlap proving checksums are rechecked before promotion;
- repair of an existing catalog with incorrect/missing normalized product data;
- ten warm loads with campaign-sales and demographic scan methods forbidden;
- startup reconciliation after a simulated missed post-import refresh;
- live options version accepted by live v2 submission;
- historical Result product labels resolved from the run's recorded catalog;
- schema-28 duplicate-current cleanup and unique-index enforcement.

Existing schema, import, currentness, API, Results, and performance tests were also run.

## Commands and results

1. `python -m pytest tests/test_targeting_catalog_lifecycle.py -q`
   - `8 passed in 55.89s`.
2. Broad catalog-adjacent regression covering targeting lifecycle, currentness, imports, business form, result history, performance gates, and schema migrations:
   - `126 passed, 26 deselected in 637.53s`.
3. `python -m compileall -q app`
   - Passed.
4. Focused Ruff check across all Step 10 implementation, migration, and test files:
   - `All checks passed!`.
5. `git diff --check`
   - Passed; only pre-existing CRLF normalization warnings were reported.

## Acceptance evidence

- The exact catalog returned by `/api/potential-customer-search/options` was submitted through `/api/potential-customer-search/runs` with calibrated selection and received HTTP `201`.
- The deterministic race test changed authoritative identity while an unseen catalog was being scanned; the worker returned and promoted the new authoritative identity, not the stale scanned version.
- Warm loads succeeded while all large option fetch methods and product rebuild were configured to fail if called.
- Database uniqueness prevents two catalog rows from being current simultaneously.

## Known remaining risks

- A truly unseen checksum identity still requires one option build. This is intentional; only exact existing versions use the scan-free path.
- The existing product option cap of 250 and dimension option cap of 100 remain unchanged policy.
- If the immutable parent JSON or its checksum identity is corrupt, catalog access fails closed rather than silently overwriting historical evidence.
- The broad performance gate uses deterministic local fixtures. This prompt proves the warm path performs no large-table option scan; canonical 5M timing remains owned by the later performance-certification prompt.

## Gate

**GO for Prompt 10.** The live options version and live submission contract agree, at most one catalog is current, A→B→A reuses the exact prior payload, concurrent source changes cannot promote stale data, and warm loads remain compact-table-only.

Recommended next prompt: `11_CALIBRATION_TRAIN_CALIBRATE_TEST_ISOLATION_AND_GOVERNANCE.md`.
