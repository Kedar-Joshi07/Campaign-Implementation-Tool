# Phase 10 Policy & Decision Contract

Introduce versioned constants:
- PHASE10_MODELING_CONTEXT_CONTRACT_VERSION=1
- PHASE10_COMPATIBILITY_CONTRACT_VERSION=1
- PHASE10_HISTORICAL_WINDOW_POLICY_VERSION=1
- PHASE10_MULTI_PRODUCT_POSITIVE_POLICY_VERSION=1
- PHASE10_TRAINING_ELIGIBILITY_POLICY_VERSION=1
- PHASE10_AUTOMATED_TRAINING_POLICY_VERSION=1
- PHASE10_ORCHESTRATION_CONTRACT_VERSION=1
- PHASE10_INTELLIGENCE_GENERATION_CONTRACT_VERSION=1
- PHASE10_LIFECYCLE_POLICY_VERSION=1

Historical Window v1: use the complete currently available canonical contact-date
range and persist exact from/to dates.

Conversion v1:
- contacted_only=true
- conversion_definition=ATTRIBUTED_PURCHASE

Multi-product v1:
- exact combined context
- positive customer if ANY qualifying row for ANY selected product is positive
- customer appears once
- no per-product model score fusion

Phase 10 must add historical filtering for campaign_categories and offer_types.

Training eligibility:
Do not invent arbitrary thresholds. Derive and freeze policy v1 from existing training
constraints plus deterministic diagnostics on representative canonical contexts.
At minimum govern selected/P/U counts and validation split viability. Once selected,
values become code constants and boundary tests.

Automated training v1 unless frozen contracts dictate otherwise:
- seed 42
- validation_fraction 0.20
- governed PRIMARY Bagging PU
- Elkan–Noto challenger enabled
- challenger cannot promote

Invalidation matrix:
- campaign name/description/date: reuse all
- delivery channel: reuse all
- prospect targeting filters: reuse all intelligence
- modeling context dimension: re-resolve historical and downstream
- customer/campaign-sales source: rebuild historical/model/scoring
- feature/model/evaluation policy: reuse analysis, rebuild model/scoring
- demographics source: reuse analysis/model, rescore + rank
- rank/analytics only stale: reuse scoring, rebuild rank only

Lifecycle v1:
CURRENT, REUSABLE, SUPERSEDED, STALE, RETIREMENT_ELIGIBLE, PROTECTED.
No automatic physical deletion.
