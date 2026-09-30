# Prompt 01 — Make the exact-SHA baseline green: API compatibility, mobile Result Detail, browser retry key fallback


# Common execution contract

**Canonical starting SHA:** `f437efd3be9e6d4945b0ee12bff91ccce2697088`

You are working on the repository **Campaign Implementation Tool**. Treat the current codebase, database schema, tests, migrations, and committed evidence as authoritative only after you verify them yourself. Do not assume prior summaries are correct merely because they exist in `docs/evidence`.

Before changing anything:

1. Run `git rev-parse HEAD` and confirm the starting commit is `f437efd3be9e6d4945b0ee12bff91ccce2697088` or a documented descendant created by an earlier prompt in this pack.
2. Run `git status --short`. Do not overwrite unrelated local changes. If prior pack steps created changes, preserve them and identify the exact prior step/commit.
3. Read the files named in this prompt plus adjacent callers, tests, migrations, API schemas, and frontend consumers. Search the whole repository for every symbol you modify.
4. Reproduce the current behavior with focused tests before changing it when practical.
5. Keep changes additive and narrowly scoped. Do not rewrite frozen Phase 1-10 behavior unless a defect proven by this pack requires it.
6. Preserve synthetic-data truthfulness. Do **not** fabricate customers, widen targeting filters, lower approved probability thresholds, duplicate people, change scenario definitions, or invent evidence to make a demo pass.
7. Preserve existing immutable lineage. Never rewrite historical attempts, snapshots, calibration artifacts, feedback batches, or audit events in place.
8. Never persist tracebacks, raw exception text, filesystem paths, secrets, contact PII, or unbounded payloads into business-safe runtime fields.
9. Every mutable worker write must be concurrency-safe and transactionally guarded.
10. Do not mark a requirement complete just because code exists. Prove the behavior through tests and, where requested, canonical/runtime evidence.
11. If a required business-policy decision is not encoded in the repository, stop that policy change and produce a decision document instead of silently choosing.
12. Do not commit or push unless explicitly instructed by the operator. At the end, report changed files, tests run, results, remaining risks, and the next prompt to run.

## Required completion format

End the run with:

- **Starting SHA**
- **Working tree state before**
- **Defects reproduced**
- **Root cause**
- **Files changed**
- **Schema/API/contract changes**
- **Tests added or changed**
- **Commands run**
- **Pass/fail results**
- **Evidence artifacts produced**
- **Known remaining risks**
- **GO / NO-GO for this prompt**
- **Recommended next prompt**


## Objective

Remove the known deterministic CI failures **without hiding regressions**. Preserve the new v2 functionality while restoring a coherent, explicitly versioned API contract and responsive Result Detail behavior.

## Inspect at minimum

- `.github/workflows/*`
- `app/schemas/potential_customer_search.py`
- `app/routers/potential_customer_search.py`
- `app/services/potential_customer_search_submission_service.py`
- `app/services/phase11_results_service.py`
- `tests/test_phase11_api_backward_compatibility.py`
- `tests/test_phase11_results_history_detail.py`
- all tests asserting exact status payload keys
- `frontend/js/business-search-status.js`
- `frontend/js/run-progress.js`
- relevant Result Detail HTML/CSS
- responsive/browser tests

## Workstream A — API contract

Reproduce the failing legacy status-contract test.

Determine the intended public contract from:
- existing route versioning;
- OpenAPI schemas;
- previous Phase 11 compatibility evidence;
- current v2 additions.

Implement one coherent approach:

**Preferred:** preserve a stable legacy/v1 projection where legacy clients/tests require it, and expose additive v2 fields through an explicitly versioned response or clearly versioned endpoint/schema.

Alternative: if repository contracts already explicitly permit additive fields, update tests/docs to reflect that policy, but only if you can prove the compatibility contract really changed intentionally.

Do not simply weaken exact-key assertions because tests fail.

Verify:
- create;
- GET run;
- GET status;
- history;
- result detail;
- OpenAPI generation;
- v1 and v2 request/response round trips.

## Workstream B — responsive Result Detail

Reproduce the 390x844 overflow.

Identify the exact offending DOM element. Typical suspects:
- long SHA/reference text;
- definition-list grid min-width;
- progress metadata;
- buttons/action rows;
- unbreakable IDs;
- code-like technical fields.

Fix the component, not the test viewport.

Test at least:
- 390x844;
- 360x800;
- 768px tablet;
- desktop.

Require `document.documentElement.scrollWidth <= clientWidth` on mobile Result Detail.

## Workstream C — retry idempotency key fallback

Centralize a browser idempotency-key helper. Retry must not directly call `crypto.randomUUID()` when feedback already has a safe fallback.

Use:
- `crypto.randomUUID()` when available;
- `crypto.getRandomValues()` fallback;
- no `Math.random()` fallback.

Use the same helper for retry and feedback where sensible.

## Tests

Add/adjust tests proving:
- v1 contract remains stable or is deliberately versioned;
- v2 fields are available where promised;
- mobile page has no horizontal overflow;
- retry works in a browser context with `randomUUID` unavailable but `getRandomValues` available;
- existing feedback key generation still works.

Run the exact previously failing test groups and the frontend/browser contract suite.

## Evidence

Write:
`docs/evidence/recovery_hardening/01_CI_API_MOBILE.md`

Include failing-before/passing-after test names and the final API contract decision.

## Acceptance gate

GO only when the deterministic exact-SHA failures addressed by this prompt are green. Do not claim repository-wide CI green until Prompt 19.
