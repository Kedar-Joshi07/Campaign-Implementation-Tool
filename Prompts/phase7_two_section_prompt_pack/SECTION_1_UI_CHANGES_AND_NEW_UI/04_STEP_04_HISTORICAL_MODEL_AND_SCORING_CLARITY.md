# Step 4 — Historical, Model & Scoring Clarity

## Historical analyses
Show:
- CURRENT — eligible for training
- STALE — historical only

Stale run remains inspectable but must not look trainable.

## Model metrics
Rename to:
- Recall @ Top 5% / 10% / 20%
- Lift @ Top 5% / 10% / 20%
- Top-10% Lift / Recall

Explain these percentages refer to the highest-scored validation population.

Retain:
- U is not confirmed negative;
- score is not purchase probability;
- BAGGING_PU remains governed primary.

## Scoring currentness card
Show:
Historical source | Current
Demographic source | Current
Model/artifact | Verified
Scoring run | Canonical

Use lightweight checks only.

## Model-list N+1
Avoid one model-detail/artifact call per list row.
Include bounded quality flags in list or lazy-load detail.

Add tests. STOP.
