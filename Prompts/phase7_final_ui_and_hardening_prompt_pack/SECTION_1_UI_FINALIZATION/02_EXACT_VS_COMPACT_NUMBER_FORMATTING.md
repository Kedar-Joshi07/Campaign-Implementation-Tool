# UI Step 2 — Exact vs Compact Number Formatting

Create explicit helpers, for example:

```javascript
formatId(value)
formatExactInteger(value)
formatCompactNumber(value)
formatDecimal(value, ...)
```

Required behavior:
- formatId(8) -> "8"
- formatExactInteger(416275) -> "416,275"
- formatExactInteger(5000000) -> "5,000,000"
- formatCompactNumber(5000000) -> "5.00M" or current compact equivalent

Use exact formatting for:
campaign/audience/scoring/model/analysis/import/export-event IDs,
target_count, resolved_count, selected_count, deliverable_count,
undeliverable_count, row_count, reconciliation counts, boundary counts.

Compact formatting is allowed only on high-level KPI surfaces where exact identity or
reconciliation is not the task. If useful, expose exact count in tooltip/title.

Never display `Campaign #3.00`, `Run #8.00`, or `416.28K selected` where exactness matters.

Add formatter and surface-level frontend tests. STOP.
