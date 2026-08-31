# Step 5 — Real 5M Phase 6 Performance Evidence

Use HEAD from Step 4.

## Separate evidence types

Keep Step 8 evidence as:

`Synthetic bounded query-plan/index validation`

Do NOT describe synthetic timings as real 5M performance.

Remove absolute local paths from committed evidence.

## Capture real 5M timings

Capture actual elapsed time for:

1. unfiltered first page;
2. next keyset page;
3. top 1% estimate/search;
4. top decile estimate;
5. state filter;
6. age + income filter;
7. rank band + state;
8. audience estimate;
9. top 1% profile;
10. filtered TOP_N 50K profile;
11. saved audience list;
12. saved audience detail/currentness;
13. clean rank preparation on a copied DB using Step 4 instrumentation.

Record only safe aggregate values.

Create:

`docs/evidence/phase6_real_5m_performance.json`

Suggested sections:

```text
canonical_context
rank_preparation
search
estimate
profile
saved_audience
index_signals
environment_notes
```

No PII, person IDs, raw SQL, absolute paths, or tracebacks.

These are local POC measurements, not production SLAs.

Do not add indexes unless real evidence justifies them.

If an index is added, record before/after timing and DB-size effect.

STOP.
