# Step 5 — Overview Historical Analytics Enhancement

## Objective

Enhance the existing Overview page with a concise real-data historical performance section and a clear path to Historical Analysis.

Do not implement the full Historical Analysis page in this step.

## Design intent

Overview remains a launchpad, not a BI dashboard. Preserve the Phase 1 data-foundation cards and health/readiness content.

Add no more than three compact historical visualizations:

1. Monthly attributed-purchase or purchase trend.
2. Performance by campaign channel.
3. Product-category performance.

Add a visible `Analyze historical campaigns` call to action that navigates to the still-to-be-completed Historical Analysis view. It may navigate to a clearly marked loading/next-step shell until Step 6, but do not enable a broken interaction in the final Step 5 state.

## Data source

Fetch only:

`GET /api/historical/overview`

Do not derive historical KPIs from DOM constants. Do not fetch raw campaign rows.

## Implementation expectations

- Extend the existing modular JavaScript structure, for example with `frontend/js/historical-overview.js`.
- Reuse API caching/error helpers.
- Use accessible HTML/CSS and native SVG or CSS bars.
- No chart library or CDN.
- Use `textContent` and safe DOM methods.
- Format counts, percentages, currency, and dates consistently.
- Include useful text/table equivalents or accessible labels for visual information.
- Truncate or wrap long campaign/category/channel labels safely.
- Do not use color as the only meaning carrier.
- Keep the layout responsive at desktop and narrow widths.

## States

Implement and test:

- loading skeleton/spinner
- loaded real data
- empty/no campaign history
- backend error with retry
- partial/unknown categories

A retry that succeeds must clear the page-level error and restore the global backend status indicator.

## Tests

Add frontend contract/integration tests proving:

1. The historical overview request is made through the API module.
2. No chart values are hard-coded.
3. Data-derived text uses safe rendering patterns.
4. Loading, empty, error, and retry hooks exist.
5. Existing Overview and Data Status elements still exist.
6. Future Model Training, Audience Explorer, and Campaigns navigation remains disabled.
7. Historical Analysis navigation/CTA is distinguishable and ready for Step 6.

Where practical, run the application with a small fixture and inspect the Overview in a real browser at desktop and narrow width. Record evidence without committing screenshots unless explicitly requested.

## Completion criteria

- Overview shows real historical trends without becoming crowded.
- Phase 1 overview behavior is preserved.
- Error/retry behavior is functional.
- Full Historical Analysis is not implemented early.
- Focused and full tests pass.
- Progress tracker is updated.

Stop after this step.

