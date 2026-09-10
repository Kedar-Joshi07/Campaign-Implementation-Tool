# Phase 9 Step 5 — Campaign Context Report

Date: 2026-09-09
Status: PASS

## Scope

This step implements Campaign Context capture in the Phase 9 Create Campaign wizard. It does not resolve models, fuse model output, score prospects, filter an audience, or activate a campaign.

## Implemented flow

1. The browser requests `GET /api/campaign-planner/context-options`.
2. The backend reads current values from `campaign_sales` and returns products, campaign types, campaign categories, offer types, and historical campaign channels in deterministic order.
3. The backend separately returns the governed Phase 7 delivery channels. Delivery channel and historical-channel context are distinct controls and distinct contract fields.
4. The user selects one or more products and optional context values, plus one required delivery channel.
5. The browser sends the context to `POST /api/campaign-planner/contexts` for first save or `PUT /api/campaign-planner/contexts/{id}` for an update.
6. The server validates all selected reference values against the current option set, trims/deduplicates/sorts multi-select values, normalizes the delivery channel, creates canonical JSON, and records its SHA-256 digest.
7. The saved context is read back through `GET /api/campaign-planner/contexts/{id}`. Its canonical JSON digest is verified before a response is returned.
8. The browser retains only the context identifier and working form values in session state, then reopens the authoritative server record when the wizard is loaded again.

## Business semantics

- Values within a context dimension represent OR: for example, Product A or Product B.
- Populated dimensions combine as AND: for example, selected products and campaign type and offer type.
- Multiple selected products remain one business context request.
- No model is selected, combined, or fused in this step. Phase 10 owns context-to-model resolution.
- `campaign_channel` is the final delivery channel contract (`EMAIL` or `DIRECT_MAIL`).
- `historical_campaign_channels` is optional descriptive context from historical data and is not silently mapped to the delivery channel.
- Context values are stored as campaign meaning; they are not repurposed as audience filters.

## Current-data evidence

A read-only query against the configured current database found:

| Dimension | Distinct current values |
| --- | ---: |
| Products | 36 |
| Campaign types | 7 |
| Campaign categories | 9 |
| Offer types | 6 |
| Historical campaign channels | 9 |

All business-option elements are populated from the API. No product, campaign-type, campaign-category, offer-type, or historical-channel values are hardcoded in JavaScript.

## Validation and persistence controls

- At least one product is required.
- The delivery channel is required and constrained by the existing governed campaign channel contract.
- Unknown current-data IDs or values return HTTP 422.
- Blank selections, unsupported request fields, and invalid request shapes are rejected.
- Multi-select arrays are canonical, case-stable, deduplicated, and sorted.
- The persisted JSON and SHA-256 digest are deterministic for equivalent input.
- Create stores the existing Step 3 default targeting-criteria contract only to satisfy the shared Phase 9 persistence row; it does not execute targeting.
- Update changes only campaign-context fields and preserves targeting criteria and any later scoring linkage.
- New context rows explicitly retain `source_scoring_run_id = NULL`.
- Reopen verifies stored context integrity before returning it.

## Files

- `app/repositories/campaign_targeting_context_repository.py`
- `app/routers/campaign_targeting.py`
- `app/schemas/campaign_targeting.py`
- `app/services/campaign_targeting_context_service.py`
- `app/main.py`
- `frontend/index.html`
- `frontend/css/components.css`
- `frontend/js/campaign-context.js`
- `frontend/js/campaign-planner-form.js`
- `frontend/js/campaign-planner-state.js`
- `tests/test_phase9_campaign_context.py`
- `tests/test_frontend.py`

## Verification

Commands and results:

- `python -m pytest tests/test_phase9_campaign_context.py -q` — 4 passed.
- `python -m pytest tests/test_phase9_schema.py tests/test_phase9_targeting_contracts.py tests/test_phase9_campaign_context.py tests/test_frontend.py -q` — 48 passed.
- `python -m ruff check app/schemas/campaign_targeting.py app/repositories/campaign_targeting_context_repository.py app/services/campaign_targeting_context_service.py app/routers/campaign_targeting.py tests/test_phase9_campaign_context.py` — all checks passed.
- `git diff --check` — passed; the only output was Git's pre-existing README line-ending warning.

Node.js is not installed in this environment, so `node --check` was unavailable. The frontend module and its served asset are covered by the passing frontend integration and Step 5 UI contract tests.

## Acceptance result

PASS. The Campaign Context step uses current backend data, preserves explicit OR-within/AND-across meaning canonically, keeps delivery and historical-channel concepts separate, rejects unknown values, and is readable after save and reopen.

STOP — no Phase 9 Step 6 work was performed.
