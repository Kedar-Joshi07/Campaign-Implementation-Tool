# Phase 10 Handoff Contract

Phase 9 must leave clean extension points for Phase 10.

Phase 9 captures:
- campaign business context
- normalized targeting criteria
- business-friendly match-strength request
- target-group preview requirements
- target-group save/campaign draft workflow
- technical-detail progressive disclosure
- current targeting-intelligence source reference, when one is explicitly linked

Phase 10 will add:
- canonical Campaign Targeting Context hashing
- automatic historical-analysis compatibility
- automatic model compatibility
- automatic scoring-run compatibility
- reuse of valid current intelligence
- build/refresh orchestration when missing
- long-running progress state
- context-specific model/scoring provenance
- scoring lifecycle/retention

Phase 9 MUST NOT implement fake automatic compatibility by “latest run wins”.
