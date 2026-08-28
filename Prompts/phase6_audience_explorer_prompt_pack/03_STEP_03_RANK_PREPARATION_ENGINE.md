# Step 3 — Deterministic Percentile/Rank Preparation Engine

Use HEAD from successful Step 2. Do not implement search/profile/UI yet.

## Objective

Build a memory-bounded job that scans existing Phase 5 scores once in canonical order and persists only 100 percentile boundary rows.

Do NOT recompute scores, update propensity_scores, materialize 5M ranks, use OFFSET, or load 5M rows into Python memory.

## Input gate

Before submit/run:
- scoring_run_id valid;
- run COMPLETED;
- full Phase 6 canonical currentness/provenance gate passes;
- score count reconciles;
- if 100 boundaries already exist for same run/contract, return conflict/already-prepared rather than duplicate.

## Concurrency

Reuse shared `ProcessPoolExecutor(max_workers=1)`.

Audience preparation conflicts with active model training/prospect scoring/other preparation and vice versa. Return 409 using existing patterns.

## Keyset score scan

Use existing rank index `(scoring_run_id, propensity_score DESC, person_id ASC)`.

Initial:
```sql
WHERE scoring_run_id=?
ORDER BY propensity_score DESC, person_id ASC
LIMIT ?
```

Next:
```sql
WHERE scoring_run_id=?
AND (propensity_score < ? OR (propensity_score = ? AND person_id > ?))
ORDER BY propensity_score DESC, person_id ASC
LIMIT ?
```

Suggested chunk 100,000 with hard bounds. Read only person_id + score.

## Boundary algorithm

For N exact score rows and p=1..100:
`target_rank[p] = ceil(N*p/100)`

Stream with 1-based global rank. When a target rank is reached, capture bucket, rank, score, person_id, N.

For test populations N<100 use `max(1, ceil(N*p/100))`; duplicate target ranks across different buckets are permitted. Classification selects the smallest bucket whose boundary contains the row.

## Transactional publication

Flow:
```text
validate provenance
capture source snapshot
stream scores and compute 100 boundaries in memory
revalidate provenance and count
single transaction publishes exactly 100 rows
verify persisted completeness
mark job COMPLETED
```

If source/currentness changes mid-run, fail and publish no new complete boundary set.

## Pure helpers

Implement testable:
- classify_percentile_bucket(score, person_id, boundaries)
- classify_decile(bucket)
- classify_rank_band(bucket)

Ties use person_id ASC.

## APIs

Implement:
- POST `/api/audience/runs/{scoring_run_id}/prepare`
- GET `/api/audience/runs/{scoring_run_id}/preparation-status`
- GET `/api/audience/runs`

Run-level responses only; never return person IDs from preparation/job public payloads.

## Tests

Boundary math, ties, N<100, no OFFSET, no gaps/duplicates, 100 rows, percentile100=N, re-run conflict, stale run rejection, source drift mid-run, compute exclusion, restart reconciliation, no IDs in job payload, no 5M rank table, regressions.

STOP.
