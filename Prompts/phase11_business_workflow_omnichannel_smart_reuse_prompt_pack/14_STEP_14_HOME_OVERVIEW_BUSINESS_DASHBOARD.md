# Step 14 — Home / Overview Business Dashboard

## Objective
Provide a clean entry point without technical operational clutter.

Business-safe cards:
- Potential Customers Available
- Search Runs
- Completed Results
- Latest Result Count
- optionally Results This Month

Recent Results:
show latest bounded 5–10 search runs with status/count/profile and View action.

Primary CTA:
Find Potential Customers

Do not show:
- model IDs
- analysis IDs
- scoring IDs
- PU counts
- artifacts
- rank boundary technical metrics

Technical backend unavailable state:
clear business message + retry; successful retry restores global backend online state.

Use bounded aggregate queries and avoid full 5M scans on every Home load.
Reuse metadata/current aggregates where possible.

Evidence:
`docs/evidence/phase11/14_HOME_OVERVIEW.md`

STOP.
