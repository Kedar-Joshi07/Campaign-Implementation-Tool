# Step 4 — Real Rank-Preparation Metrics

Use HEAD from Step 3.

Instrument actual Phase 6 rank preparation to record:

```text
scanned_rows
chunk_size
chunk_count
largest_chunk_rows
runtime_seconds
rows_per_second
boundary_count
total_population
```

Persist bounded metrics in the AUDIENCE_PREPARATION job `result_json`.

Do not expose person IDs or cursor person IDs.

Do not fake metrics for already-completed historical preparation jobs.

For old jobs, metrics may be absent or `metrics_available=false`.

## Real measurement

Use a COPY of the canonical POC DB.

In the copy:
1. retain Phase 1–5 data/scores;
2. remove only Phase 6 boundary/preparation state required to allow a clean run;
3. run rank preparation;
4. capture real metrics;
5. discard the copied DB afterward.

Do not modify canonical Phase 5 scores.
Do not rerun Phase 5 scoring.

## Tests

- multi-chunk scan metrics;
- chunk_count correct;
- largest_chunk_rows correct;
- scanned_rows equals score count;
- runtime finite/non-negative;
- rows/sec finite/non-negative;
- public result has no person IDs;
- failure does not report fake completed metrics;
- full regressions pass.

STOP.
