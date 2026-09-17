# Phase 11 Step 8 — Find Potential Customers single business form

Date: 2026-09-17  
Baseline preserved: `881b5a652e869af1415547de452b9cccd2c18293`

## Outcome

The normal **Find Potential Customers** route now presents one business request form instead of the five-screen technical planner. The original planner source, modules, IDs and API contracts remain present inside a hidden legacy shell and have an explicit test-harness initializer; they were not deleted or presented as an authorization control.

The form has four sections and one primary action:

1. Campaign Details — required name, optional description and planned launch date.
2. Campaign Context — Products, Campaign Types, Campaign Categories, Offer Types and Historical Campaign Channels.
3. Targeting Preferences — Match Strength, Gender, Age Groups, State and Region shortcut, Income Groups, optional Top Matching %, `ALL_MATCHING`/`TOP_N`, and target count. Six advanced demographic selectors and family-size bounds are collapsed under **More options**.
4. Delivery / Download Profile — current backend-registry profiles only; available profiles are selectable, while a previously selected unavailable profile is shown disabled with a reason. The UI explains that delivery choice does not retrain targeting intelligence and that contactability is evaluated later.

The only submit action is **Find Potential Customers**.

## Contracts and lineage

- Values come from the existing Phase 9 context/targeting option services and the Phase 11 omnichannel registry. The frontend contains labels and field mappings, not invented option values.
- The shared Step 7 component enhances all 16 multi-select fields. Products remain required. Unavailable draft choices remain visible and disabled until the user explicitly removes them.
- Region is only a business shortcut that adds its backend-owned States. `regions` is not persisted as an analytical criterion.
- Criteria use the unchanged Phase 9 normalizer. A value list is OR-ed within a field; the generated branches retain AND-across-field semantics and preserve disjoint age/income ranges.
- Every accepted intentional submission creates a fresh immutable context/criteria row and a separate `campaign_search_runs` row before the executor handoff. Repeat submissions are therefore separately discoverable rather than silently overwriting earlier intent.
- The additive `PHASE11_1` campaign-context representation permits all registry-owned delivery channels while retaining the five frozen Phase 9 analytical dimensions and their live-reference validation. The frozen Phase 9 request/API enum remains unchanged.
- Modeling Context identity is derived only from Products, Campaign Types, Campaign Categories, Offer Types and Historical Campaign Channels. Tests prove that delivery profile/channel and prospect-filter changes do not change this hash.
- The search run records campaign details, context ID, Modeling Context hash, canonical criteria and checksum, exact filter branches and checksum, selection mode/count, channel/profile and status. Status/history responses expose a small allowlist and fixed safe messages; no criteria or PII are returned.
- Request models reject unknown fields, invalid dates, invented reference selections, unavailable/mismatched profiles, impossible numeric bounds and invalid selection combinations before persistence.
- Results history uses durable database records with newest-first keyset pagination. A submitted request remains discoverable after navigating away and after page reload.
- Submission locks the form against duplicate in-flight intent. A late acknowledgement does not force the user away from a route they deliberately opened.

## Smart-reuse boundary

Step 8 provides an explicit executor dependency seam. Step 9 now owns the exact-result → Phase 10 intelligence → new Phase 10 build decision and filtering engine; Step 11 still owns safe membership publication and the final production composition. With no complete executor composition installed:

- the form options truthfully report that preparation is unavailable;
- a valid request is still durably recorded;
- its run transitions to `BLOCKED` with a fixed business-safe explanation;
- no fake completed status, count, snapshot or result is created.

An isolated executor-hook test proves that a connected executor receives an already-durable exact run and may transition it to `PROCESSING`. Another test proves exceptions preserve the run as `FAILED` without exposing exception text. This is a tested handoff boundary, not a claim that the later Step 11/12 snapshot/results functionality is complete.

## UI states and safety

- Loading, option-load failure/retry, empty Products, unavailable prior values, invalid fields, saving, blocked acknowledgement, saved history and status-load failure have explicit states.
- Draft restoration uses a versioned, bounded session-storage shape and never silently converts removed business values.
- The form uses DOM text nodes for returned business metadata and fixed client messages for failures. Backend validation and executor exceptions are not reflected into the page.
- Delivery selection performs no preparation, training, scoring or API mutation. Only an intentional valid form submission creates a run.
- The visible form fits the tested 390 px mobile and 1280 px desktop widths without horizontal overflow.

## Verification

Focused Step 8 suite:

```text
.venv/Scripts/python.exe -m pytest tests/test_phase11_business_search_form.py -q
56 passed in 124.81s
```

The 56 cases include 17 installed-system-Chrome browser cases and backend/API tests for:

- real option/profile registry projection and unavailable-profile gating;
- all ten current profile/channel submissions under the additive context contract;
- canonical criteria, OR-within/AND-across branch lineage and Modeling Context identity;
- immutable repeat submissions, keyset history and database-backed status;
- invalid/unknown/stale values producing no context, run, snapshot, model or scoring writes;
- executor handoff, processing persistence and safe executor failure;
- the single form, collapsed advanced options, Region-to-State behavior and `TOP_N` reset;
- native/custom validation, corrected-error retry and unavailable-draft recovery;
- duplicate-submit locking, navigation during acknowledgement, reload discovery and intentional repeat submission;
- option failure/retry, empty Products, mobile/desktop overflow and absence of edit-triggered heavy calls.

Affected regression suite:

```text
.venv/Scripts/python.exe -m pytest \
  tests/test_phase11_business_navigation.py \
  tests/test_phase11_multi_select_dropdown.py \
  tests/test_frontend.py \
  tests/test_phase9_campaign_context.py \
  tests/test_phase9_business_targeting.py \
  tests/test_phase9_validation_and_states.py \
  tests/test_phase9_progressive_disclosure.py \
  tests/test_phase9_accessibility_responsive.py \
  tests/test_phase10_business_ui.py -q
116 passed in 165.64s
```

Python compile checks for the new schema/service/router completed successfully. `git diff --check` passed; the command emitted existing line-ending conversion warnings only.

Browser verification used installed headless system Chrome. Every browser request was intercepted into static repository assets or the real FastAPI app backed by a tiny temporary SQLite fixture. No remote traffic or canonical application server was used.

## No-heavy-work statement and stop

No canonical generation, import, reconciliation, historical analysis, training, scoring, ranking, preparation, result snapshot, export or activation was run. Tests used temporary databases and bounded fixture rows only.

Earlier uncommitted Phase 11 changes remain preserved. No staging, commit, push or freeze was performed.

`STOP_AFTER_STEP_08`

Step 9 was implemented subsequently; this Step 8 evidence remains scoped to the earlier form/submission boundary.
