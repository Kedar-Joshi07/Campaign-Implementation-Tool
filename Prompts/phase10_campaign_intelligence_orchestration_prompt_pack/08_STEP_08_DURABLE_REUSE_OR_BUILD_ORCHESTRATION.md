# Step 8 — Durable Reuse-or-Build Orchestration

Create a persistent Phase 10 parent workflow.

Technical stages:
CHECKING_COMPATIBILITY
RESOLVING_HISTORICAL_CONTEXT
CHECKING_TRAINING_ELIGIBILITY
RESOLVING_MODEL
VALIDATING_MODEL
RESOLVING_SCORING
SCORING_POTENTIAL_CUSTOMERS
PREPARING_TARGET_GROUP
VERIFYING_FINAL_CURRENTNESS
READY

Business labels:
Checking available targeting intelligence
Checking verified past campaign history
Confirming enough past examples
Preparing targeting intelligence
Verifying targeting quality
Checking potential-customer coverage
Matching the full potential-customer universe
Preparing Target Group insights
Final verification
Targeting intelligence ready

Use existing persistent job framework safely, e.g. job type
CAMPAIGN_TARGETING_PREPARATION, while phase10_orchestration_runs stores detailed state.

Before heavy work persist reuse plan:
analysis/model/scoring/rank = REUSE or BUILD.

Idempotency:
same exact intelligence key returns existing active orchestration or READY generation.
Never duplicate full 5M scoring.

Contexts with same Modeling Context/current source/policies may share generation,
including different delivery channels.

Progress must be monotonic. Suggested ranges:
0-10 compatibility, 10-20 historical, 20-25 eligibility, 25-45 model,
45-50 validation, 50-90 scoring, 90-98 rank, 98-100 verify.
Map child scoring progress into parent 50-90.

FAILED: safe business message, no partial READY.
BLOCKED: insufficient history, not a technical failure.

Startup reconciliation must inspect durable child/asset state; retry resumes highest verified stage.

Add explicit tests proving no nested single-worker executor deadlock.

Evidence:
`docs/evidence/phase10/08_ORCHESTRATION_ENGINE.md`

STOP.
