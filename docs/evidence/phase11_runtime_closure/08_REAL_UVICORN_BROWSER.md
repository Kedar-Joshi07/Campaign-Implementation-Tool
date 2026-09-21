# Step 8 - Real Uvicorn Browser Smoke and Reuse Certification

## Result

**PASS** - The Phase 11 business flow, durable result history, governed download, and all three reuse scenarios were exercised through installed Chrome against the real application server. No custom Step 19/20 server, executor monkeypatch, or materializer monkeypatch was used.

## Runtime under test

- Command: `python -m uvicorn app.main:app`
- Application URL: `http://127.0.0.1:8000`
- Server process: PID 26480
- Browser: installed Google Chrome
- Database: `data/campaign_poc.db`, schema version 18
- Population exposed by Home: 5,000,000 potential customers

The server was launched once and kept alive for the complete certification. The full-data currentness/materialization work was allowed to finish without replacement servers or patched workers.

## Browser smoke flow

1. Home loaded successfully and showed a 5,000,000-person targeting population.
2. The only primary business-navigation entries were `Home`, `Find Potential Customers`, and `Results`.
3. The single Find Potential Customers workflow loaded successfully.
4. The searchable Products multi-select was opened, searched with `PRD024`, and used to select `Travel Grooming Kit 24 (PRD024)`. Age, state, and income multi-selects were also exercised.
5. A bounded, current-compatible `TOP_N` request with target count 1,000 was submitted.
6. Chrome visibly showed both `Processing` and `Completed` states.
7. Navigation away to Home and back to Results succeeded while the search was active.
8. The Results route was refreshed after completion.
9. Search #18 remained present and completed after refresh.
10. Search #18 detail loaded with current snapshot provenance and complete lineage.
11. The governed `DIRECT_MAIL_CONTACT_V1` download completed through Chrome.

The governed export was recorded as export event 17 with status `COMPLETED`, snapshot 2, 4 selected rows, 4 deliverable rows, 0 undeliverable rows, currentness `CURRENT`, and CSV SHA-256 `fe762d40926bde0b88b8c19cdd210a9e38f583ea7d441b76a87cfe0883058492`.

## Reuse scenarios

| Scenario | Search | Change | Result | Snapshot | Generation / analysis / model / scoring | Selected | Duration |
|---|---:|---|---|---:|---|---:|---:|
| A - exact repeat | 18 | Exact repeat of the current Direct Mail request | `EXACT_RESULT_REUSE` | 2 | 1 / 4 / 3 / 3 | 4 | 1,826 s |
| B - filter change | 19 | Removed New York; retained Maryland | `INTELLIGENCE_REUSE` | 3 | 1 / 4 / 3 / 3 | 1 | 1,540 s |
| C - delivery profile change | 20 | Direct Mail to Email only | `EXACT_RESULT_REUSE` | 3 | 1 / 4 / 3 / 3 | 1 | 1,231 s |

Scenario A created new search history while retaining snapshot 2. Scenario B preserved modeling context SHA-256 `b5a864f988754b5561f34759f25ef833d65d7ea08e66232e7fed8e26b6f51bff`, changed the filter identity, reused generation 1/model 3/scoring 3, and created snapshot 3. Scenario C retained Scenario B's modeling, targeting, and filter hashes, retained snapshot 3, and changed only the delivery channel/profile to `EMAIL` / `EMAIL_CONTACT_V1`.

All three search rows completed without a safe error message.

## Lineage counts

| Registry | Before | After | Delta |
|---|---:|---:|---:|
| `campaign_search_runs` | 17 | 20 | +3 |
| `campaign_result_snapshots` | 2 | 3 | +1 |
| `phase10_intelligence_generations` | 1 | 1 | 0 |
| `historical_analysis_runs` | 4 | 4 | 0 |
| `model_runs` | 3 | 3 | 0 |
| `scoring_runs` | 3 | 3 | 0 |

This proves the filter and delivery-profile changes did not start historical analysis, training, or scoring. Only the filter-change scenario materialized one new immutable result snapshot.

## Captured API traffic

The Uvicorn access log recorded successful responses for the browser flow:

- `GET /` -> 200
- `GET /api/health` -> 200
- `GET /api/business/overview` -> 200
- `GET /api/business/recent-results?limit=5` -> 200
- `GET /api/potential-customer-search/options` -> 200
- `POST /api/potential-customer-search/runs` -> 201 for searches 18, 19, and 20
- `GET /api/potential-customer-search/runs/{id}/result` -> 200 during polling and detail rendering
- `GET /api/potential-customer-search/results?limit=200` -> 200
- `GET /api/potential-customer-search/runs/18/download` -> 200

Static assets returned either 200 or expected cache-validation 304 responses. No 4xx/5xx response occurred in the exercised flow.

## Error review

- Chrome console/page warning and error log at initial load: `[]`
- Chrome console/page warning and error log at final Results verification: `[]`
- No JavaScript exception, failed fetch, HTTP error, or network error was observed.
- Uvicorn emitted repeated non-fatal `sklearn.base.InconsistentVersionWarning` messages because the persisted estimators were written by scikit-learn 1.7.2 and the active runtime is 1.7.1. These warnings did not produce an HTTP failure, search failure, lineage change, or incorrect reuse classification.
- Chrome control detached during the long full-data waits and was reattached to the same local application. This was an automation-control lifecycle event, not an application, JavaScript, HTTP, or network failure; all durable state was subsequently verified in a fresh Chrome tab.

## Final browser verification

The final Results page visibly showed, newest first:

- Search #20: Completed, Email, 1 potential customer, `Reused previous exact result`.
- Search #19: Completed, Direct Mail, 1 potential customer, `Reused existing targeting intelligence`.
- Search #18: Completed, Direct Mail, 4 potential customers, `Reused previous exact result`.

The final Chrome console warning/error query returned an empty array.
