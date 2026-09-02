# Phase 7 Two-Section Prompt Pack

Repository:
`https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Required starting Phase 6 closure SHA:
`0b22fe60b52d4a9b15c2748ae2ef16e9a56241b0`

Substantive Phase 6 implementation parent:
`808df26ec2d3cc11f9382db1d265840cf2b1b3d9`

## Section 1 — UI changes, updates and new UI creation
Clean up Phase 1–6 UI/product-language drift, clarify data meaning/currentness/privacy,
and create the complete Campaign Builder UI shell and multi-step workflow.

## Section 2 — Phase 7 implementation
Implement Campaign Builder persistence, current saved-audience handoff, deterministic
member resolution, explicit minimal contact-PII export contracts, CSV streaming, export
audit metadata, full UI integration, and real 5M acceptance.

## Frozen product boundary
Phase 7 stops at deterministic target-list export. It does NOT activate/send campaigns,
integrate external marketing platforms, create a 5M campaign-member table, link
historical `customer_id` to prospect `person_id`, or persist server-side PII CSV files.

## Frozen Phase 1–6 contracts
- Feature Contract v1 / SHA `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`
- Model Role Policy v2
- Evaluation Contract v2
- PRIMARY `BAGGING_PU`
- exact 11 scoring features
- propensity = relative look-alike affinity, not purchase probability
- order = `propensity_score DESC, person_id ASC`
- Filter / Rank / Selection Contract v1
- Audience Analytics Contract v1
- saved-audience immutability
- current source/model/scoring provenance
- `customer_id` / `person_id` isolation

## Quality-first rule
Performance must be optimized only after correctness, data integrity, business logic,
reproducibility, provenance, and analytical usefulness are satisfied.

Performance optimizations MUST NOT introduce sampling/approximation, semantic changes,
reduced data coverage, weaker validation, altered business results, weaker currentness,
or less useful output.

Interactive lightweight operations should remain responsive. Exact heavy analytics,
preparation, integrity validation, deterministic member resolution, and large target
exports may take about 60 seconds normally and, where exact full-volume work genuinely
requires it, about 120–180 seconds.

Long-running exact work should use clear progress/loading/streaming states rather than
compromising process, logic, data quality, or usefulness.

Optimize unnecessary work, not necessary work.
