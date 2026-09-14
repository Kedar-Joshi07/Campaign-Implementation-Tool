# Step 6 — Model Compatibility, Reuse & Validation

Compatible model requires:
- COMPLETED
- exact compatible analysis linkage
- cohort counts reconcile
- governed PRIMARY selected
- exact feature contract version/SHA
- exact model-role policy
- exact evaluation contract
- compatible automated-training policy
- artifact exists, SHA verifies and loads
- preprocessing/hyperparameter/evaluation metadata valid
- no prohibited model input

Search Phase 10 CURRENT/REUSABLE generations first. If none, discover old model runs linked
to exact analysis. Filter every candidate for exact compatibility BEFORE deterministic
selection. Record compatible/rejected candidates and reasons.

If missing, train using existing governed service/core. Preserve seed/policy,
Bagging PRIMARY, challenger-only Elkan–Noto and diagnostic non-selectability.

Executor rule:
inside parent Phase 10 worker, persist child job metadata if needed but invoke the safe
synchronous training worker/core directly. Never submit into the same single-worker pool
and wait.

Before scoring verify COMPLETED model, PRIMARY, artifact/feature/policy/evaluation integrity.

Tests: exact reuse; wrong analysis/feature/policy/evaluation; challenger selected;
missing/corrupt artifact; failed run; deterministic candidate selection; fresh training.

Evidence:
`docs/evidence/phase10/06_MODEL_COMPATIBILITY.md`

STOP.
