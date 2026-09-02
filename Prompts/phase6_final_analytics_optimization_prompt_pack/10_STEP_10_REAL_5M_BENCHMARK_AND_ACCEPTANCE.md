# Step 10 — Real 5M Service Benchmark & Acceptance

## Objective
Benchmark actual application services, not SQL approximations.

Create/update `docs/evidence/phase6_final_analytics_performance.json`.

## Required timings
Measure audience runs, preparation status, options, estimate all/top1/top-decile/state/age+income/rank+state, search first/next/state/top1, profile no-filter all/top1/demographic ALL_MATCHING/filtered TOP_N 50K, saved list/detail/currentness, save without/with profile, scoring status/detail.

## Required targets
- options <2 sec (preferred <0.5)
- estimate all <1 sec
- rank-only estimates <2 sec
- search typical <2 sec
- profile no-filter all <2 sec
- profile top1 <=60 sec threshold
- filtered TOP_N 50K <=60 sec threshold
- save with profile <=60 sec threshold
- heavy bounded flows in 120-180 sec are acceptable when authenticity, quality, and usefulness are preserved and no contract/provenance drift occurs
- saved currentness <5 sec
- scoring status/detail <5 sec (preferred <2)

If options/profile remain multi-minute, or if performance gains weaken correctness/provenance/usefulness: NO-GO.

## Query plans/index evidence
Capture safe plan summaries for important dynamic queries and before/after index evidence. Record DB bytes/page_count/page_size and snapshot/index size impact.

## Final deep integrity audit
Run one explicit deep validation: 5,000,000 score rows, 5,000,000 distinct person IDs, duplicates=0, invalid FK=0, valid score range, aggregate reconciliation, historical source current, demographic source current.

Run deterministic rescore sample_size=256 with verified=true and max_abs_diff=0.0.

## Analytics reconciliation
Verify snapshot population=5M, 100 percentile buckets, bucket total=5M, universe profile=5M, historical-positive count equals analysis positive count, every universe categorical dimension totals 5M.

Expected rank bands: ELITE 50k; VERY_HIGH 200k; HIGH 250k; MEDIUM 750k; LOW 1.25M; VERY_LOW 2.5M.

## Full gates
Run pip check, full pytest, compileall app/scripts/tests, git diff --check, validate_data --json. Record exact test count and note validation is local unless CI exists.

STOP unless all required targets/integrity gates pass.

Quality precedence rule: data and process quality gates overrule timing outcomes. A faster run with degraded semantic integrity is a failure.
