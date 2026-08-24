# Single Master Phase 5 Prompt

Implement **Phase 5 — 5M Prospect Scoring Engine** in `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git` from authoritative Phase 4 baseline `fdae4a7a40c846e4038a8ebe656257eb4164cd5d`.

Read all contracts before coding, especially freeze, agent instructions, schema, model/feature, score semantics, job lifecycle, API, UI, performance/privacy and progress tracker.

Frozen input:

```text
PRIMARY=BAGGING_PU
role policy=2
evaluation contract=2
feature contract=1
feature SHA=a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535
```

Outcome:

```text
verified model_run_id
→ async PROSPECT_SCORING job
→ bounded keyset 5M read
→ exact 11 features
→ persisted preprocessor + estimator
→ finite [0,1] score
→ propensity_scores
→ exact completed scoring_run_id
```

Execute only gated steps 1–7 (`03_...` through `09_...`) and STOP after each one. After Step 7 complete acceptance and do not begin Phase 6.

Non-negotiable: no whole-5M load, no OFFSET scoring loop, no customer/person linkage, no PII scoring columns, no refit, no legacy scoring, no individual score API, no Audience Explorer, no score bands/percentiles, no campaign/export, no distributed infrastructure.

Final report must include starting/final SHA, changed files, schema/jobs/tables/indexes, scoreability, chunk/keyset evidence, full regressions, real model/job/scoring IDs, exact 5M reconciliation, score validity min/mean/max, runtime/throughput/chunk/memory/DB growth, artifact/feature SHA, deterministic re-score difference, restart/concurrency, UI walkthrough, scope scan and Go/No-Go Phase 6.
