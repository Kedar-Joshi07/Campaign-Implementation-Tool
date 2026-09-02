# Step 4 — Options Optimization & Filter Semantic Consistency

## Objective

Make options snapshot-backed and fix all `Unknown/Other` / vocabulary inconsistencies.

## Snapshot options

Persist numeric ranges for age/income/family size and categorical values/counts for gender, state, marital_status, education, employment_status, resident_status, resident_type, type_of_employment.

Normalize categories consistently with:

```sql
COALESCE(NULLIF(TRIM(CAST(field AS TEXT)), ''), 'Unknown/Other')
```

Include `Unknown/Other` when present and require each categorical option count total == population_count.

## Runtime options

`get_audience_filter_options()` must perform lightweight currentness + snapshot currentness + one snapshot read. No live 5M GROUP BY loops. Required <2 sec; preferred <0.5 sec.

## Unknown/Other filtering

`Unknown/Other` must match NULL, blank, whitespace-only, and literal `Unknown/Other`. Apply identical normalized SQL expression in filter predicates. Do not mutate source rows.

## Context validation

Keep `normalize_audience_filters()` syntactic. After loading current snapshot, reject requested categorical values absent from current vocabulary (for all eight categorical fields). Example `state=["Atlantis"]` must be 422/validation error, not silent zero.

## Numeric contract

Context validation must preserve age 18..100, family>=1, income>=0. Valid but empty ranges remain allowed.

## Tests/frontend

Test NULL/blank/whitespace/literal Unknown across options/filter/profile/search, valid/invalid vocabulary for all categorical fields, and increase options client cache to a practical scoring-run-bound TTL (e.g. 5 min) with explicit refresh bypass.

STOP until options <2 sec and semantic tests pass.
