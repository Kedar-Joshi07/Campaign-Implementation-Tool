# Phase 9 Master Guardrails

## Frozen Phase 1–8 baseline
Start from:
`d6a9f9b963622a334bf3e5c3220e5d0a73e528fe`

Do not modify frozen Phase 1–8 behavior except when an explicit Phase 9 adapter/refactor is required and regression-tested.

## Quality-first rule
Correctness, data integrity, business meaning, reproducibility, provenance, privacy, and validated output take priority over convenience or speed. Do not introduce sampling, approximation, hidden semantic shortcuts, weak compatibility assumptions, or misleading labels merely to make the workflow faster or simpler. Simplify the user experience, not the analytical truth.

## Phase boundary
Phase 9 is the business-user experience and targeting-criteria layer. Phase 10 will add automatic campaign-context model resolution, compatible-model/scoring reuse, and automatic build orchestration. Phase 9 MUST NOT silently pretend that Product, Campaign Type, Campaign Category, Offer Type, or Channel have already changed the model/scoring source unless an explicit compatible targeting-intelligence source is genuinely linked and verified.

## Hard rules
- Do not rewrite the PU model methodology.
- Do not change Feature Contract v1.
- Do not change Model Role Policy v2 or Evaluation Contract v2.
- Do not change prospect/customer identity boundaries.
- Do not add customer_id ↔ person_id mapping.
- Do not expose contact PII in target-group preview.
- Do not call the 5M demographic population “historical customers”.
- Use `Potential Customers` or `People available for targeting`.
- Keep propensity semantics honest: similarity/ranking signal, NOT calibrated purchase probability.
- Do not let Product/Campaign/Offer selectors act as fake demographic filters.
- Product, Campaign Type, Campaign Category, Offer Type, and historical Channel are campaign/model-context dimensions, not prospect-row attributes.
- Phase 9 may capture those context dimensions, but automatic compatibility/model/scoring resolution belongs to Phase 10.
- Do not silently pick an unrelated latest scoring run and imply it is campaign-specific.
- Any target preview must identify a genuinely current validated targeting-intelligence source.
- Preserve Saved Audience immutability/provenance underneath the business-friendly `Saved Target Group` terminology.
- Preserve final campaign export privacy and deliverability rules.
- All final Phase 9 UI certification must use installed system Chrome or Edge, not VS Code embedded browser.
- Every new reachable actionable control must be browser-tested or individually justified as mutually exclusive.
