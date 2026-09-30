# Prompt 01 — Exact-SHA CI, API Compatibility, and Mobile Result Detail

## Starting point

- Starting SHA: `f437efd3be9e6d4945b0ee12bff91ccce2697088`
- The working tree already contained the untracked recovery prompt pack and the Prompt 00 evidence directory. Those files were preserved.
- The exact-SHA GitHub Actions run `36409122639` was red in the Tests and Frontend Contract jobs. Public log retrieval returned HTTP 403, so the deterministic failures were reproduced locally instead of inferring details from unavailable logs.

## Defects reproduced

1. `tests/test_phase11_api_backward_compatibility.py::test_create_get_status_and_history_share_one_safe_status_contract` failed because the stable legacy status projection had acquired additive Phase 11 recovery fields.
2. The Result Detail document did not overflow at the tested viewports, but at 360 px the `#result-detail-content` component had an 8 px internal overflow (`scrollWidth=332`, `clientWidth=324`).
3. Retry called `crypto.randomUUID()` directly, while feedback used a separate secure fallback. Retry therefore failed in otherwise supported browser contexts without `randomUUID`.

## Root cause

- The legacy/v1 response schema was expanded in place even though the Phase 11 compatibility contract defined the status response as a stable, business-safe allowlist.
- Result Detail grid, panel, definition-list, and action children did not all have explicit shrink/wrap boundaries.
- Browser idempotency generation was duplicated and retry bypassed the existing secure entropy fallback.

## Contract decision

- Legacy/v1 create, run, status, and history projections retain exactly these nine fields:
  `search_run_id`, `campaign_name`, `status`, `created_at`, `completed_at`, `selected_count`, `delivery_channel`, `export_profile`, and `safe_message`.
- A v2 request is explicitly identified by the versioned selection contract (`propensity_bucket`). Its response uses `SearchSubmissionV2Status`, which adds:
  `selection_contract_version`, `propensity_bucket`, `attempt_number`, `queue_position`, `progress`, `issue`, and `retry_eligible`.
- Result History and Result Detail remain separate richer read models. They remain backward-readable and expose their recorded selection-contract lineage.
- No database schema, migration, source-data, score, snapshot, or historical-run mutation was made in this prompt.

## Files changed

- `app/schemas/potential_customer_search.py`
- `app/services/potential_customer_search_submission_service.py`
- `frontend/css/components.css`
- `frontend/js/business-search-status.js`
- `tests/test_phase11_api_backward_compatibility.py`
- `tests/test_phase11_business_search_form.py`
- `tests/test_phase11_results_history_detail.py`

## Tests added or changed

- Exact v1 field-set assertions for create, run, status, and history.
- Explicit v2 create/read/status/history/detail round-trip assertions.
- OpenAPI assertions for the distinct v1 and v2 schemas.
- Browser retry coverage with `Crypto.prototype.randomUUID` unavailable and `getRandomValues` available.
- Responsive Result Detail coverage at 360x800, 390x844, 768x900, and 1280x900, including the expanded technical-details state.
- Static assertions that retry and feedback share the secure helper, use `getRandomValues`, and do not use `Math.random`.

## Commands and results

1. Focused non-browser contract tests:
   `python -m pytest -q -m "not browser" tests/test_phase11_api_backward_compatibility.py tests/test_phase11_business_search_form.py tests/test_phase11_results_history_detail.py`
   Result: **62 passed, 25 deselected**.
2. Result History/Detail browser tests:
   `python -m pytest -q -m browser tests/test_phase11_results_history_detail.py`
   Result: **8 passed, 5 deselected**.
3. Expanded frontend browser matrix:
   `python -m pytest -q -m browser tests/test_phase11_business_navigation.py tests/test_phase11_business_search_form.py tests/test_phase11_results_history_detail.py tests/test_frontend.py`
   Result: **98 passed, 51 deselected**.
4. Production-file lint:
   `python -m ruff check app/schemas/potential_customer_search.py app/services/potential_customer_search_submission_service.py`
   Result: **passed**.
5. Targeted compilation and `git diff --check`:
   Result: **passed**.
6. A broader CI-shaped frontend/API selector was started and showed no displayed failure through more than half of the suite, but its terminal session ended before the final exit code was captured. It is therefore not claimed as a completed result.

## Remaining risks and gate

- The historic exact-SHA remote run remains a historical failed run and cannot become green retroactively. A future commit/CI run is required to produce a new remote status.
- Repository-wide CI green is not claimed; the prompt pack reserves that assertion for Prompt 19.
- The full existing test-tree Ruff invocation reports established test-fixture import/redefinition and one-line-style debt outside this narrow production change. The modified production Python files are clean.

**Prompt 01 gate: GO.** The deterministic API, responsive Result Detail, and secure browser retry defects in scope are fixed and covered by passing focused suites.

**Recommended next prompt:** `02_DURABLE_ATTEMPT_FENCING_LEASES_AND_STALE_WORKER_PROTECTION.md`.
