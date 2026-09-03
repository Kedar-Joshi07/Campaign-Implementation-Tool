# Hardening Step 1 — Baseline & Large-Export Profiling

Record committed baseline:
- EMAIL TOP_N 1K: ~7–8 sec
- DIRECT_MAIL TOP_N 50K: ~30 sec
- filtered DIRECT_MAIL ~416,275 rows: ~14 minutes in browser E2E

Do not assume the 14-minute runtime is necessary.

Instrument actual export path without logging PII and measure:
- currentness validation
- query-context creation
- member-selection query time per chunk
- number of member-selection queries
- rows returned per query
- percentile/rank classification CPU
- temp ID table delete/insert
- contact join
- deliverability validation
- CSV serialization
- SHA update
- export-event writes
- final currentness

Capture safe query-plan summaries for:
- unfiltered TOP_N
- state+age ALL_MATCHING
- large rank-only ALL_MATCHING
- direct-mail contact retrieval

Do not log raw contact values, person IDs, SQL with user values, or filesystem paths.

Create:
`docs/evidence/phase7_export_profiling_baseline.json`

Identify dominant unnecessary work before optimizing. STOP.
