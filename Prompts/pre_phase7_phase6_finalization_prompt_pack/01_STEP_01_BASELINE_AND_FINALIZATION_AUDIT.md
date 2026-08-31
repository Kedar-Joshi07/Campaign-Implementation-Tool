# Step 1 — Baseline and Finalization Audit

Required starting SHA:

`b2cdfa95713aa2f8d9309be4881079f703df1831`

Do not modify code.

Run:

```text
git rev-parse HEAD
git status --short
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
python scripts/validate_data.py --json
```

HEAD must equal `b2cdfa95713aa2f8d9309be4881079f703df1831`.

If there are unexplained worktree changes, STOP.

Record:
- schema version;
- current canonical analysis/model/scoring IDs;
- audience boundary count;
- saved audience count;
- test count.

Confirm these known issues:

1. Runtime contains an arbitrary `TOP_N` cap around 1,000,000 while Selection Contract v1 says `TOP_N <= current prospect universe`.
2. `/api/audience/runs` and `/preparation-status` do not clearly distinguish `prepared` from `current/canonical and ready`.
3. AUDIENCE_PREPARATION result does not persist real `scanned_rows`, `chunk_count`, `largest_chunk_rows`, `runtime_seconds`, `rows_per_second`.
4. Step 8 query timing evidence is synthetic, not real 5M performance evidence.
5. `artifacts/phase6_step8_perf_security.db` is tracked.
6. Runtime `_PII_POLICY` metadata omits some frozen blocked fields.

Create sanitized:

`docs/evidence/phase6_prephase7_finalization_baseline.json`

No absolute paths, PII, person IDs, SQL, or tracebacks.

STOP.
