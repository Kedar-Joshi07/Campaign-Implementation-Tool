# Master Guardrails

Phase 1–8 frozen baseline: `d6a9f9b963622a334bf3e5c3220e5d0a73e528fe`
Phase 9 pre-fix baseline: `6934c586780b5f8f5bd57d533b5597ea63dec8cc`

## Hard rules
- Preserve Phase 1–8 contracts and behavior.
- Preserve Phase 9 business workflow and terminology.
- Preserve match-strength thresholds, age/income contracts, OR-within/AND-across semantics.
- Preserve explicit targeting-intelligence source linkage.
- Never add a “latest scoring run wins” fallback.
- Never collapse disjoint Phase 9 branches into one broad min/max filter.
- Never silently show only branch #1 as the complete definition.
- Preserve Saved Target Group immutability and Phase 7 export/member semantics.
- Preserve the no-PII planning/preview boundary.
- Preserve the Phase 9/Phase 10 boundary.
- Use installed Chrome preferred, Edge fallback, for final browser certification.
- Final GO requires exact-SHA green CI.

## Multi-branch truth rule
For Phase 9 groups with multiple branches, the authoritative targeting definition is the complete branch set stored in Phase 9 metadata.

If legacy Audience Explorer cannot faithfully replay the complete branch set, it MUST block/redirect reopen rather than present an incomplete definition.
