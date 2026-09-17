# Phase 11 Step 16 — API and Backward Compatibility

Date: 2026-09-17

## Outcome

Step 16 is complete. The three-screen Phase 11 product has a complete additive API surface, and the retained Phase 1–10 APIs passed their bounded compatibility regression unchanged.

## Phase 11 endpoint inventory

### Home

| Method | Path | Contract |
| --- | --- | --- |
| GET | `/api/business/overview` | Metadata-only business KPI summary |
| GET | `/api/business/recent-results?limit=5` | Bounded 5–10 newest search results |

### Search setup and run status

| Method | Path | Contract |
| --- | --- | --- |
| GET | `/api/potential-customer-search/options` | Backend-owned context, criteria, and profile options |
| POST | `/api/potential-customer-search/runs` | Validate, persist immutable run, synchronously hand off to orchestration, return status |
| GET | `/api/potential-customer-search/runs` | Bounded newest-first run history |
| GET | `/api/potential-customer-search/runs/{search_run_id}` | Business-safe run status lookup added in Step 16 |
| GET | `/api/potential-customer-search/runs/{search_run_id}/status` | Pollable run status lookup |

### Results and downloads

| Method | Path | Contract |
| --- | --- | --- |
| GET | `/api/potential-customer-search/results` | Additive rich result-history projection used by Results UI |
| GET | `/api/potential-customer-search/runs/{search_run_id}/result` | Saved result detail with analytical lineage but no contact PII |
| GET | `/api/potential-customer-search/runs/{search_run_id}/download` | Governed profile-specific streaming CSV |
| GET | `/api/export-profiles` | Backend-owned omnichannel profile registry projection |

The new base run lookup reuses the existing `SearchSubmissionStatus` schema, repository lookup, and service projection. No duplicate status logic or direct SQL was added to the router.

## Submission and orchestration boundary

- Pydantic rejects malformed top-level requests and extra fields.
- Campaign context, targeting criteria, branch expansion, channel/profile compatibility, and source-backed options are validated by the established services.
- A new immutable search record is committed before the executor handoff.
- The Phase 11 submission service composes the existing Campaign Planner contracts and Phase 10 intelligence orchestration; it does not bypass them.
- The handoff is synchronous in the current POC and does not create detached worker processes per click.
- Repeated intentional identical POST requests create distinct durable history events. Exact-result and intelligence reuse remain responsible for avoiding unnecessary repeated heavy work.
- An idempotency token is not introduced in this phase, as permitted by the prompt.

## Error and privacy contracts

| Situation | HTTP status | Public behavior |
| --- | ---: | --- |
| Invalid request, criteria, profile, ID, or bound | 422 | Stable validation/business message |
| Missing run/result/snapshot lineage | 404 | Stable not-found message |
| Result incomplete, stale, mismatched, or not ready for download | 409 | Stable business conflict message |
| Unexpected submission/projection/export failure | 500 | Logged internally; stable sanitized response |

The contract tests inject an exception containing SQL, a Windows path, an artifact reference, and an email address. None appear in the JSON response. Search status, result detail, overview, recent-result, and profile responses were also checked for raw local paths, stack traces, SQL text, and contact values.

Contact identifiers can appear only inside an authorized governed CSV stream for the selected profile. They are not returned by the JSON APIs or result UI projections.

## Backward compatibility

The OpenAPI inventory confirms the retained health/version, data, reference, historical analysis, model/scoring, audience, saved-audience, campaign, targeting, finalize, and export endpoints remain registered. Phase 11 routes are additive; no legacy route, method, or response contract was removed by Step 16.

Schema version 18 is an additive source/lineage extension. Existing API tests consume `CURRENT_SCHEMA_VERSION` where schema version is part of a response. No unrelated Phase 1–10 response was versioned or changed.

## Verification

New Step 16 API contract suite:

```text
python -m pytest tests/test_phase11_api_backward_compatibility.py -q
13 passed in 51.55s
```

This covers the complete recommended OpenAPI surface, base run lookup, shared status response, repeated intentional submissions, bounded request validation, 404/409/500 contracts, and response sanitization.

Existing Phase 11 API/result/export regression:

```text
python -m pytest \
  tests/test_phase11_business_search_form.py \
  tests/test_phase11_results_history_detail.py \
  tests/test_phase11_omnichannel_export_engine.py \
  -m "not browser and not performance and not full5m" -q

62 passed, 19 deselected in 223.63s
```

Retained Phase 1–10 API compatibility regression:

```text
python -m pytest \
  tests/test_health.py tests/test_data_api.py tests/test_historical_api.py \
  tests/test_model_api.py tests/test_scoring_api.py tests/test_audience_api.py \
  tests/test_audience_profile_api.py tests/test_audience_step4_api.py \
  tests/test_saved_audience_api.py tests/test_campaign_api.py \
  tests/test_campaign_export_hardening.py tests/test_phase10_api_bridge.py \
  tests/test_phase9_campaign_context.py \
  tests/test_phase9_save_target_group_campaign.py \
  -m "not browser and not performance and not full5m and not cleanroom" -q

108 passed in 929.65s
```

Python compilation passed for the application and the new Step 16 test module.

Aggregate result: **183 passed**, with 19 intentionally deselected browser/performance/full-volume cases owned by later Phase 11 certification steps.

## Guardrail confirmation

- No canonical import or data regeneration ran.
- No production training, scoring, ranking, or intelligence build ran.
- No 5M population scan ran.
- No activation, feedback ingestion, or outbound delivery ran.
- No files were staged, committed, or pushed.
