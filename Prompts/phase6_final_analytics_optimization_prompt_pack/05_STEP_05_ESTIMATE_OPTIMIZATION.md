# Step 5 — Exact Estimate Fast Paths

## Objective
Eliminate unnecessary 5M scans for cases answerable exactly from metadata/bucket aggregates.

## No-filter fast path
Use `scored_person_count`, `score_min`, `score_mean`, `score_max`. No 5M query. Target `<1 sec`.

## Rank-only fast path
For filters containing only `top_percentile_max`, `deciles`, `rank_bands`, derive exact count and score summary from `score_bucket_stats_json`. Support exact intersections and multiple ranges. No approximation and no full score scan. Target `<2 sec`.

## Demographic-filter estimates
May use SQL, but use lightweight currentness, normalized categorical expressions, and vocabulary validation. Benchmark state, age, income, gender+state, age+income, rank+state. Required common filters `<10 sec`, preferred `<5 sec`.

## Index policy
Do not add speculative indexes. Capture real query plans/timings. Add an index only when a measured important query materially improves. Record before/after timing, DB size impact, and plan change. Avoid combinatorial multi-column indexes.

## Regression
Compare fast-path results to reference SQL on fixtures. Counts exact; floats within explicit tiny tolerance.

STOP until estimate-all `<1 sec` and rank-only `<2 sec`.
