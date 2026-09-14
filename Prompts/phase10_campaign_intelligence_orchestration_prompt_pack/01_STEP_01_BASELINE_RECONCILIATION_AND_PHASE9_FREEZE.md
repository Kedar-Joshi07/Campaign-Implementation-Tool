# Step 1 — Baseline Reconciliation & Phase 9 Freeze

Start exact SHA `7e54754053bf998e65c59a36c0096d5404bb6479`.

Record branch/HEAD/origin/status, schema version, Phase 9 contract versions, GO evidence,
exact-SHA CI, canonical imports/checksums/counts, feature contract, model-role/evaluation
policies, current scoring context and rank readiness.

Create a do-not-change inventory for feature contract, PU governance, score semantics,
rank semantics, campaign/export contracts, Phase 9 buckets/match strengths,
multi-branch save and safe legacy reopen.

Inventory callable existing functions for:
Historical Analysis creation/reopen, cohort reconstruction, model-run creation,
synchronous training worker/core, scoring-run creation, synchronous scoring worker/core,
rank/analytics preparation, currentness verification and persistent jobs.

Explicitly document which functions submit to ProcessPool vs which are safe to call
inside a parent worker. Prevent nested single-worker deadlock.

Evidence:
`docs/evidence/phase10/01_BASELINE_AND_ARCHITECTURE.md`

No Phase 10 feature implementation yet. STOP.
