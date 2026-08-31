# Step 7 — Final Regression and Phase 7 Freeze

Use HEAD from Step 6.

Do not implement Phase 7.

Run on the ACTUAL final code:

```text
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
python scripts/validate_data.py --json
```

Also run dedicated Phase 6 audience/hardening suites.

## Revalidate Phase 6

Resolve canonical IDs dynamically.

Expected lineage remains the accepted chain around:
- analysis 12;
- model 8;
- scoring 8;

but never hard-code these in runtime.

Verify:
- scoring provenance canonical;
- historical source current;
- demographic source current;
- deterministic Phase 5 sample re-score still verified;
- exactly 100 boundaries;
- exact 5M percentile/decile/band reconciliation;
- keyset pagination no duplicates/gaps;
- saved validation audience current;
- historical-positive profile reconciliation;
- no Phase 7 surfaces.

## Contract closure

Verify:
- TOP_N runtime now matches Selection Contract v1;
- preparation list/status distinguish prepared vs current-ready;
- real rank-preparation metrics are persisted;
- real 5M performance evidence exists;
- synthetic evidence is clearly labeled;
- generated SQLite artifact DB is no longer tracked;
- PII policy metadata matches frozen deny-list.

## Refresh

Update:

```text
docs/PHASE_6_IMPLEMENTATION_SUMMARY.md
docs/evidence/phase6_5m_acceptance.json
docs/evidence/phase6_real_5m_performance.json
Prompts/phase6_prompt_pack/02_PROGRESS_TRACKER.md
Prompts/phase6_prompt_pack/03_ACCEPTANCE_CHECKLIST.md
Prompts/phase6_prompt_pack/04_PHASE_7_HANDOFF_CONTRACT.md
```

Do not rewrite root README.

## Repository hygiene

Run:

```text
git status --short
git ls-files artifacts/*.db
```

No generated validation DB should remain tracked.

## Commit

Create a dedicated finalization commit, e.g.:

`fix: finalize phase6 contracts and phase7 handoff evidence`

After commit:

```text
git rev-parse HEAD
```

The resulting SHA becomes the candidate Phase 7 baseline.

## Final report

Return:
1. starting SHA `b2cdfa95713aa2f8d9309be4881079f703df1831`;
2. final SHA;
3. files changed;
4. schema version;
5. TOP_N fix;
6. max valid TOP_N for current universe;
7. preparation readiness semantics;
8. rank prep scanned rows;
9. rank prep chunk count;
10. rank prep runtime;
11. rank prep rows/sec;
12. real 5M search timings;
13. real 5M profile timings;
14. saved audience timing/currentness;
15. synthetic evidence correction;
16. artifact DB cleanup;
17. PII metadata completion;
18. canonical analysis/model/scoring IDs;
19. boundary count;
20. exact band counts;
21. saved validation audience status;
22. deterministic re-score;
23. pytest result;
24. pip check;
25. compileall;
26. diff check;
27. validate_data;
28. no Phase 7 implementation;
29. GO / CONDITIONAL GO / NO-GO.

STOP.
