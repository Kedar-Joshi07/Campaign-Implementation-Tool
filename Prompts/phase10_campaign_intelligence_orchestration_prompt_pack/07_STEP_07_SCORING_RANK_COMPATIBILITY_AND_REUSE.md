# Step 7 — Scoring, Rank & Analytics Compatibility / Reuse

Scoring compatible requires:
- COMPLETED
- exact model_run_id
- artifact SHA exact
- feature version/SHA exact
- score semantics exact
- current demographic import/checksum/count
- full universe scored
- distinct score person count == universe
- duplicates 0
- scores finite and 0..1
- canonical scoring currentness

If only demographics changed: reuse analysis/model, full-rescore current prospects, rebuild rank.
Do not retrain.

Rank/analytics ready requires:
- exactly 100 percentile boundaries with correct population
- current analytics snapshot
- ready_for_current_audience_actions=true
- no provenance drift

If scoring compatible but rank stale/missing: rank/analytics only rebuild.

If everything current: no heavy work; register/reuse generation, bind context,
set Phase 9 source_scoring_run_id and READY.

Tests: full reuse, demographic drift, incomplete/duplicate/invalid scores, artifact mismatch,
rank missing, analytics missing, rank contract mismatch, rank-only path, existing Phase9 binding.

Evidence:
`docs/evidence/phase10/07_SCORING_RANK_COMPATIBILITY.md`

STOP.
