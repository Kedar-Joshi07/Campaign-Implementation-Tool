# Bounded Phase 1 Hardening Commit Prompt

## Role

You are implementing one tightly scoped Phase 1 hardening change in the repository:

`https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

The audited base commit is:

`50f673797cdabf064bb782382decb54f79b24488`

Before editing:

1. Confirm the current repository, branch, and `HEAD`.
2. Read `README.md`, `Prompts/phase1_prompt_pack/01_PHASE_1_FREEZE_AND_BOUNDARIES.md`, `Prompts/phase1_prompt_pack/02_AGENT_OPERATING_INSTRUCTIONS.md`, and `Prompts/phase1_prompt_pack/11_PROGRESS_TRACKER.md`.
3. Inspect the existing implementation and tests for every file named below.
4. Preserve unrelated user changes and do not reset, discard, or reformat unrelated files.
5. If `HEAD` is no longer `50f6737`, compare intervening changes and continue only when they do not already solve or conflict with this scope.

## Objective

Prepare one bounded, commit-ready hardening diff that fixes exactly these four medium findings:

1. Sanitize public import-history errors.
2. Make approximate customer-count readiness meaningful and visible.
3. Document the repository's Git LFS data-delivery workflow accurately.
4. Preflight replacement sources before deleting existing data.

Do not start Phase 2 and do not make broad architecture, style, dependency, schema, or UI redesign changes.

## Authoritative constraints

- Keep FastAPI, SQLite, HTML, CSS, and Vanilla JavaScript.
- Do not introduce a frontend framework or build system.
- Do not add Redis, task queues, services, containers, cloud resources, authentication, or ML dependencies.
- Do not add PU learning, model training, propensity scoring, audience selection, campaign creation, or export behavior.
- Do not modify the three Git LFS GZIP datasets, samples, masters, summaries, generator outputs, or LFS object hashes.
- Do not change frozen customer/campaign/demographic table columns.
- Avoid a database migration unless strictly necessary. The requested solution should not require one.
- Preserve the existing API routes and their bounded aggregate behavior.
- Preserve detailed internal import errors in logs and/or `data_import_runs`; sanitize only the public API representation.
- Keep imports streaming and memory-bounded.
- Update tests alongside implementation changes.
- Do not commit or push unless the human explicitly authorizes those actions. Produce a clean, single-commit-ready diff.

## Finding 1 — Sanitize public import-history errors

### Current defect

`GET /api/data/imports` returns `error_message` from `data_import_runs` without sanitization. Missing-file errors expose absolute filesystem paths, and integrity failures can expose raw SQLite details.

Relevant code:

- `app/schemas/data.py`
- `app/services/data_api_service.py`
- `app/services/data_import_service.py`
- `app/repositories/data_repository.py`
- `tests/test_data_api.py`
- `tests/test_data_import.py`

### Required behavior

1. Keep the full internal error message in server logs and the database audit record.
2. At the API boundary, return only a stable, display-safe error message.
3. A public import error must not contain:
   - absolute Windows or POSIX paths;
   - parent directories;
   - SQLite exception/constraint details;
   - SQL text;
   - stack traces;
   - arbitrary source-row contents.
4. Preserve `source_path` filename sanitization already implemented.
5. Keep the public API useful. Map internal failures to a small stable set of messages, for example:
   - source file unavailable;
   - source schema invalid;
   - source data validation failed;
   - target already contains data;
   - database operation failed;
   - import failed.
6. Prefer a small private helper in the API service such as `_public_import_error(...)`; do not spread sanitization logic across routers.
7. Preserve response compatibility where practical. It is acceptable to keep the `error_message` field but replace its value with the sanitized message. Do not expose a second raw field.

### Required tests

Add API tests proving that:

1. A missing source file returns a useful public message but not the temporary directory or full path.
2. A duplicate/SQLite integrity failure does not expose `UNIQUE constraint failed`, table names, SQL, or a raw SQLite message.
3. A schema mismatch returns a stable public schema-error message without echoing the full received header or path.
4. Successful import rows still return `error_message: null`.
5. Existing limit/offset and source-filename sanitization tests continue to pass.

## Finding 2 — Meaningful approximate-count readiness

### Current defect

With `CUSTOMER_COUNT_EXACT_REQUIRED=false`, any nonzero customer count is reported as `OK`. For example, 1,000 rows can be `OK` against the 125,000 target. The API returns `exact_match_required`, but Data Status does not display the policy.

Relevant code:

- `app/config.py`
- `.env.example`
- `app/services/data_reconciliation_service.py`
- `app/schemas/data.py`
- `app/services/data_api_service.py`
- `frontend/index.html`
- `frontend/js/data-status.js`
- `frontend/js/ui.js` if needed
- `tests/test_data_reconciliation.py`
- `tests/test_data_api.py`
- `tests/test_frontend.py`
- `README.md`

### Required count policy

Implement a configurable percentage tolerance for non-exact customer counts.

Add:

`CUSTOMER_COUNT_TOLERANCE_PERCENT=5.0`

Rules:

1. Validate/configure it as a finite number from `0` through `100`.
2. Default customer expectation remains 125,000.
3. Exact datasets keep current behavior:
   - zero rows → `NOT_LOADED`;
   - structural violations → `ERROR`;
   - nonzero exact-count mismatch → `WARNING`;
   - exact count with no violations → `OK`.
4. Non-exact customer behavior becomes:
   - zero rows → `NOT_LOADED`;
   - structural violations → `ERROR`;
   - actual count outside the inclusive tolerance range → `WARNING`;
   - actual count inside the inclusive tolerance range → `OK`.
5. Calculate and return explicit inclusive bounds:
   - `acceptable_min_rows`;
   - `acceptable_max_rows`.
6. Preserve `expected_count_match` as literal equality, but add a separate `acceptable_count` boolean.
7. Return sufficient policy information through `/api/data/status`, including:
   - `exact_match_required`;
   - `count_tolerance_percent` when applicable;
   - `acceptable_min_rows` and `acceptable_max_rows`;
   - `acceptable_count`.
8. Do not make the expected count or tolerance hard-coded in SQL.

Use deterministic integer bounds. Document the rounding rule and test the boundaries. A reasonable rule is:

- minimum = `ceil(expected * (1 - tolerance / 100))`
- maximum = `floor(expected * (1 + tolerance / 100))`

### Required UI behavior

On each Data Status dataset card:

1. Display whether the target is `Exact target` or `Approximate target`.
2. For an approximate target, show the tolerance, for example `Approximate target (±5%)`.
3. Do not rely on color alone; keep the textual `Ready`, `Warning`, `Error`, or `Not loaded` badge.
4. Continue displaying expected and actual rows using formatted numbers.
5. Do not add charts or redesign the page.

### Required tests

Add tests for:

1. 1,000 actual against 125,000 ±5% → `WARNING`.
2. A count exactly at the lower boundary → `OK`.
3. A count exactly at the upper boundary → `OK`.
4. A count one row below/above the boundary → `WARNING`.
5. Exact campaign/demographic mismatch behavior remains `WARNING`.
6. Structural errors override count acceptability and remain `ERROR`.
7. Empty data remains `NOT_LOADED`.
8. `/api/data/status` returns the new policy fields correctly.
9. Frontend contract tests confirm visible exact/approximate policy labels and no hard-coded KPI values.

## Finding 3 — Document Git LFS and correct stale README statements

### Current defect

Commit `50f6737` delivers the three required GZIP files through Git LFS, but README prerequisites and setup do not mention LFS. The README also says generated source files under `data/` are Git-ignored and that generation is required before import; both statements are now false.

Relevant files:

- `README.md`
- `.gitattributes` for verification only; do not change unless necessary
- `.gitignore` for verification only; do not change unless necessary
- `docs/PHASE_1_IMPLEMENTATION_SUMMARY.md` only if a small consistency note is needed

### Required documentation changes

Update `README.md` to include:

1. Git LFS as a prerequisite alongside Python.
2. Fresh-clone commands, including:

   ```powershell
   git lfs install
   git lfs pull
   git lfs ls-files
   ```

3. A clear statement that the exact Phase 1 GZIP datasets are stored through Git LFS and can be imported directly after LFS pull.
4. Correct folder-structure language:
   - generated source datasets and samples are tracked;
   - local SQLite database/WAL/SHM files remain ignored.
5. A concise data manifest containing expected sizes and SHA-256 values:

   | File | Expected bytes | SHA-256 |
   |---|---:|---|
   | `customer_master_125000.csv.gz` | `6145052` | `5e80e1f25e433373f5f4b066e4d8d3a723cb4ae8d5af028895ea469d3c533a2e` |
   | `campaign_sales_570000.csv.gz` | `6465596` | `16aace571676765f358ecb3e981ec273ae08653fc9397229856cc4e27dfd500c` |
   | `usa_demographic_synthetic_5000000_rows.csv.gz` | `331342839` | `b5ff7051dda391f60188838ff91cb13e75c1cd855ef57461b2b0ad0a0786cd1d` |

6. Troubleshooting for unresolved LFS pointer files:
   - file is approximately 130 bytes instead of the expected size;
   - file begins with `version https://git-lfs.github.com/spec/v1`;
   - import reports `Not a gzipped file` or similar;
   - fix with `git lfs install` and `git lfs pull`.
7. State that generators are optional reproducibility/regeneration tools; they are not required when the committed LFS objects are present.
8. Disk-space guidance: allow space for approximately 344 MB of compressed LFS inputs plus approximately 2.9 GB for the populated SQLite database, with additional working headroom.
9. Keep Windows commands and cross-platform notes consistent with existing README style.

Do not place LFS objects, database files, or new generated artifacts into normal Git history.

## Finding 4 — Preflight replacement sources before deletion

### Current defect

`_prepare_target(..., replace=True)` deletes the target before `_stream_sources` opens the source and validates headers. A wrong-header, unreadable, or corrupt replacement can erase valid existing data before inserting a row.

Relevant code:

- `app/services/data_import_service.py`
- `app/services/data_validation_service.py` only if genuinely needed
- `tests/test_data_import.py`
- `README.md` replacement/troubleshooting sections

### Required implementation

1. Add a focused source-preflight helper; avoid a new abstraction framework.
2. Preserve failed-attempt metadata:
   - initialize DB;
   - start the `RUNNING` import record;
   - validate/resolve source paths;
   - preflight every source;
   - only then clear the target when `replace=True`;
   - stream, validate and insert as before.
3. Preflight all source files before deleting anything.
4. For every import, preflight at least:
   - file exists and is a supported `.csv` or `.csv.gz`;
   - file opens successfully;
   - text decodes with the supported encoding;
   - file is nonempty;
   - header exactly matches the frozen schema.
5. For `replace=True`, perform a full streaming structural/readability pass over every source before deletion so that:
   - CSV parsing errors are detected;
   - incorrect field counts are detected;
   - GZIP CRC/truncation errors are detected even when corruption occurs after the header;
   - the pass remains memory-bounded.
6. The replacement preflight does not need to repeat all business validation for every row. Late business-rule failure may still leave a documented partial replacement under the current batch-commit design; do not introduce staging tables or a multi-gigabyte single transaction in this bounded commit.
7. Keep defense-in-depth header/row validation during the actual import even after preflight.
8. Do not increment final `rows_read`/`rows_inserted` counters during preflight. Those counters must describe the actual import pass.
9. Log one concise preflight start/completion/failure event per source, not per row.
10. If preflight fails:
    - mark the import run `FAILED`;
    - keep the existing target row count and data unchanged;
    - return an actionable CLI error;
    - do not expose raw details through the public API after Finding 1 is fixed.

### Required tests

Add tests proving:

1. Customer `--replace` with a wrong header preserves the original customer rows when no campaign rows block replacement.
2. Campaign `--replace` with a corrupt GZIP preserves the original campaign rows.
3. Demographic multi-part `--replace` preflights every part; if a later part has a bad header or corrupt stream, all original demographic rows remain.
4. Failed preflight creates a `FAILED` audit row with zero inserted rows.
5. Successful customer, campaign and demographic replacement still works.
6. Default non-replace duplicate protection remains unchanged.
7. The 5M pipeline remains streaming and does not load complete files into memory.

## Expected file scope

The final diff should normally be limited to:

```text
.env.example
README.md
app/config.py
app/schemas/data.py
app/services/data_api_service.py
app/services/data_import_service.py
app/services/data_reconciliation_service.py
frontend/index.html
frontend/js/data-status.js
frontend/js/ui.js                 # only if needed
tests/test_data_api.py
tests/test_data_import.py
tests/test_data_reconciliation.py
tests/test_frontend.py
docs/PHASE_1_IMPLEMENTATION_SUMMARY.md   # small consistency update only if needed
Prompts/phase1_prompt_pack/11_PROGRESS_TRACKER.md
```

Do not modify unrelated files. Do not modify the frozen specification files, Git LFS datasets, samples, masters, summaries, or generator scripts in this commit.

## Explicitly out of scope

Do not fix these separate low-severity findings in this commit:

- global backend badge remaining offline after successful retry;
- `campaign_sales_summary.json` catalogue-versus-observed product naming;
- machine-specific path in the demographic summary.

Do not perform general cleanup, dependency upgrades, formatting sweeps, UI redesign, schema refactoring, or performance optimization unrelated to the four medium findings.

## Validation sequence

Run and record:

1. `python -m pip check`
2. `python -m pytest`
3. `git diff --check`
4. Fresh temporary SQLite initialization.
5. Small fixture import of all three datasets.
6. Replacement-preflight failure checks proving existing rows remain intact.
7. Reconciliation tests for exact and approximate count policies.
8. API checks proving public errors contain no full path or SQLite detail.
9. Browser/manual check of Data Status exact/approximate labels.
10. If Git LFS files and sufficient disk space are available, run the full documented 125K/570K/5M import and reconciliation against a temporary database outside tracked repository paths. Confirm:
    - exact row counts;
    - zero rejected rows;
    - all 17 indexes;
    - zero structural violations;
    - all required APIs return successfully.

Do not claim a test was run if it was not run. Document environmental limitations precisely.

## Acceptance criteria

This hardening task is complete only when:

- `/api/data/imports` never exposes full paths, raw SQLite text, SQL, stack traces, or row contents.
- A severe customer-count shortfall is `WARNING`, not `OK`.
- Approximate count tolerance and inclusive bounds are tested and returned by the API.
- Data Status visibly distinguishes exact and approximate targets.
- README accurately explains Git LFS, current tracked data, optional regeneration, object verification and troubleshooting.
- Replacement preflight failures preserve all existing target rows.
- Failed preflights are recorded as `FAILED` without counting preflight rows as imported.
- All existing and new tests pass.
- No Phase 2 functionality or unrelated change is present.
- The progress tracker records the hardening work and evidence.

## Final response format

Report:

1. Base and resulting `HEAD` SHA.
2. Files changed, grouped by finding.
3. Exact behavior implemented for each finding.
4. Tests and runtime checks executed with results.
5. Any remaining limitations.
6. Confirmation that LFS data files and Phase 2 scope were untouched.
7. Proposed single commit message.

Suggested commit message:

`Harden Phase 1 import safety, readiness policy, and LFS setup`

Stop after producing the validated commit-ready diff unless explicit authorization to commit or push has been provided.
