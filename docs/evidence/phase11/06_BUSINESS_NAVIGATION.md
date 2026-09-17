# Phase 11 Step 6 — Business Navigation

Date: 2026-09-16

Prompt: `Prompts/phase11_business_workflow_omnichannel_smart_reuse_prompt_pack/06_STEP_06_HIDE_LEGACY_UI_AND_ADD_BUSINESS_NAVIGATION.md`

Frozen information architecture: [Step 2 evidence](02_PRODUCT_INFORMATION_ARCHITECTURE.md).

Baseline HEAD: `881b5a652e869af1415547de452b9cccd2c18293`. This is local, uncommitted Step 6 evidence, not an exact-SHA release/CI certification. Existing Phase 11 Steps 3–5 worktree changes are preserved.

## Result

`PASS_STEP_06_BUSINESS_NAVIGATION`

Normal navigation contains exactly Home, Find Potential Customers, Results, in that order. Default startup opens Home. The Home primary CTA and brand use the business router. Result Details selects Results in navigation, without becoming a fourth top-level destination.

## Implementation and preserved boundaries

- `frontend/js/view-contract.js` is the central, immutable authority for groups, business states, titles, DOM mappings, navigation membership/order, aliases, and route resolution. `app.js` consumes it; DOM rules also hide non-business route controls consistently. No element-specific CSS hiding was added.
- Group metadata is `BUSINESS_USER_VISIBLE`, `ANALYST_HIDDEN`, and `ADMIN_HIDDEN`. This provides a future role-aware presentation seam, not role implementation.
- All seven retained legacy view sections remain in the HTML, initially hidden. Their modules, initialization handlers, and analytical/API behavior remain in source. Static legacy sidebar links are replaced, not mistaken for the capabilities themselves.
- `loadLegacyWorkspace` is an explicit ES-module regression/future-exposure seam. Normal hash routing never calls a legacy loader or reveals a legacy view. The harness loads the retained modules and invokes the read-only Saved Target Groups loader without changing the visible business view.
- The existing five-step planner is retained and its heading now reads Find Potential Customers. Step 8 owns conversion to the single business form; this step does not implement or claim it.
- Results and Result Details have accessible, honest navigation-only shells. They explicitly say history/details are not connected; no fake results, currentness, search submissions, or downloads are supplied. Step 12 owns real history/detail integration.
- Existing frontend regression assertions now distinguish retained capability presence from normal-navigation visibility. Analytical safety, provenance, PII, API, and legacy DOM/module assertions remain in coverage.
- The frontend TestClient fixture redirects both dependency resolution and application-startup database paths to the same temporary fixture. No runtime recovery/scans are allowed accidentally through a request-only override.

UI hiding is not authentication, authorization, access control, security, or RBAC. Existing endpoints remain callable under their existing contracts. A future RBAC implementation must independently enforce API access.

## Routing strategy

One consistent strategy is used: hidden internal fragments redirect to Home; hidden pages are not made publicly navigable with an advanced label.

| Incoming fragment | Canonical destination |
|---|---|
| Empty, `#`, `#home` | `#home` |
| `#overview` | `#home` |
| `#campaign-planner` | `#find-potential-customers` |
| `#find-potential-customers` | Unchanged |
| `#results` | Unchanged |
| `#results/<positive-integer-run-id>` | Result Details; Results remains selected |
| `#saved-target-groups`, `#campaigns`, `#insights`, `#historical-analysis`, `#audience-explorer`, `#data-status`, `#model-training` | `#home` |
| Unknown/malformed fragment | `#home` |

Step 5 allocates positive integer run IDs; routing treats their path-safe string representation as opaque and does not infer chronology or convert it to a JavaScript number. Details are not fetched in Step 6.

Normalization uses `history.replaceState`, so aliases, empty startup, and invalid/hidden fragments do not add redirect history entries or hash-change loops. Intentional navigation uses hash history. Back/forward, detail/back, brand navigation, repeated active-item clicks, and exactly one active `aria-current="page"` navigation item are tested.

## Sequential verification

Final command:

```powershell
.venv/Scripts/python.exe -m pytest -q tests/test_frontend.py tests/test_phase3_hardening.py tests/test_phase9_progressive_disclosure.py tests/test_phase9_accessibility_responsive.py tests/test_phase9_validation_and_states.py tests/test_phase10_business_ui.py tests/test_phase11_business_navigation.py
```

Result: **95 passed in 102.83 seconds**. This includes all **28** new Step 6 cases; counts are overlapping, not additive.

Final hygiene checks passed: targeted Python compileall, tracked Step 6 textual `git diff --check`, and trailing-whitespace scans of the new contract, tests, and evidence. `git diff --name-only -- app/routers app/main.py` was empty, confirming no API-router or application-entrypoint implementation changes. Git emitted only its existing README CRLF-to-LF normalization warning.

The new coverage proves:

- exact three-item navigation, retained hidden DOM, and explicit non-security documentation;
- legacy API paths remain registered in the application's OpenAPI contract;
- 24 startup/deep-link cases covering business destinations, aliases, all seven hidden routes, and malformed/unknown/prototype-name fragments;
- browser hash/history behavior and Results-active detail routing;
- frozen contract/navigation metadata and retained modules importing successfully in a real JavaScript module environment;
- the explicit legacy loader remains usable by the harness without exposing a hidden route;
- normal navigation requests do not invoke legacy model/audience/campaign endpoints or workflow mutations;
- existing Phase 9 validation, accessibility, progressive disclosure and Phase 10 preparation UI contracts are preserved.

Browser tests use the repository's installed-system-browser launcher, headless, with isolated temporary profile/download directories. Every request is intercepted: static HTML/CSS/JS comes from the working tree; API requests receive an intentional safe 503 response. No application server or runtime database is connected. This is navigation/module certification, not the later real-backend business-flow certification. Browser cases carry the existing `browser` marker and are excluded by the ordinary CI non-browser test gate; no remote CI-green claim is made here.

Initial verification found one defect in the new test itself: the current framework exposes included-router wrappers rather than a flat `app.routes` path list. The assertion was corrected to inspect `app.openapi()["paths"]`. No API implementation change was needed. A prior standalone run of the new tests also passed 28/28; the final suite reverified them after final presentation/marker changes.

Windows sandbox subprocess pipes blocked Playwright initially. The bounded intercepted-browser test commands ran with reviewed escalation; no project database, imports, analytical jobs, or heavy work were used.

## Scope and stop declaration

No backend router/API handler, database schema, repository, synthetic source, analytical contract, model, score, rank, snapshot artifact, or export implementation was changed by Step 6. No canonical generation, import, training, scoring, ranking, result build, or export was run. Earlier-step work remains uncommitted and preserved.

`STOP_AFTER_STEP_06`

Step 7 and subsequent prompt execution have not started. No staging, commit, push, or release freeze was performed.
