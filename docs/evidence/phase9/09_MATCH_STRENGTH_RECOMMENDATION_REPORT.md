# Phase 9 Step 9 — Match-Strength Recommendation Report

Date: 2026-09-09
Status: PASS

## Scope

This step adds an exact match-strength comparison and deterministic recommendation to the READY Target Group Preview. It does not train a model, run scoring, sample people, change saved targeting preferences, save a target group, create a campaign, or start Phase 9 Step 10.

## Exact comparison

`GET /api/campaign-planner/contexts/{id}/match-strength-recommendation` compares, in fixed order:

- Very Strong Match — 0.90+;
- Strong Match — 0.80+;
- Good Match — 0.70+; and
- Broad Match — 0.60+.

For each option, the response provides:

- the exact matching count;
- the exact percentage of the available population;
- the count change from the current match-strength choice;
- Narrower, Current, or Broader relative to the current choice; and
- whether the option is recommended.

All non-strength criteria remain unchanged for every comparison. A saved TOP_N selection is deliberately ignored for the comparison count because the panel compares all people who match each strength, not the later selection cap.

Each count is computed through the existing Phase 9 adapter around the Phase 6 normalization, predicate-building, exact member-materialization, and canonical-preparation checks. Disjoint age and income branches retain their existing exact union and de-duplication behavior. No count is sampled, approximated, inferred from a score-band summary, or copied from stale data.

## Versioned deterministic rule

The public contract version is `1` and the recommendation-rule version is `1`.

Rule version 1 is evaluated in this order:

1. Recommend **Very Strong Match** only when its exact count meets the higher Very Strong sufficiency count.
2. Otherwise recommend **Strong Match** when its exact count meets the practical minimum.
3. Otherwise recommend **Good Match** when its exact count meets the practical minimum.
4. If only **Broad Match** meets the practical minimum, return `REVIEW_REQUIRED` and do not select Broad automatically.
5. If Broad is also below the practical minimum, return `REVIEW_REQUIRED` and state that all match-strength options are too small.

The two configurable inputs are:

- `MATCH_STRENGTH_RECOMMENDATION_MINIMUM_COUNT`, default `1000`; and
- `MATCH_STRENGTH_VERY_STRONG_MINIMUM_MULTIPLIER`, default `2.0`.

The resolved Very Strong sufficiency count is:

`ceil(practical minimum count × Very Strong minimum multiplier)`

Both configuration values are validated at application startup, documented in `.env.example` and `README.md`, and returned with the recommendation so the decision is auditable. The response also includes a stable reason code: `VERY_STRONG_USABLE`, `STRONG_USABLE`, `GOOD_USABLE`, `BROAD_ONLY_USABLE`, or `ALL_TOO_SMALL`.

## Business presentation

The comparison panel appears within Target Group Preview and displays four cards with exact matching people, percentage of available people, change from the current choice, and the Narrower/Current/Broader relationship. The recommended card is highlighted. When no automatic recommendation is allowed, the panel shows **Review needed** and explains whether only Broad is usable or every option is too small.

The browser displays the rule version, practical minimum, and resolved Very Strong sufficiency count without requiring the user to interpret model mathematics. It avoids precision, recall, classifier-threshold, ROC/AUC, calibration, and posterior-probability terminology.

The mandatory disclaimer is returned by the backend and rendered by the browser exactly as:

> Higher match strength means greater similarity under the current targeting intelligence; it does not guarantee a purchase or response.

## Readiness and sequential flow

The recommendation uses the same READY gate as the exact target-group preview. Missing, stale, incompatible, or unprepared targeting intelligence returns the existing blocked response and no comparison count.

For a READY context, the browser performs these operations sequentially:

1. load the exact target-group preview;
2. load the exact match-strength comparison and recommendation; and
3. load the first privacy-safe target-group page.

Review & Save remains disabled until all three operations succeed. No browser requests introduced by Step 9 are run in parallel.

## Tests and evidence

The focused suite proves:

- exact counts of 3, 4, 5, and 5 for the four strengths in the six-person fixture;
- exact available-population percentages;
- TOP_N does not cap comparison counts;
- deterministic repeated responses;
- all five rule outcomes;
- no silent Broad fallback;
- successful response-model validation;
- the READY source gate returns HTTP 409 when blocked;
- sequential browser request ordering; and
- required business language with prohibited model terminology absent from the panel implementation.

## Files

- `.env.example`
- `README.md`
- `app/config.py`
- `app/routers/campaign_targeting.py`
- `app/schemas/campaign_targeting.py`
- `app/services/match_strength_recommendation_service.py`
- `frontend/index.html`
- `frontend/css/components.css`
- `frontend/js/target-group-preview.js`
- `tests/test_phase9_match_strength_recommendation.py`

## Verification

- `python -m pytest tests/test_phase9_match_strength_recommendation.py -q` — 8 passed.
- Complete Phase 9 test sequence through Step 9 — 39 passed.
- `python -m pytest tests/test_frontend.py -q` — 37 passed.
- `python -m compileall -q app tests` — passed.
- `git diff --check` — passed; Git emitted only existing line-ending warnings for `.env.example` and `README.md`.

Ruff and Node.js are not installed in this environment. The available Python compilation, exact service/API tests, served frontend integration tests, UI contract assertions, and repository diff validation passed.

No project data import, audience preparation, model training, or scoring process was run. Automated tests used isolated temporary SQLite fixtures and their local preparation records only.

## Acceptance result

PASS. Business users can compare exact target-group sizes across all four match strengths and receive transparent, reproducible guidance without model-evaluation terminology or a silent lowering of standards.

STOP — no Phase 9 Step 10 work was performed.
