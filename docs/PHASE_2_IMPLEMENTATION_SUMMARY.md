# Phase 2 Implementation Summary

## Delivered scope

Phase 2 adds governed historical campaign analysis to the accepted Phase 1
foundation. It preserves FastAPI, direct `sqlite3`, and the static
HTML/CSS/Vanilla JavaScript frontend. The delivered workflow provides real filter
options and overview aggregates, synchronous customer-grain cohort analysis,
positive/unlabeled classification, bounded aggregate profiles, saved snapshots,
five typed APIs, and an end-to-end Historical Analysis UI.

Model training, propensity scoring, demographic prospect scoring, Audience
Explorer, campaign creation, activation, and export are not implemented.

## Schema and architecture

The current schema version is 2. Migration from version 1 is additive,
transactional, and idempotent. It adds `historical_analysis_runs` with constrained
status/conversion fields, stable normalized `filters_json`, bounded aggregate
`results_json`, listing summary columns, internal-only diagnostics, and a
newest-first index. The accepted Phase 1 tables and rows remain unchanged.

Historical SQL lives in one repository implementation. Values are parameterized;
dynamic clauses and columns come only from fixed code-owned allowlists. Services
own normalization, cohort semantics, persistence, and response composition;
Pydantic models bound and validate the public contract; the router maps stable
domain failures. The frontend consumes only server aggregates.

## Analysis semantics

An observation is a matching `campaign_sales` row. Selection and labels are at
distinct `customer_id` grain:

- known positive: at least one matching observation satisfies the chosen
  conversion definition;
- unlabeled: a selected customer has no matching qualifying observation;
- unlabeled is not a confirmed negative;
- activity outside the submitted filters cannot change the current label; and
- positive plus unlabeled always equals selected distinct customers.

The conversion definitions are:

| Definition | Positive observation rule |
|---|---|
| `ATTRIBUTED_PURCHASE` | attributed-sale flag = 1 and purchase flag = 1 |
| `ANY_PURCHASE` | purchase flag = 1 |
| `RESPONSE` | response flag = 1 |

`contacted_only=true` and `ATTRIBUTED_PURCHASE` are the defaults. Date bounds are
inclusive and constrained to the loaded contact-date range. Omitted bounds are
normalized and persisted. Derived age uses the normalized end date, including a
calendar-aware birthday comparison.

## Public API and UI

The aggregate-only API surface is:

- `GET /api/historical/options`
- `GET /api/historical/overview`
- `POST /api/historical/analyses`
- `GET /api/historical/analyses`
- `GET /api/historical/analyses/{analysis_run_id}`

The Overview retains Phase 1 content and adds three concise historical visuals.
Historical Analysis provides real multi-select options, date/exposure/conversion
controls, visible validation and synchronous loading, eight KPIs, trends,
breakdowns, four customer-profile groups, recent runs, and reopen. Loading,
empty, zero-match, unavailable, retry, keyboard, and narrow-width paths are
covered. Model Training, Audience Explorer, and Campaigns remain disabled.

## Full-data reconciliation

Step 7 independently queried the ignored local populated SQLite database in
read-only mode. Service/snapshot results matched these direct SQL values:

| Measure | Reconciled value |
|---|---:|
| Observations | 570,000 |
| Contacted / engaged / response | 563,240 / 132,798 / 76,557 |
| Purchase / attributed purchase | 54,450 / 34,273 |
| Distinct customers / campaigns / products | 121,016 / 96 / 36 |
| Net sales / gross margin | $10,894,336.96 / $5,102,167.06 |
| Contact-date range | 2024-01-01 through 2025-12-31 |

The 24 direct monthly groups sum to every overview count and both financial
totals. The broad contacted attributed-purchase cohort reconciled to 563,240
observations, 120,886 selected customers, 25,502 positives, and 95,384
unlabeled customers.

For campaign `CMP0086` and product `PRD011`, direct SQL and saved snapshots both
returned 14,037 observations/customers. Positives were 626 for attributed
purchase, 1,015 for any purchase, and 1,703 for response; each definition
preserved the positive-plus-unlabeled invariant. Saved response run 6 also
matched source response/purchase/attribution counts and $467,154.32 net sales /
$252,749.20 gross margin at creation time.

## Query plans and performance

Local first/repeat measurements are hardware- and load-dependent:

| Operation | First | Repeat |
|---|---:|---:|
| Options | 4.442s | 3.841s |
| Historical overview | 12.281s | 9.502s |
| Broad default analysis | 53.914s | 60.127s |
| Narrow campaign/product analysis | 15.069s | 14.398s |
| Recent-run list | 0.044s | 0.049s |
| Saved-run reopen | 0.050s | 0.049s |

Overview and broad analysis exceed the approximate warm targets. Plans show a
full `campaign_sales` scan and temporary B-trees for overview distinct/grouped
aggregates. The broad cohort uses the contact-date index, materializes matching
observations, and uses a temporary customer-label grouping B-tree. Its cost also
includes bounded breakdowns and four groups across eleven customer-profile
dimensions.

Step 7 removed `TRIM()` wrappers from normalized filter predicates because all
imported text is already stripped. On the full database, the representative
narrow count changed from a contact-date scan (3.2799s) to the existing
`idx_campaign_sales_campaign_product_pu` lookup (0.0274s), with the same 14,037
rows. No new composite index was added: narrow queries already have a useful
index, while broad queries select nearly all history and are dominated by
aggregation/profile work. A speculative full-range scan variant was not retained
because repeated end-to-end timing did not show a reliable benefit.

## Hardening and tests

Dedicated Step 7 coverage verifies every list exactly at and one above its bound,
out-of-range dates, indexable predicates, locked database sanitization with
internal logging, unexpected service-exception sanitization, and corrupt saved
JSON. Earlier Phase 2 tests cover empty history, reversed dates, duplicate/blank
options, zero matches, multiple observations per customer, zero contacted
denominators, inconsistent labels, failed-run reopen, SQL-looking values, PII
exclusion, migrations, APIs, UI states, and browser retry.

Run the final checks with:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app scripts tests
git diff --check
```

## Known limitations and handoff

- Analytics are synchronous in this POC.
- Results are snapshots and do not auto-refresh after source changes.
- Unlabeled does not mean negative.
- Analysis quality depends on synthetic historical data.
- No causal inference is claimed; metrics are descriptive, not model metrics.
- No model is trained and no prospect is scored.
- SQLite/local single-user architecture is not production multi-user
  infrastructure.

The Phase 3 handoff is exactly one valid completed `analysis_run_id`. Its saved
filters define reconstruction; its aggregate results are explanatory, not a
training matrix. Phase 3 must recompute and reconcile membership counts before
training. No customer-ID list, raw SQL, model artifact, score, or demographic
linkage is part of Phase 2.
