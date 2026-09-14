# Phase 10 — Automatic Campaign Intelligence & Targeting Orchestration

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`
Frozen Phase 9 baseline: `7e54754053bf998e65c59a36c0096d5404bb6479`

## Mission
Turn the Phase 9 Campaign Planner into a complete automatic intelligence workflow for
business users. Users define a campaign and targeting preferences; the system decides
whether valid targeting intelligence can be reused or whether missing analytical stages
must be built.

## Target flow
Campaign Details
→ Campaign Context
→ Modeling Context
→ exact compatibility resolution
→ reuse or build Historical Analysis / model / full-universe scoring / rank analytics
→ Targeting Intelligence READY
→ existing Phase 9 Target Group Preview
→ immutable Saved Target Group
→ Campaign Draft
→ governed Phase 7 export

## Critical distinction
The full Campaign Context remains the Phase 9 business object.
Phase 10 adds a separate Modeling Context for analytical compatibility.

Modeling Context includes:
- product_ids
- campaign_types
- campaign_categories
- offer_types
- historical_campaign_channels
- governed historical-window policy
- conversion policy
- multi-product positive policy

Modeling Context excludes:
- delivery channel
- campaign name/description/launch date
- Match Strength
- demographic targeting filters
- top percentage/TOP_N
- Target Group name/description

## Non-negotiable rule
Never implement “latest run wins”. Reuse requires exact compatibility and currentness.

## Sequential steps
1. Baseline reconciliation & Phase 9 freeze
2. Context identity & policy contracts
3. Extend historical context filtering
4. Phase 10 schema/registry/repositories
5. Historical compatibility & eligibility
6. Model compatibility/reuse/validation
7. Scoring/rank compatibility/reuse
8. Durable reuse-or-build orchestration
9. Phase 10 API & Phase 9 bridge
10. Business UI automatic preparation
11. Intelligence lifecycle/retention
12. Comprehensive Phase 10 test matrix
13. Bounded clean-room Phase 10
14. Real system-browser certification
15. Clean-head full 5M certification
16. Exact-SHA CI, documentation & freeze
