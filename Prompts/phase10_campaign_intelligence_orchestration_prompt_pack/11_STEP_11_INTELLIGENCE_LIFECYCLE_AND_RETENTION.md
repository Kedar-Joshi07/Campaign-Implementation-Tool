# Step 11 — Intelligence Lifecycle & Retention

Because each scoring generation can contain the full prospect universe, Phase 10 must reuse
and classify before building more.

States:
CURRENT, REUSABLE, SUPERSEDED, STALE, RETIREMENT_ELIGIBLE, PROTECTED.

PROTECTED if directly/indirectly referenced by Saved Audience, Phase9 Saved Target Group,
Campaign, finalized Campaign/export audit history, or active orchestration.

A new generation may supersede old; never mutate immutable old groups/campaigns to point to new.

RETIREMENT_ELIGIBLE only when not current, referenced, active or audit-required.

Do NOT automatically delete propensity_scores, scoring_runs, model artifacts/model_runs,
or historical analyses in Phase10 v1.

Touch last_used_at on reuse, preview and target-group save.

Provide no-PII lifecycle report:
counts by state, score-row footprint estimate/count, protection reasons,
reusable contexts, retirement-eligible generations.

Tests: current reuse, protected superseded, unreferenced retirement eligibility,
stale source, active protection, and prove no lifecycle DELETE of analytical data.

Evidence:
`docs/evidence/phase10/11_LIFECYCLE_RETENTION.md`

STOP.
