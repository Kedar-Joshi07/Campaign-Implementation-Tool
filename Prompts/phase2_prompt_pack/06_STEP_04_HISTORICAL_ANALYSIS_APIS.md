# Step 4 — Historical Analysis APIs

## Objective

Expose the tested Phase 2 services through bounded, typed FastAPI endpoints under `/api/historical`.

Do not build or change frontend pages in this step.

## Required files

Use the repository conventions, likely including:

- `app/routers/historical.py`
- `app/schemas/historical.py`
- `app/main.py` router registration and Phase 2 description/version updates where appropriate
- focused API tests

Do not put analytical SQL in the router.

## 1. `GET /api/historical/options`

Return the Step 2 option/default contract.

Requirements:

- HTTP 200 on a valid loaded database.
- Stable empty-data representation if campaign history is not loaded.
- No hard-coded campaign/product/category/channel values.
- Response model with bounded arrays and ISO dates.

## 2. `GET /api/historical/overview`

Return the historical overview summary and breakdowns.

Requirements:

- no query parameters in Phase 2;
- no person-level data;
- finite numbers only;
- deterministic ordering;
- response-model validation;
- return a stable readiness/empty response rather than fabricated metrics when history is absent.

## 3. `POST /api/historical/analyses`

Accept the frozen request model and synchronously create a saved analysis run.

POC behavior:

- synchronous analysis is acceptable for the 570K historical table;
- return HTTP 201 with the completed analysis snapshot;
- return 422 for Pydantic field/length/date-shape violations;
- return a documented 400 or 422 domain response for no matching observations or invalid option combinations;
- do not pretend the work is queued;
- do not create Phase 3 job infrastructure.

Use a single stable public error shape. Do not expose raw SQLite errors, SQL, paths, stack traces, raw headers, or row content.

## 4. `GET /api/historical/analyses`

Return bounded newest-first summaries.

Query parameters:

- `limit`, default 20, range 1–100
- `offset`, default 0, minimum 0

Do not include full `results_json` in list items. Include only identifiers, name, timestamps, status, conversion definition, normalized high-level filters, and summary counts/rate.

## 5. `GET /api/historical/analyses/{analysis_run_id}`

- Require a positive integer identifier.
- Return the full bounded saved snapshot.
- Return 404 for unknown IDs.
- Allow failed-run metadata to be inspected with a sanitized public failure message, but never return the stored internal error text.

## 6. OpenAPI and existing application behavior

- Register the router once.
- Ensure `/docs` contains the five endpoints and useful descriptions.
- Preserve all Phase 1 routes and response models.
- Update the application description from Phase 1-only wording to Phase 2 without claiming model/scoring functionality.
- Do not remove or rename existing endpoints.

## Tests

Add API tests for:

1. Happy-path options and overview.
2. Happy-path create, list, and reopen analysis.
3. Request normalization reflected in the response.
4. All three conversion definitions.
5. Invalid enum, reversed dates, blank/long names, excessive list sizes, invalid IDs, limit/offset validation.
6. Zero-match domain response.
7. Unknown run returns 404.
8. Failed-run detail is sanitized.
9. SQL-looking filter values cannot change query behavior.
10. Response contains no customer IDs/PII.
11. Empty/unloaded campaign history is handled consistently.
12. Existing Phase 1 endpoints and `/docs` still return expected results.

Inspect serialized responses for forbidden markers such as absolute temporary paths, `SELECT`, constraint/table details, and injected row values.

## Completion criteria

- Five endpoints match `13_API_CONTRACT_REFERENCE.md`.
- OpenAPI is accurate.
- Existing APIs are regression-tested.
- No frontend or later-phase functionality is added.
- Focused and full tests pass.
- Progress tracker is updated.

Stop after this step.

