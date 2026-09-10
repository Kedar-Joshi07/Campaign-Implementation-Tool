# Phase 9 Step 8 — Target Group Preview Report

Date: 2026-09-09
Status: PASS

## Scope

This step implements the exact, business-friendly Target Group Preview over the existing Phase 6 Audience Engine. It does not train a model, run scoring, choose a scoring source, save a target group, create a campaign, or advance to Phase 9 Step 9.

## Readiness and currentness gate

Preview and search are available only when the explicitly linked targeting-intelligence source resolves to `READY`. The Step 7 resolver now also requires the Phase 6 rank boundaries and analytics snapshot to be current and prepared. A completed scoring run whose audience preparation is absent or stale resolves to `NEEDS_REFRESH` rather than failing after the preview gate opens.

The browser keeps the existing source-boundary presentation for all required states:

- `READY` — the exact preview is shown with an **Up to date** badge;
- `NEEDS_REFRESH` or `STALE` — **Targeting intelligence needs refresh** is shown and preview remains blocked; and
- `NOT_AVAILABLE` or `INCOMPATIBLE_CONTEXT` — **Targeting is not yet available for this campaign** is shown and preview remains blocked.

No estimated, sampled, fallback, or fabricated count is displayed for a blocked state. Technical source IDs and checksums remain under Advanced technical details and are not shown in the default preview.

## Exact Phase 6 adapter

`app/services/target_group_preview_service.py` is a view-model adapter over the existing Phase 6 preparation, normalization, filter-predicate, materialization, profile, percentile, and canonical-currentness functions.

The adapter does not reproduce propensity-query or demographic-profile rules. It adds only the Phase 9 behavior needed to preserve the Step 6 business contract:

1. Each normalized age/income branch is materialized with the Phase 6 filter engine.
2. Branch results are unioned by `person_id` with a unique index, preserving OR semantics without duplicates.
3. If TOP_N is requested, the union is ranked once by `propensity_score DESC, person_id ASC` and the exact requested prefix is selected.
4. The Phase 6 profile helper computes matching and selected summaries and demographic distributions from the materialized tables.

This is important for disjoint selections. For example, selecting 25–34 and 45–54 does not widen the request to include 35–44. Tests combine disjoint age and income selections and verify the exact expected people, counts, and score statistics.

## Exact preview contract

`GET /api/campaign-planner/contexts/{id}/target-group-preview` returns:

- Potential Customers Available;
- Matching Your Preferences;
- Selected for Target Group;
- % of Available People;
- Average Targeting Match Score;
- Strongest Match;
- Lowest Selected Match;
- five non-overlapping score bands: 0.90–1.00, 0.80–<0.90, 0.70–<0.80, 0.60–<0.70, and 0.00–<0.60;
- Age Mix, Gender Mix, Where They Are Located, and Income Mix;
- advanced demographic mixes only when the corresponding advanced criterion was selected; and
- a deterministic plain-language explanation.

The test fixture reconciles exactly to six available people, two matching people, two selected people, a 33.333…% available share, a 0.85 average score, a 0.94 strongest match, and a 0.76 lowest selected match. The five score-band counts reconcile to the selected total.

The explanation is derived only from saved campaign context, source category/readiness, selected match strength, and its versioned threshold. It states that scores express similarity for ranking and do not establish why a person will act or predict a purchase outcome. It does not claim causality.

## Privacy-safe search and deterministic pagination

`POST /api/campaign-planner/contexts/{id}/target-group-search` uses the Phase 6 stable ordering and an opaque keyset cursor bound to:

- targeting context ID;
- explicitly linked scoring run ID;
- targeting-criteria SHA-256;
- last score; and
- last potential-customer ID.

A cursor cannot be replayed against another context, source, or criteria definition. Page results are ordered by score descending and potential-customer ID ascending. The test traverses one-row pages and proves that the complete result is ordered and contains no duplicate IDs.

The API permits only Potential Customer ID, Targeting Match Score, Top Matching %, Match Strength, and approved Phase 6 demographic attributes. The default browser table displays Potential Customer ID, score, top percentage, match strength, age, gender, state, and individual yearly income. It does not display names, email addresses, phone numbers, street addresses, customer IDs, or prohibited demographic fields.

## Browser flow

The Target Group Preview module subscribes to the targeting-intelligence resolution event. For a READY source it performs requests sequentially:

1. request and render the exact summary;
2. request and render the first privacy-safe page; and
3. request each later page only when the user selects **Load more potential customers**.

It includes loading, retry, error, empty, current, and additional-page states. Review & Save remains disabled until the exact summary and first page have both succeeded. A request-generation guard prevents an older response from replacing a newer context. The renderer also de-duplicates Potential Customer IDs defensively while the backend remains authoritative.

## Files

- `app/routers/campaign_targeting.py`
- `app/schemas/campaign_targeting.py`
- `app/services/target_group_preview_service.py`
- `app/services/targeting_intelligence_service.py`
- `frontend/index.html`
- `frontend/css/components.css`
- `frontend/js/campaign-planner-form.js`
- `frontend/js/target-group-preview.js`
- `frontend/js/targeting-intelligence.js`
- `tests/test_frontend.py`
- `tests/test_phase9_target_group_preview.py`
- `tests/test_phase9_targeting_intelligence_boundary.py`

## Verification

- `python -m pytest tests/test_phase9_target_group_preview.py -q` — 4 passed.
- Successful preview/search response-model validation and blocked-gate/invalid-cursor API test — passed.
- `python -m pytest tests/test_phase9_schema.py tests/test_phase9_targeting_contracts.py tests/test_phase9_campaign_context.py tests/test_phase9_business_targeting.py tests/test_phase9_targeting_intelligence_boundary.py tests/test_phase9_target_group_preview.py -q` — 31 passed.
- `python -m pytest tests/test_audience_query_service.py tests/test_audience_profile_service.py tests/test_audience_api.py tests/test_audience_profile_api.py -q` — 26 passed.
- `python -m pytest tests/test_phase9_targeting_intelligence_boundary.py tests/test_frontend.py -q` — 45 passed.
- `python -m compileall -q app tests` — passed.
- `git diff --check` — passed; Git emitted only the existing README line-ending warning.

Ruff and Node.js are not installed in this environment. The available Python compilation, backend/API suites, served-asset tests, frontend contract assertions, and repository diff validation passed.

## Acceptance result

PASS. A READY campaign context now produces an exact, current, privacy-safe, deterministic target-group preview and keyset-paginated search by adapting the Phase 6 Audience Engine. Blocked source states remain honest and do not expose a count.

STOP — no Phase 9 Step 9 work was performed.
