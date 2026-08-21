# Step 3 — Cohort Analysis Engine and Saved Analysis Runs

## Objective

Implement the authoritative customer-grain cohort engine, aggregate profiles, and saved-analysis persistence that Phase 3 can later consume by `analysis_run_id`.

Do not expose APIs or build UI in this step.

## 1. Internal normalized filter contract

Create one typed internal/request-compatible filter representation with:

- analysis name
- campaign IDs
- product IDs
- product categories
- campaign channels
- campaign types
- contact date from/to
- contacted-only flag
- conversion definition

Normalization rules:

- trim strings;
- reject blanks;
- deduplicate list values;
- sort list values for stable persistence;
- enforce list maxima;
- normalize omitted dates to the real available minimum/maximum;
- validate `from <= to`;
- use only the three frozen conversion definitions;
- generate a useful default analysis name when omitted;
- serialize JSON with stable key ordering.

Never accept raw SQL, column names, operators, or sort expressions from the caller.

## 2. Customer-grain cohort SQL

Build a parameterized matching-observations CTE from fixed allowlisted clauses. Then aggregate once per `customer_id`.

Conceptually:

```sql
WITH matching_observations AS (...fixed select and parameterized filters...),
customer_labels AS (
    SELECT
        customer_id,
        MAX(CASE WHEN <fixed conversion expression> THEN 1 ELSE 0 END)
            AS is_positive,
        COUNT(*) AS matching_observations
    FROM matching_observations
    GROUP BY customer_id
)
...
```

The conversion expression is selected from a code-owned mapping, never supplied as SQL by the client.

Required invariants:

- one customer contributes once to customer counts/profiles;
- positive means any matching row meets the chosen definition;
- activity outside submitted filters does not affect the label;
- unlabeled means selected and not known positive;
- positive + unlabeled = selected;
- a zero-match request fails with a stable validation/domain error and persists a failed run only if the implementation has already created run metadata.

## 3. Analysis outputs

Produce the frozen summary metrics and bounded breakdowns for matching observations.

Customer profiles must support these groups:

- `selected`
- `positive`
- `unlabeled`
- `historical_baseline`

Required profile dimensions:

- age band
- gender
- state
- individual-income band
- marital status
- education
- employment status
- resident status
- resident type
- family-member-count band
- type of employment

Recommended stable bands:

### Individual income

- `<25K`
- `25K–49,999`
- `50K–74,999`
- `75K–99,999`
- `100K–149,999`
- `150K–249,999`
- `250K+`
- `Unknown/Other`

### Family size

- `1`
- `2`
- `3–4`
- `5+`
- `Unknown/Other`

For each profile category return count and share of that group. Shares must be finite and consistent with the group total. Bound high-cardinality dimensions such as state to a documented top N plus `Other`.

Use the normalized analysis end date for deterministic age calculation. Add explicit birthday-boundary tests.

Do not include customer IDs or PII in results.

## 4. Saved run lifecycle

Implement repository/service operations:

1. Insert `RUNNING` metadata with normalized filters.
2. Execute the analysis.
3. On success, persist `COMPLETED`, completion time, summary list fields, and bounded `results_json`.
4. On failure, persist `FAILED` and full internal diagnostic text in `error_message`.
5. Return public/domain exceptions without exposing internal details.
6. List recent runs newest first with bounded pagination.
7. Fetch one completed or failed run by integer ID.

The completed response reopened from SQLite must match the response originally returned, apart from fields explicitly expected to differ.

Avoid holding a write transaction during long analytical reads. Do not retain database locks unnecessarily.

## 5. Analysis-name and JSON safety

- Enforce a reasonable length such as 1–120 characters after trimming.
- Store text as data.
- Never use analysis name in file paths or SQL.
- Validate decoded persisted JSON shape before returning it.
- If stored JSON is corrupt, log details and return a stable internal/domain error.

## Tests

Tests must prove:

1. Multiple matching rows for one customer yield one customer label.
2. One positive row makes the selected customer positive.
3. A purchase outside the filters does not make the current cohort positive.
4. All three conversion definitions behave correctly.
5. `contacted_only` behaves correctly.
6. Date boundaries are inclusive.
7. Every multi-select filter works alone and in combination.
8. Filter values resembling SQL injection are treated only as values.
9. List bounds and invalid dates are rejected.
10. Positive + unlabeled = selected for every case.
11. Profile counts/shares reconcile.
12. Age calculation is deterministic around birthdays.
13. Empty matches are handled cleanly.
14. Completed runs persist/reopen identically.
15. Failed runs preserve internal diagnostics without partial result JSON.
16. Newest-first listing and limit/offset are correct.
17. No customer IDs, PII, SQL, or paths appear in public service results.

## Completion criteria

- One authoritative cohort engine exists.
- Analysis runs persist reproducibly.
- Phase 3 handoff data exists but no model code exists.
- Focused and full tests pass.
- Progress tracker documents semantics and limitations.

Stop after this step.
