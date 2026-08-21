# Step 2 — Historical Options and Overall Performance Analytics

## Objective

Implement repository/service logic for real filter options and bounded overall historical campaign-performance aggregates.

Do not add the router or frontend yet. Do not persist cohort analysis runs yet.

## Required modules

Use names consistent with the repository, for example:

- `app/repositories/historical_repository.py`
- `app/services/historical_service.py`
- internal typed structures or schema-neutral dictionaries as appropriate

Do not place all SQL in a router or extend `DataRepository` into a Phase 2 catch-all.

## 1. Historical filter options

Implement a repository query/service response that returns:

- minimum and maximum contact date
- campaign options: ID and stable display name
- product-category values
- product options: ID, name, category
- campaign-channel values
- campaign-type values
- supported conversion definitions with labels/descriptions
- default filters, including full available date range, `contacted_only=true`, and `ATTRIBUTED_PURCHASE`

Requirements:

- All database options come from real `campaign_sales` values.
- Exclude null/blank option values.
- Deduplicate and order deterministically.
- Bound option counts even if the data grows.
- Campaign/product IDs and names must be grouped consistently; flag inconsistent labels in logs/tests rather than returning arbitrary duplicates.
- Do not return customer data.

## 2. Historical overview aggregates

Implement overall full-history metrics defined in the freeze.

Document denominators explicitly:

- engagement rate = engaged observations / contacted observations
- response rate = responded observations / contacted observations
- purchase rate = purchased observations / contacted observations
- attributed-purchase rate = attributed purchases / contacted observations

When contacted observations are zero, rates must return `0.0` or `null` according to one documented contract. Never return NaN or Infinity.

Financial totals must use `COALESCE` and consistent rounding suitable for JSON display. Counts remain integers.

## 3. Bounded breakdowns

Return deterministic aggregate arrays:

### Monthly trend

Group by `YYYY-MM` from `contact_date`, including:

- observations
- contacted
- engaged
- responses
- purchases
- attributed purchases
- net sales
- purchase and attributed-purchase rates

Order ascending by month.

### Channel and product-category performance

Include the same useful counts/rates and net sales. Order by observation count descending and then label ascending. Return at most a documented limit; combine remaining categories into `Other` when appropriate.

### Top campaigns and products

Return stable IDs/names and bounded counts, rates, positives, and net sales. Order deterministically.

### PU descriptive observation distribution

Return `pu_label=1` and `pu_label=0` observation counts, explicitly labeled `Known positive observations` and `Unlabeled observations`. This is descriptive only and must not be confused with the customer-grain cohort contract used in Step 3.

## 4. Query design

- Use SQLite aggregation, not Python row aggregation.
- Avoid N+1 queries.
- Use parameterized values.
- Treat category labels as values, not SQL identifiers.
- Do not query `demographics`.
- Record query counts and representative timings on test fixtures.
- If using multiple queries, keep each purpose clear and bounded.

## Tests

Use a fixture containing:

- multiple observations per customer
- contacted and uncontacted records
- engagement/response/purchase combinations
- attributed and unattributed purchases
- multiple months, channels, categories, campaigns, and products
- null financial values where schema permits
- a zero-contact edge case

Prove:

1. Option values are real, deduplicated, stable, and bounded.
2. Full-history counts and financial totals reconcile with independent SQL/assertions.
3. Rates use the documented denominator.
4. Zero denominators are safe.
5. Trends are ordered chronologically.
6. Top lists are ordered deterministically.
7. No raw customer/person fields appear in service results.
8. No demographic query is introduced.

## Completion criteria

- Repository/service options and overview are complete.
- No router/frontend/persistence work has leaked into this step.
- Focused and full tests pass.
- Progress tracker includes query semantics and results.

Stop after this step.

