# Step 1 — Baseline Audit & Phase 10 Freeze

## Objective
Prove the Phase 10 baseline is trusted and identify every Phase 11 seam before changing code.

Record:
- branch/HEAD/origin
- clean git status
- schema version
- exact Phase 10 contract/policy versions
- latest exact-SHA CI
- current UI navigation
- current Campaign Planner controls
- current campaign/export profiles
- current demographic columns
- current Phase 10 generation/orchestration schema
- current Phase 9 Saved Target Group schema
- current export audit schema
- current 5M scoring behavior/reuse evidence

Explicitly confirm current facts:
- export profiles only EMAIL/DIRECT_MAIL;
- historical campaign data contains additional channels;
- demographics contains email/phone/address but no governed push/ad/web identifiers;
- Phase 10 already reuses intelligence when Modeling Context is unchanged;
- filter/delivery changes are supposed to avoid model/scoring rebuilds.

Create a frozen-signature inventory for Phase1–10 contracts that Phase11 must not silently modify.

Identify frontend components that will be hidden versus components that remain visible.

Identify exact lower-level service calls to:
- prepare Phase10 intelligence;
- resolve Phase9/10 source currentness;
- estimate/search/profile target group;
- save immutable target group;
- resolve campaign members;
- export channel-specific members.

Evidence:
`docs/evidence/phase11/01_BASELINE_AUDIT.md`

No feature implementation yet. STOP.
