# Step 2 — Context Identity & Policy Contracts

Create `app/schemas/phase10_intelligence.py` and service support for canonical Modeling Context.

Canonical fields:
product_ids, campaign_types, campaign_categories, offer_types,
historical_campaign_channels, conversion_definition, contacted_only,
historical_window_policy_version, multi_product_positive_policy_version,
plus Modeling Context contract version.

Normalize/deduplicate/sort. Canonical compact JSON. SHA-256 UTF-8.

Keep Phase 9 campaign_context_sha256 unchanged and add a distinct
modeling_context_sha256.

Tests MUST prove delivery channel, campaign details and prospect targeting filters do
not change the Modeling Context hash; modeling dimensions and policy versions do.

Define canonical fingerprints for:
- Historical compatibility: exact resolved filters + customer/campaign checksums + context/policies
- Model compatibility: historical fingerprint + analysis + feature/model/evaluation/training policy
- Scoring compatibility: model fingerprint + artifact + demographics checksum/count + score semantics

Evidence:
`docs/evidence/phase10/02_CONTEXT_IDENTITY_AND_POLICIES.md`

STOP.
