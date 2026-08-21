# Step 6 — Historical Campaign Analyzer UI

## Objective

Enable the Historical Analysis navigation and implement the complete Phase 2 browser workflow using the APIs from Step 4.

## Required user journey

```text
Open Historical Analysis
        ↓
Load real filter options and defaults
        ↓
Choose cohort filters and conversion definition
        ↓
Analyze Population
        ↓
Review distinct customers, positives, and unlabeled
        ↓
Review trends, breakdowns, and customer profiles
        ↓
See the saved analysis-run ID
        ↓
Reopen the analysis from Recent Analyses
```

Every step must work with real backend data.

## 1. Navigation and page shell

- Enable only Historical Analysis among the later-phase entries.
- Keep Model Training, Audience Explorer, and Campaigns disabled/labeled later phase.
- Preserve hash/view routing conventions.
- Give the page a unique heading, concise explanation, and Phase 2 context.

## 2. Analysis form

Include:

- analysis name text field
- campaign multi-select
- product-category multi-select
- product multi-select
- campaign-channel multi-select
- campaign-type multi-select
- from/to date inputs
- contacted-only checkbox enabled by default
- conversion-definition radio/select control
- Analyze Population button
- Reset to defaults action

Use real options from `/api/historical/options`.

If native multi-select usability is poor, implement a small accessible checkbox/dropdown component in Vanilla JS. Do not introduce a UI library.

Explain conversion definitions in business language:

- Campaign-attributed purchase: confirmed attributed purchasers are known positive.
- Any purchase: any observed purchaser inside the selected cohort is known positive.
- Response: any responder inside the selected cohort is known positive.

Show this permanent statement near the results:

> Unlabeled customers are not confirmed negatives; no qualifying positive event was observed inside the selected filters.

## 3. Submission behavior

- Validate required/name/date/list constraints client-side for usability, while relying on backend validation as authoritative.
- Disable duplicate submissions while running.
- Show a visible analysis loading state.
- POST the normalized form to `/api/historical/analyses`.
- Render server-normalized filters and result values.
- Do not manufacture IDs, counts, rates, or charts.
- Preserve the form after a recoverable error.

## 4. Results

Render summary cards:

- matching observations
- selected distinct customers
- known-positive customers
- unlabeled customers
- positive-customer rate
- net sales
- gross margin
- saved analysis-run ID

Render bounded visual sections:

- monthly trend
- channel performance
- product-category performance
- top campaigns/products
- selected population profile
- positive profile
- unlabeled profile
- historical-customer baseline

Profiles should make comparison easy without overwhelming the page. Use tabs or a compact comparison control if useful, implemented in Vanilla JS and accessible by keyboard.

Never render person-level identifiers or contact data.

## 5. Recent analyses

- Load `/api/historical/analyses?limit=20&offset=0`.
- Show name, run ID, completion time, status, conversion definition, selected/positive/unlabeled counts, and positive rate.
- Reopen a completed analysis through `GET /api/historical/analyses/{id}`.
- Failed analyses display a stable public failure label without internal diagnostic detail.
- An empty history has a helpful empty state.

## 6. Loading, errors, accessibility, responsiveness

Implement:

- options-loading state
- analysis-running state
- recent-runs loading state
- inline form validation
- backend validation message
- zero-match message
- general backend error and retry
- empty-data state
- successful retry restoring the global backend badge

Requirements:

- proper `<label>` associations
- keyboard navigation
- focus moves to validation/error/result heading when appropriate
- `aria-live` for run status/result announcements
- charts have accessible names or textual equivalents
- colors meet existing design contrast patterns
- usable at narrow viewport width

## Tests and browser validation

Add tests proving:

1. Historical Analysis navigation is enabled; later features remain disabled.
2. Options are loaded from the API.
3. Form payload maps exactly to the API contract.
4. Counts/rates are rendered from the response.
5. Positive/unlabeled explanation is visible.
6. Recent analyses load and reopen.
7. Data-derived text uses safe DOM rendering.
8. No person-level table or demographic scoring request exists.
9. Loading, validation, empty, error, and retry states exist.

Perform real-browser validation with a small fixture and, when practical, the full populated database. Exercise at least:

- default analysis
- one filtered campaign/product cohort
- each conversion definition
- a zero-match filter
- reopen recent analysis
- backend unavailable then retry
- narrow viewport

Record observed values and screenshots only as local evidence unless asked to commit them.

## Completion criteria

- Historical Analysis works end-to-end.
- Saved analyses reopen reproducibly.
- No later-phase functionality is enabled.
- Focused and full tests pass.
- Browser validation is recorded.
- Progress tracker is updated.

Stop after this step.

