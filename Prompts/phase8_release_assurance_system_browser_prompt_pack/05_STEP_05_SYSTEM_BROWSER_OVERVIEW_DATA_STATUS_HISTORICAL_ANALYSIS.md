# Step 5 — System Browser: Overview, Data Status & Historical Analysis

Use only the system-browser harness.

## Overview
Exercise navigation, backend-status control, Refresh data, Historical Analysis CTA and retry/error paths. Verify API-driven counts, health, schema, historical charts and correct positive-count grain.

## Data Status
Exercise navigation, refresh/reconciliation and retry controls. Verify current published dataset vs last import attempt, all source provenance/currentness, reconciliation and safe user-facing errors.

## Historical Analysis — TRUE UI submission
This step must actually create historical analyses through browser interactions.

Exercise every current control, including where present:
- analysis name
- contact date from/to
- campaign multi-select
- product multi-select
- channel multi-select
- campaign type/category
- contacted-only
- conversion definition
- Reset
- Analyze Population
- Refresh/Retry options
- saved/recent run selector
- reopen/view
- profile dimensions/tabs

Run:
A. broad valid analysis
B. narrow campaign/product/channel analysis

Verify through UI:
selected population, P, U, P+U reconciliation, rate, profile/charts/tables and currentness.

Validation:
invalid date ordering, required fields, invalid/empty states where reachable, reset after error.

Backend/DB reads may verify resulting run IDs and counts only after browser creation.

Update UI inventory statuses.

Create `docs/evidence/phase8/05_SYSTEM_BROWSER_HISTORICAL_ANALYSIS_REPORT.md`.

STOP.
