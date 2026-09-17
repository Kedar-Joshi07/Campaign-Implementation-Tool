# Phase 11 Product Information Architecture

Generated: 2026-09-16

Prompt: `Prompts/phase11_business_workflow_omnichannel_smart_reuse_prompt_pack/02_STEP_02_PHASE11_PRODUCT_INFORMATION_ARCHITECTURE.md`

Baseline: `881b5a652e869af1415547de452b9cccd2c18293`

## Step result

`PASS_STEP_02_PHASE11_PRODUCT_INFORMATION_ARCHITECTURE`

This document freezes the normal-user product flow before backend or UI
implementation begins. Step 6 implements this contract. Step 2 does not change
the current DOM, router, APIs, legacy modules, tests, data, or runtime behavior.

## Normative product decisions

### IA-01: normal-user navigation

The normal business navigation contains exactly three top-level destinations,
in this order:

1. **Home**
2. **Find Potential Customers**
3. **Results**

There is no normal-user navigation group called Advanced, Analyst, Technical,
Model Management, Campaigns, Insights, or Saved Target Groups.

### IA-02: hidden capabilities remain intact

The following views are removed from normal navigation and from visible
business-route entry points, but their source, DOM, APIs, and regression
coverage are retained:

| Existing view key | Existing DOM ID | Frozen group | Normal navigation |
|---|---|---|---|
| `saved-target-groups` | `saved-target-groups-view` | `ANALYST_HIDDEN` | Hidden |
| `campaigns` | `campaigns-view` | `ANALYST_HIDDEN` | Hidden |
| `insights` | `insights-view` | `ANALYST_HIDDEN` | Hidden |
| `historical-analysis` | `historical-analysis-view` | `ANALYST_HIDDEN` | Hidden |
| `audience-explorer` | `audience-explorer-view` | `ANALYST_HIDDEN` | Hidden |
| `data-status` | `data-status-view` | `ADMIN_HIDDEN` | Hidden |
| `model-training` | `model-training-view` | `ADMIN_HIDDEN` | Hidden |

UI hiding is not authorization. Hiding is a presentation decision only; it is
not authentication, access control, or RBAC. Phase 11 does not implement any of
those controls. Existing backend endpoints remain callable under their existing
contracts.

### IA-03: business route and state contract

| Contract key | State | Canonical fragment | DOM view | Top navigation | Title |
|---|---|---|---|---|---|
| `home` | `HOME` | `#home` | `overview` / `overview-view` | Yes | Home |
| `find-potential-customers` | `FIND_POTENTIAL_CUSTOMERS` | `#find-potential-customers` | `campaign-planner` / `campaign-planner-view` | Yes | Find Potential Customers |
| `results` | `RESULTS` | `#results` | `results` / `results-view` | Yes | Results |
| `result-detail` | `RESULT_DETAIL` | `#results/<run-id>` | `result-detail` / `result-detail-view` | No; Results remains selected | Result Details |

`<run-id>` is an opaque, path-safe search-run identifier. Its persistence type
is owned by Step 5; the frontend must not infer chronology or business meaning
from its representation.

Startup with an empty fragment opens `HOME` and normalizes the URL to `#home`.
An unknown or malformed fragment redirects to `#home` using history
replacement, not an additional history entry.

### IA-04: old-fragment behavior

Phase 11 chooses a single redirect strategy rather than leaving hidden views
directly addressable through browser fragments.

| Incoming fragment | Result |
|---|---|
| empty, `#`, `#home` | `HOME` |
| `#overview` | Replace with `#home` |
| `#campaign-planner` | Replace with `#find-potential-customers` |
| `#saved-target-groups` | Replace with `#home` |
| `#campaigns` | Replace with `#home` |
| `#insights` | Replace with `#home` |
| `#data-status` | Replace with `#home` |
| `#historical-analysis` | Replace with `#home` |
| `#model-training` | Replace with `#home` |
| `#audience-explorer` | Replace with `#home` |
| any unknown fragment | Replace with `#home` |

The two business aliases preserve useful bookmarks while adopting the new
language. Hidden analyst/admin fragments redirect to Home consistently. Their
DOM and JavaScript remain in source for regression and future governed role
exposure. This redirect is still not authorization; a future RBAC phase must
enforce access independently.

### IA-05: centralized view-group contract

Step 6 must add `frontend/js/view-contract.js` as the single authority for view
grouping, business states, titles, hashes, DOM mappings, and top-navigation
membership. `frontend/js/app.js` consumes it; scattered allow/deny lists and
one-off CSS hiding are prohibited.

The contract shape is frozen as follows. Exact syntax may be adjusted only to
meet the existing lint/runtime target without changing these semantics.

```javascript
export const VIEW_GROUPS = Object.freeze({
  BUSINESS_USER_VISIBLE: "BUSINESS_USER_VISIBLE",
  ANALYST_HIDDEN: "ANALYST_HIDDEN",
  ADMIN_HIDDEN: "ADMIN_HIDDEN",
});

export const BUSINESS_VIEW_STATES = Object.freeze({
  HOME: "HOME",
  FIND_POTENTIAL_CUSTOMERS: "FIND_POTENTIAL_CUSTOMERS",
  RESULTS: "RESULTS",
  RESULT_DETAIL: "RESULT_DETAIL",
});

export const VIEW_DEFINITIONS = Object.freeze({
  home: {
    state: BUSINESS_VIEW_STATES.HOME,
    group: VIEW_GROUPS.BUSINESS_USER_VISIBLE,
    hash: "#home",
    domView: "overview",
    title: "Home",
    showInNavigation: true,
  },
  "find-potential-customers": {
    state: BUSINESS_VIEW_STATES.FIND_POTENTIAL_CUSTOMERS,
    group: VIEW_GROUPS.BUSINESS_USER_VISIBLE,
    hash: "#find-potential-customers",
    domView: "campaign-planner",
    title: "Find Potential Customers",
    showInNavigation: true,
  },
  results: {
    state: BUSINESS_VIEW_STATES.RESULTS,
    group: VIEW_GROUPS.BUSINESS_USER_VISIBLE,
    hash: "#results",
    domView: "results",
    title: "Results",
    showInNavigation: true,
  },
  "result-detail": {
    state: BUSINESS_VIEW_STATES.RESULT_DETAIL,
    group: VIEW_GROUPS.BUSINESS_USER_VISIBLE,
    hashPattern: "#results/<run-id>",
    domView: "result-detail",
    title: "Result Details",
    showInNavigation: false,
    parentNavigation: "results",
  },
  // Existing retained views use ANALYST_HIDDEN or ADMIN_HIDDEN.
});
```

The module also owns immutable `BUSINESS_NAVIGATION`, legacy alias metadata,
and pure route-resolution helpers. A visibility group is metadata for future
role mapping; it must not be presented as a security decision.

### IA-06: frozen business copy

| Context | Required default copy | Prohibited default copy |
|---|---|---|
| Population noun | Potential Customers | prospects |
| Primary search action | Find Potential Customers | Create Campaign, Build Audience, Score Prospects |
| Search history | Results | Scoring Results, Saved Audiences, Saved Target Groups |
| Preparation status/help | Targeting intelligence | model training, scoring job, PU model, rank build |
| Detail page | Result Details | Audience Explorer |

“Targeting intelligence” may appear in progress text, help, or an explicitly
expanded technical-details disclosure. It is not a top-level normal-user
navigation label. Model, scoring, rank, artifact, compatibility, generation,
and checksum language stays out of the default business surface and may remain
inside progressive technical disclosure.

## Frozen wireflow

```text
Application start / logo
          |
          v
        HOME  ---------------- primary CTA ----------------+
          |                                                  |
          | top navigation                                   v
          +---------------------------------> FIND POTENTIAL CUSTOMERS
          |                                                  |
          |                                                  | submit once
          |                                                  v
          |                                      SEARCH RUN / PROGRESS
          |                                                  |
          |                                      completed or failed
          |                                                  v
          |                                             RESULT DETAIL
          |                                                  |
          |                                    governed download / refine
          |                                                  |
          | top navigation                                   |
          v                                                  |
       RESULTS -------- select immutable run ----------------+
          |
          +-------- newest-first history; every submission visible
```

Behavioral rules:

- Home has one primary **Find Potential Customers** CTA.
- Submitting the form creates a run before any reuse/build outcome is known.
- Progress is business-safe and uses “Preparing targeting intelligence” where
  technical preparation must be described.
- Completion opens Result Details for the submitted run.
- Failure remains an inspectable Result Details state rather than disappearing.
- Results lists every run newest first, including running, failed, completed,
  reused, and newly built outcomes.
- Selecting a Results row opens its immutable Result Details route.
- Download is available only from a completed/current result under the governed
  profile-specific export contract implemented later.
- Refine/new search returns to Find Potential Customers and creates a new run on
  the next intentional submission.

## Current DOM and control inventory

This inventory is descriptive of the frozen Phase 10 baseline. It is not an
instruction to delete hidden content.

### Global shell and current navigation

| Surface | Current selector/control |
|---|---|
| Shell | `.app-shell`, `aside.sidebar`, `main#main-content` |
| Brand/home link | `a.brand[href="#overview"]` |
| Navigation | `nav.navigation[aria-label="Application sections"]` |
| Page identity | `#page-title`, document title |
| Runtime status | `#backend-status`, `#backend-status-text` |
| Current business group label | “Business Workspace” |
| Current technical group label | “Advanced / Analyst Tools” |

Current navigation controls are `data-view-target="overview"`,
`campaign-planner`, `saved-target-groups`, `campaigns`, `insights`,
`data-status`, `historical-analysis`, `model-training`, and
`audience-explorer`.

### Current Home source

The reusable Home source is `#overview-view[data-view="overview"]`.

| Area | Controls/regions |
|---|---|
| Error/retry | `#overview-error`, `#overview-error-message`, `#overview-retry` |
| Heading/action | `#overview-title`, `#overview-refresh` |
| Business metrics | `#customer-count`, `#campaign-sales-count`, `#demographic-count`, `#distinct-campaigns`, `#distinct-products`, `#known-positive-count` |
| Health/readiness | `#overview-health-badge`, `#application-health`, `#database-health`, `#schema-health`, `#readiness-spinner`, `#readiness-note` |
| Historical overview | `#historical-overview-title`, `#historical-overview-loading`, `#historical-overview-empty`, `#historical-overview-unavailable`, `#historical-overview-content` |
| Visible legacy entry point | `#historical-analysis-cta[data-view-target="historical-analysis"]` |

The visible historical-analysis CTA violates the target IA. Step 6 replaces it
with a Home **Find Potential Customers** CTA; Step 14 later completes the
business-safe Home dashboard.

### Current Find Potential Customers source

The reusable source is
`#campaign-planner-view[data-view="campaign-planner"]`. Its present five-step
shell is retained until Step 8 composes it into the single business form.

| Area | Existing DOM contract |
|---|---|
| Heading/draft/progress | `#campaign-planner-title`, `#planner-save-draft`, `#planner-progress-label`, `#planner-current-step-name`, `#planner-draft-status` |
| Step navigation | `#planner-step-1` through `#planner-step-5`; `#planner-step-panel-1` through `#planner-step-panel-5` |
| Campaign details | `#planner-campaign-details-form`, `#planner-campaign-name`, `#planner-campaign-description`, `#planner-planned-launch-date` |
| Campaign context | `#planner-context-form`, `#planner-context-products`, `#planner-context-types`, `#planner-context-categories`, `#planner-context-offers`, `#planner-context-delivery-channel`, `#planner-context-historical-channels` |
| Targeting | `#planner-targeting-form`; controls under `#planner-targeting-*` for strength, gender, age, state, region, income, advanced criteria, family size, percentage, selection mode, and target count |
| Preparation/progress | controls under `#planner-intelligence-*`, including status, explanation, reuse message, progress bar, retry, and technical details |
| Preview | controls under `#planner-target-preview-*`, `#planner-preview-*`, and `#planner-match-*` for exact counts, explanation, comparisons, profile, and privacy-safe rows |
| Review/save | `#planner-review-*`, `#planner-save-target-group-form`, `#planner-target-group-name`, `#planner-target-group-description`, `#planner-save-target-group`, `#planner-save-success` |
| Accessibility status | `#planner-status-announcement` |

Step 2 changes none of these controls. Later steps may compose or relabel them
but must preserve backend values, currentness, accessibility, and multi-branch
semantics.

### Existing visible legacy entry points

In addition to the nine sidebar buttons, the baseline contains these route
controls that Step 6 must remove from the normal business surface or redirect
through the centralized contract:

| Location | Current control | Current destination |
|---|---|---|
| Home historical overview | `#historical-analysis-cta` | `historical-analysis` |
| Audience Explorer reopen guidance | unnamed buttons | `saved-target-groups`, `campaign-planner` |
| Saved Target Groups | unnamed primary button | `campaign-planner` |
| Insights | unnamed buttons | `historical-analysis`, `audience-explorer` |

Controls inside already-hidden retained views may remain for regression use,
but `app.js` must never make their old fragments visible in the normal business
router. The Home CTA is replaced because Home remains visible.

## Target DOM and control inventory

Step 6 implements the following shell. Results content is initially an honest
shell and is completed by Step 12.

| Surface | Required target |
|---|---|
| Primary navigation | `#business-navigation.navigation`, labelled “Primary business navigation” |
| Home control | `#nav-home[data-view-target="home"]`, label “Home” |
| Find control | `#nav-find-potential-customers[data-view-target="find-potential-customers"]`, label “Find Potential Customers” |
| Results control | `#nav-results[data-view-target="results"]`, label “Results” |
| Home view | retained `#overview-view`, mapped by contract to `HOME` |
| Home primary CTA | `#home-find-potential-customers[data-view-target="find-potential-customers"]` |
| Find view | retained `#campaign-planner-view`, mapped to `FIND_POTENTIAL_CUSTOMERS` |
| Results history shell | new `#results-view[data-view="results"]` with `#results-title`, `#results-status`, and `#results-empty` |
| Result detail shell | new `#result-detail-view[data-view="result-detail"]` with `#result-detail-title`, `#result-detail-status`, and `#result-detail-back` |
| Advanced retained views | existing sections remain in DOM/source with centralized hidden-group metadata and `hidden` state |

Active-state rules:

- exactly one top-level navigation item has `.is-active` and
  `aria-current="page"`;
- Result Details keeps Results active;
- hidden views never receive normal-navigation active state;
- route normalization must not create a hash-change loop;
- browser back/forward traverses Home, Find Potential Customers, Results, and
  Result Details predictably.

## Step 6 implementation and regression handoff

Step 6 must:

1. add and consume `frontend/js/view-contract.js`;
2. replace the static nine-link navigation with the exact three-link business
   navigation;
3. preserve hidden view sections and legacy JavaScript modules;
4. normalize old/unknown fragments using IA-04;
5. add honest Results and Result Details shells without inventing backend data;
6. replace the visible Home legacy CTA with the frozen primary action;
7. preserve API routes and avoid security/RBAC claims; and
8. update tests that currently equate legacy capability presence with visible
   navigation.

Known regression assertions requiring deliberate separation of “source exists”
from “normal nav is visible” include:

- `tests/test_frontend.py::test_navigation_groups_and_phase7_shell_labels_are_visible`;
- `tests/test_frontend.py::test_historical_analysis_navigation_and_workspace_are_enabled`;
- current Campaign Planner title assertions in `tests/test_frontend.py`;
- `tests/test_phase3_hardening.py::test_phase5_api_surface_includes_scoring_and_step7_navigation_state`;
- the legacy view-presence assertions later in `tests/test_phase3_hardening.py`;
- `tests/test_phase9_progressive_disclosure.py::test_business_navigation_exposes_saved_target_groups_and_insights`.

Tests must continue proving that the retained sections, modules, and APIs exist,
while new Phase 11 assertions prove that they are absent from normal business
navigation and cannot be opened through the normal hash router.

## Non-goals and preserved boundaries

- No authentication, authorization, RBAC, or security claim.
- No deletion of legacy DOM, JavaScript, API, test, or analytical behavior.
- No backend, schema, repository, database, source-data, model, scoring, rank,
  snapshot, or export change.
- No Step 7 multi-select implementation.
- No Step 8 single-form implementation.
- No Step 9 reuse engine.
- No Step 12 Results data/history implementation.
- No fake run/result data in the new shells.

## Execution declaration and stop boundary

- Information architecture: frozen.
- Centralized view-group contract: specified for Step 6 implementation.
- Business routes/states: frozen.
- Legacy fragment strategy: redirect to Home, documented as non-security.
- Copy contract: frozen.
- Wireflow: created.
- Current and target DOM/control inventories: created.
- Runtime feature implementation: not started in this step.

`STOP_AFTER_STEP_02`
