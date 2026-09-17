# Step 16 — Phase 11 API & Backward Compatibility

## Objective
Expose the new three-screen product cleanly while preserving Phase1–10 APIs.

Recommended APIs:

Home:
GET /api/business/overview
GET /api/business/recent-results

Search setup:
GET /api/potential-customer-search/options
POST /api/potential-customer-search/runs
GET /api/potential-customer-search/runs/{id}
GET /api/potential-customer-search/runs/{id}/status

Results:
GET /api/potential-customer-search/runs
GET /api/potential-customer-search/runs/{id}/result
GET /api/potential-customer-search/runs/{id}/download
or profile-specific download query parameter if cleaner

Profiles:
GET /api/export-profiles

Use established schema/service/repository layering.
Do not bypass existing Campaign Planner/Phase10 engines; Phase11 service composes them.

POST search:
- validates payload;
- creates immutable search run immediately;
- returns ID/status;
- idempotency token optional but double-click behavior must not create uncontrolled duplicate processing;
- repeated intentional identical submissions still create separate history events.

Error contracts:
422 invalid criteria/profile
409 currentness/not-ready conflict where appropriate
404 run/snapshot not found
500 safe server message

No raw file paths, SQL, stack traces or contact PII in JSON responses.

Backward compatibility:
Phase1–10 APIs continue to pass tests unchanged unless an additive source-schema extension
requires versioned response changes.

Evidence:
`docs/evidence/phase11/16_API_BACKWARD_COMPATIBILITY.md`

STOP.
