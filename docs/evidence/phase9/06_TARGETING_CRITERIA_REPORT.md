# Phase 9 Step 6 — Business Targeting Criteria Report

Date: 2026-09-09
Status: PASS

## Scope

This step implements business-friendly targeting-preference capture, backend validation, canonical persistence, and deterministic mapping to the existing Audience Filter Contract. It does not select or link targeting intelligence, run scoring, estimate a target group, search people, save a target group, or create a campaign draft.

## Implemented controls

The first visible controls are:

- Targeting Strength with backend-owned labels and thresholds:
  - Very Strong Match — 0.90+
  - Strong Match — 0.80+
  - Good Match — 0.70+
  - Broad Match — 0.60+
- Gender multi-select from current demographic values.
- Age Groups multi-select from versioned backend-owned age buckets.
- Location by State from current demographic values.
- Income Groups multi-select from versioned backend-owned income buckets.

The default recommendation is returned explicitly by the API. `GOOD` is marked as the recommended starting point, remains visible as an active chip, and can be changed by the user.

The progressively disclosed “More targeting options” section contains:

- marital status;
- education;
- employment status;
- resident status;
- resident type;
- type of employment;
- minimum and maximum family size;
- top matching percentage; and
- all-matching or TOP_N selection with a required target count for TOP_N.

No street, ZIP/postal-code, or city targeting control is present. Coarse Region was optional in the prompt and was not introduced; State remains the only Phase 9 location control.

## Backend flow

1. `GET /api/campaign-planner/targeting-options` returns versioned match-strength, age, and income definitions plus current categorical values read from `demographics`.
2. Missing/blank categorical demographic values are represented consistently with the Audience Filter Contract as `Unknown/Other`.
3. `PUT /api/campaign-planner/contexts/{id}/targeting-criteria` validates the complete business contract and rejects unknown current categorical values.
4. The existing Step 3 mapper converts the business criteria into normalized Audience Filter Contract branches and the existing audience-selection contract.
5. The canonical criteria JSON and SHA-256 digest replace only the targeting-criteria portion of the existing context record. Campaign context and scoring linkage are not changed.
6. `GET /api/campaign-planner/contexts/{id}/targeting-criteria` verifies the saved canonical JSON and digest, reconstructs the mapping, and returns the readable criteria.

## Mapping correctness

- Match strength maps to exact `score_min` values of 0.90, 0.80, 0.70, or 0.60.
- Dynamic business fields map to the corresponding existing categorical filter fields.
- Age and income buckets map to inclusive numeric filter bounds.
- Adjacent selected buckets may be combined only when their union is contiguous.
- Disjoint selected buckets remain separate normalized OR branches. They are never widened into an unselected interval.
- Other selected criteria are present in each generated branch, preserving AND semantics across dimensions.
- Top matching percentage maps to `top_percentile_max`.
- Family size maps to the existing minimum/maximum family-member filters.
- TOP_N maps through the existing audience-selection contract and requires a positive target count.

## UI behavior and accessibility

- Every multi-select has an associated label and visible selected-count.
- Native multiple-select controls provide keyboard-accessible selection.
- Every active targeting preference is shown as a chip, including the recommended/default strength and selection behavior.
- Optional chips have individually labelled remove buttons.
- “Clear all” clears every optional preference while visibly retaining the recommended strength and all-matching selection default.
- The collapsed advanced section does not hide active criteria because its selections remain visible in the chip summary.
- Loading, failure, retry, validation, and save states are explicit.
- Target count is revealed and required only when TOP_N is selected.
- The layout collapses the strength choices to one column at narrow viewport widths.

## Validation

The backend validates:

- supported targeting-strength values;
- all current categorical values;
- backend-owned age and income bucket values;
- canonical trimming, sorting, and deduplication;
- positive family-size bounds and minimum not exceeding maximum;
- top matching percentage in 1–100;
- supported selection mode; and
- a positive target count when TOP_N is used.

The browser also presents immediate constraints, but backend validation remains authoritative.

## Files

- `app/repositories/campaign_targeting_context_repository.py`
- `app/routers/campaign_targeting.py`
- `app/schemas/campaign_targeting.py`
- `app/services/campaign_targeting_context_service.py`
- `frontend/index.html`
- `frontend/css/components.css`
- `frontend/js/business-targeting.js`
- `frontend/js/campaign-planner-form.js`
- `frontend/js/campaign-planner-state.js`
- `tests/test_frontend.py`
- `tests/test_phase9_business_targeting.py`

## Verification

- `python -m pytest tests/test_phase9_business_targeting.py -q` — 5 passed.
- `python -m pytest tests/test_phase9_schema.py tests/test_phase9_targeting_contracts.py tests/test_phase9_campaign_context.py tests/test_phase9_business_targeting.py tests/test_frontend.py -q` — 54 passed.
- Focused Ruff checks for all Step 6 Python files and tests — all checks passed.
- `python -m compileall -q app` — passed.
- `git diff --check` — passed; Git emitted only the pre-existing README line-ending warning.

A repository-wide Ruff invocation also identified six pre-existing unused imports in unrelated Phase 4/6/7 files. Step 6 files are clean, and unrelated user work was not modified.

Node.js is not installed in this environment. Frontend module presence, backend option binding, progressive disclosure, chips, clear controls, and served-asset behavior are covered by the passing integration and UI contract tests.

## Acceptance result

PASS. Business users can express primary and advanced targeting preferences without Audience Explorer terminology; all criteria are visible, removable, backend-validated, saved canonically, and mapped without widening disjoint buckets.

STOP — no Phase 9 Step 7 work was performed.
