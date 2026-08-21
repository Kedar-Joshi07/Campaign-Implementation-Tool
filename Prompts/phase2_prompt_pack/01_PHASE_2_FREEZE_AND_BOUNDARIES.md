# Phase 2 Freeze, Requirements, and Boundaries

## 1. Authoritative starting point

Repository:

`https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Required base commit:

`c6c9f41ea257aa33ae196b75cc8f76f8419431e7`

That commit is the accepted Phase 1 foundation. It includes the four bounded hardening fixes, 77 passing tests, the FastAPI/SQLite/HTML/CSS/Vanilla-JS architecture, and the three Git-LFS datasets.

Before Phase 2 implementation:

1. Run `git rev-parse HEAD` and record the result.
2. Run `git status --short` and do not overwrite unrelated user changes.
3. If HEAD is not the required base, inspect the intervening commits. Stop if they conflict with this specification.
4. Run the existing full test suite and record the baseline result.
5. Verify that Phase 1 data reconciliation is healthy when the populated database is available.

Do not rewrite Phase 1. Phase 2 must be an additive, reviewable extension.

---

## 2. Product objective

The Campaign Implementation Tool POC will eventually support this flow:

```text
Historical campaign analysis
        ↓
Positive / unlabeled cohort definition
        ↓
PU look-alike model training
        ↓
Score independent demographic prospects
        ↓
Audience exploration and selection
        ↓
Campaign creation and export
```

Phase 2 implements only the first two boxes. It answers:

> Which historical customers and outcomes define the behavior that a later look-alike model should learn?

The result must be analytically credible, reproducible, understandable to a business user, and directly usable as a governed input to Phase 3.

---

## 3. Frozen technology and runtime

Preserve the Phase 1 stack:

- HTML5
- CSS3
- Vanilla JavaScript modules
- Python 3.11+
- FastAPI and Pydantic
- Python `sqlite3` directly
- One local FastAPI process serving the APIs and frontend
- One SQLite database
- Pytest for automated tests

Do not add React, Vue, Angular, jQuery, TypeScript, a frontend build system, SQLAlchemy, PostgreSQL, Redis, Celery, RabbitMQ, Kafka, Spark, Docker orchestration, microservices, or cloud dependencies.

Phase 2 historical analytics must be implemented primarily with parameterized SQLite queries. Do not introduce pandas merely to aggregate 570,000 rows that SQLite can aggregate correctly.

Do not use external CDN assets. If charts are needed, use accessible HTML/CSS and small native SVG elements created by Vanilla JavaScript.

---

## 4. Phase 1 invariants that must remain true

1. Existing Phase 1 APIs continue to work.
2. Existing Overview and Data Status behavior continues to work.
3. Existing tables and imported rows are never destroyed by a migration.
4. The three Git LFS datasets and their hashes remain unchanged.
5. `customer_id` belongs to the historical population.
6. `person_id` belongs only to the independent demographic prospect universe.
7. No row-level linkage between `customer_id` and `person_id` is created or inferred.
8. Synthetic names, addresses, emails, phones, or other quasi-identifiers are never used for linkage.
9. The frontend never loads entire historical or demographic datasets.
10. Public errors remain sanitized while internal logs/metadata retain diagnostic detail.

---

## 5. Explicitly in scope for Phase 2

1. Additive schema migration from Phase 1 schema version 1 to Phase 2 schema version 2.
2. Persistence of historical analysis-run definitions and aggregate results.
3. Reference/filter options derived from the real `campaign_sales` table.
4. Overall historical performance aggregates.
5. Campaign, product, category, channel, and monthly performance breakdowns.
6. A reproducible cohort-analysis engine.
7. Customer-grain positive and unlabeled classification.
8. Aggregate profiles for selected customers, positives, unlabeled customers, and the historical-customer baseline.
9. Bounded FastAPI endpoints for historical options, overview, analyses, and saved runs.
10. Overview-page historical charts using real API values.
11. A functional Historical Analysis page using real backend data.
12. Loading, empty, error, retry, and validation states.
13. Tests for query semantics, APIs, migrations, UI contracts, and performance sanity.
14. README and Phase 2 documentation.
15. A frozen Phase 3 handoff contract based on `analysis_run_id`.

---

## 6. Explicitly out of scope for Phase 2

Do not implement or simulate:

- PU model fitting
- ordinary supervised model fitting presented as PU learning
- feature preprocessing/model pipelines
- model artifact files
- model evaluation metrics
- propensity scores
- writes to a `propensity_scores` table
- scoring the 5-million-person demographic universe
- background training/scoring jobs
- ProcessPoolExecutor, Celery, Redis, or other job infrastructure
- Audience Explorer
- person-level demographic filtering by score
- campaign creation
- campaign-audience persistence
- CSV audience export
- marketing-platform activation
- authentication, RBAC, user management, SSO, or multi-tenancy
- production data governance or enterprise audit systems

The Model Training, Audience Explorer, and Campaigns navigation entries must remain disabled and clearly labeled as later phases.

Do not create placeholder endpoints or fake metrics that imply these capabilities work.

---

## 7. Historical analysis grain

The selected population must be classified at **distinct historical customer grain**, not campaign-observation grain.

Given all `campaign_sales` rows matching the submitted filters:

1. `observation_count` is the number of matching campaign-sales rows.
2. `selected_customer_count` is the count of distinct matching `customer_id` values.
3. A selected customer is **known positive** when at least one of that customer's matching observations satisfies the selected conversion definition.
4. Every other selected customer is **unlabeled**.
5. Unlabeled never means confirmed negative.
6. A customer with ten matching rows still contributes once to positive/unlabeled customer counts and demographic profiles.
7. The invariant must always hold:

```text
positive_customer_count + unlabeled_customer_count = selected_customer_count
```

Do not randomly sample or relabel unlabeled customers in Phase 2.

---

## 8. Eligible observations and filters

The default analysis represents campaign exposure. Therefore:

- `contacted_only` defaults to `true`.
- When `contacted_only=true`, include only `campaign_sales.contacted_flag = 1`.
- A user may explicitly set it to `false` to analyze all matching records.

Supported filters:

- zero or more `campaign_id` values
- zero or more `product_id` values
- zero or more `product_category` values
- zero or more `campaign_channel` values
- zero or more `campaign_type` values
- inclusive `contact_date_from`
- inclusive `contact_date_to`
- `contacted_only`
- `conversion_definition`

Empty lists mean no restriction for that dimension. At least one matching observation is required to complete an analysis run.

API list sizes must be bounded. Recommended maxima:

- campaign IDs: 25
- product IDs: 50
- categories: 25
- channels: 20
- campaign types: 20

Date range must be valid and remain within the available historical range unless the endpoint deliberately returns a clean zero-match validation response.

---

## 9. Frozen conversion definitions

Support exactly these values:

### `ATTRIBUTED_PURCHASE`

A matching observation is positive when:

```text
campaign_attributed_sale_flag = 1 AND purchase_flag = 1
```

This is the default and should match the established `pu_label = 1` business meaning. Tests must detect inconsistent data rather than silently treating an inconsistency as valid.

### `ANY_PURCHASE`

A matching observation is positive when:

```text
purchase_flag = 1
```

### `RESPONSE`

A matching observation is positive when:

```text
response_flag = 1
```

The selected definition applies only to the matching observations inside the submitted cohort filters. Historical activity outside those filters must not make a customer positive for the current analysis.

---

## 10. Shared feature boundary for later modeling

Campaign/sales behavior creates the label and defines the target cohort. It must not become a prospect-only look-alike feature because the independent 5M demographic population has no historical campaign behavior.

Phase 2 may profile these historical-customer attributes that have a compatible demographic concept:

- derived age from `customers.date_of_birth`
- gender
- state
- individual yearly income
- marital status
- education
- employment status
- resident status
- resident type
- family member count
- type of employment

Phase 2 may report campaign behavior and commercial metrics as analysis outputs, but the Phase 3 handoff must clearly distinguish:

- label/cohort filters from campaign-sales history
- candidate predictive features shared with the prospect universe

Do not add ethnicity, religion, occupation industry, family income, or other values to historical customers by linking or guessing from demographics.

---

## 11. Age derivation

Do not use the computer's current date, because that makes the same saved analysis change over time.

For a saved analysis run:

- use `contact_date_to` as the age reference date;
- if the caller omits it, normalize it to the maximum available `contact_date` and persist that normalized date;
- calculate completed years using calendar-aware year/month/day comparison;
- group age into stable bands: `18–24`, `25–34`, `35–44`, `45–54`, `55–64`, `65+`, and `Unknown/Other` where necessary.

The implementation must be deterministic and tested around birthdays.

---

## 12. Required aggregate outputs

### Historical overview

Return real aggregates including:

- observation count
- contacted count
- engaged count
- response count
- purchase count
- attributed purchase count
- distinct customers
- distinct campaigns
- distinct products
- net sales amount
- gross margin amount
- engagement rate
- response rate
- purchase rate
- attributed-purchase rate
- available contact-date range

Also return bounded breakdowns:

- monthly trend
- performance by campaign channel
- performance by product category
- top campaigns
- top products
- positive versus unlabeled observation distribution for descriptive context

All rate denominators must be defined and documented. Handle division by zero without NaN or Infinity.

### Cohort analysis

Return:

- normalized filters
- observation count
- selected distinct-customer count
- positive customer count
- unlabeled customer count
- positive-customer rate
- purchase/response/attributed-purchase observation counts
- net sales and gross margin for matching observations
- monthly performance trend
- channel/category/campaign/product breakdowns
- aggregate customer profiles for selected, positive, unlabeled, and all historical customers

Every list must be ordered deterministically and bounded. Low-frequency categories may be combined into `Other`.

No endpoint may return names, addresses, emails, phone numbers, raw customer rows, or all matching customer IDs.

---

## 13. Additive Phase 2 schema

Create an idempotent migration to schema version `2`. Do not rebuild or replace the Phase 1 tables.

Required table: `historical_analysis_runs`.

Minimum logical fields:

- `analysis_run_id` integer primary key
- `analysis_name` text, optional or server-generated
- `created_at` text
- `completed_at` text, nullable
- `status` constrained to `RUNNING`, `COMPLETED`, or `FAILED`
- `conversion_definition`
- `filters_json` containing the normalized filter contract
- `results_json` containing the completed bounded aggregate snapshot, nullable until complete
- summary count fields useful for listing: observation, selected customer, positive customer, unlabeled customer
- `positive_customer_rate`
- `error_message` for internal diagnostics

Persist normalized JSON with stable key ordering. Never persist arbitrary SQL.

Recommended indexes:

- an index supporting newest-first analysis-run listing
- `campaign_sales(campaign_channel)`
- `campaign_sales(product_category)`
- `campaign_sales(campaign_type)` if query evidence justifies it
- one carefully chosen composite analysis index only if measured query plans/timings justify it

Do not add dozens of speculative indexes. Record query-plan evidence for any composite index.

Migration requirements:

1. Idempotent.
2. Preserves all Phase 1 rows.
3. Works on an empty database and an already populated Phase 1 database.
4. Updates `app_metadata.schema_version` only after successful migration.
5. Makes application startup/initialization bring the database to the current schema.
6. Is covered by migration and row-preservation tests.

---

## 14. Required Phase 2 endpoints

Add a router under `/api/historical`.

Required endpoints:

- `GET /api/historical/options`
- `GET /api/historical/overview`
- `POST /api/historical/analyses`
- `GET /api/historical/analyses`
- `GET /api/historical/analyses/{analysis_run_id}`

Do not add delete/update/recompute endpoints without an explicit requirement.

Use response models. Validate body/list/date/string bounds. Return stable 4xx responses for invalid filters and 404 for an unknown run. Public failure responses must not expose SQL, absolute paths, stack traces, table layouts, or raw internal errors.

Detailed request/response requirements are frozen in `13_API_CONTRACT_REFERENCE.md`.

---

## 15. Frontend scope

### Overview enhancement

Keep the existing Phase 1 Overview intact and add a restrained historical-performance section driven by `/api/historical/overview`:

- monthly conversion/performance trend
- performance by channel
- product-category performance
- a clear call to action to open Historical Analysis

Do not turn Overview into a dense BI dashboard.

### Historical Analysis page

Enable the existing Historical Analysis navigation item. The page must include:

- analysis name
- campaign selector
- product-category selector
- product selector
- channel selector
- campaign-type selector
- inclusive date range
- contacted-only control
- conversion-definition control with plain-language explanations
- Analyze Population action
- summary KPIs
- positive/unlabeled explanation
- trend and breakdown visualizations
- selected/positive/unlabeled/baseline customer profiles
- recent saved analyses and reopen action

Use server aggregates only. Do not fetch or render person-level tables in Phase 2.

Use `textContent` for data-derived text, native DOM construction, existing API/error helpers, accessible form labels, keyboard-reachable controls, loading states, empty states, and retry behavior.

---

## 16. Performance and safety principles

- Use parameterized SQL values only.
- Dynamic SQL may assemble only fixed allowlisted clauses/columns.
- Do not accept arbitrary sort expressions or SQL fragments.
- Bound all multi-select lists and aggregate result lengths.
- Prefer one or a few purposeful aggregate queries over N+1 querying.
- Do not scan the 5M demographics table for Phase 2 historical analysis.
- Do not return raw 570K campaign-sales rows.
- Use `EXPLAIN QUERY PLAN` and measured timings on the full dataset before adding indexes.
- Performance thresholds must be treated as local POC targets, not universal guarantees.
- Target a warm historical overview under roughly 5 seconds and a broad full-history cohort analysis under roughly 10 seconds on the reference development machine; record actual measurements and explain deviations.
- Frontend requests must show visible loading and remain recoverable after errors.

---

## 17. Definition of Phase 2 complete

Phase 2 is complete only when:

1. The exact Phase 1 base and baseline tests were recorded.
2. Additive schema migration succeeds without losing Phase 1 data.
3. Filter options are derived from SQLite.
4. Historical overview aggregates reconcile with independent SQL checks.
5. Cohorts are classified at distinct customer grain.
6. All three conversion definitions are correct.
7. Positive plus unlabeled equals selected distinct customers.
8. Saved analyses can be listed and reopened reproducibly.
9. APIs validate inputs and expose no raw person-level or internal diagnostic data.
10. Overview historical charts use real API values.
11. Historical Analysis works end-to-end in the browser.
12. Loading, empty, invalid-input, backend-error, and retry states work.
13. Full tests pass.
14. Full-data performance/query-plan evidence is recorded where practical.
15. README/documentation is updated.
16. Model training, scoring, audience exploration, and campaign creation remain unimplemented and disabled.
17. `12_PHASE_3_HANDOFF_CONTRACT.md` matches the implemented saved-analysis contract.

