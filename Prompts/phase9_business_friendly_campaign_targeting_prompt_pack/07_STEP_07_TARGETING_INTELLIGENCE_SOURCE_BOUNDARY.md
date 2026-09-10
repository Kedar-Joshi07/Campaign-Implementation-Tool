# Step 7 — Targeting Intelligence Source Boundary

## Objective
Make Phase 9 analytically honest before Phase 10 automatic orchestration exists.

## Hard requirement
A Phase 9 Target Group Preview may run only against a current, verified targeting-intelligence/scoring source that is explicitly linked to the planning session.

Do NOT:
- silently use “latest scoring run”
- silently use the first completed model
- imply Product/Offer/Campaign Context changed the model when it did not
- claim the target group is product-specific unless the source is genuinely compatible

## Phase 9 behavior

Introduce a backend business-friendly targeting-source state:

- READY
- NEEDS_REFRESH
- NOT_AVAILABLE
- INCOMPATIBLE_CONTEXT
- STALE

Default business UI:
- “Targeting intelligence is ready”
- “Targeting intelligence needs refresh”
- “Targeting is not yet available for this campaign”

Advanced details may show:
- analysis_run_id
- model_run_id
- scoring_run_id
- feature contract
- source checksums
- artifact SHA

## Temporary Phase 9 source linkage

Until Phase 10 automatic compatibility exists, use one explicit mechanism:
- a server-side configured/selected current scoring run attached to the targeting session/draft;
or
- an advanced analyst/admin action to link a verified current scoring run.

The normal business user must not choose raw scoring_run_id values.

## Phase 10 seam
Design an interface like:

`resolve_targeting_intelligence(context) -> TargetingIntelligenceResolution`

Phase 9 may return NOT_AVAILABLE/explicitly linked source.
Phase 10 will later implement automatic compatibility/reuse/build.

## Blocking behavior
If there is no valid linked source:
- allow campaign context and targeting preferences to be saved as a draft;
- disable exact target preview/save target group;
- explain in plain language that targeting intelligence must be prepared;
- do not fabricate counts.

## Tests
Test all statuses and ensure no unrelated “latest” fallback occurs.

Create:
`docs/evidence/phase9/07_TARGETING_INTELLIGENCE_BOUNDARY_REPORT.md`

STOP.
