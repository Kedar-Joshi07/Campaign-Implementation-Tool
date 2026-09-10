# Step 1 — Phase 9 Baseline & Gap Analysis

## Objective
Establish the exact Phase 1–8 baseline and identify every place where the current UI exposes technical/ML concepts to a business user.

## Required baseline
Start from the frozen Phase 1–8 SHA recorded in the pack README.

Record:
- local branch / HEAD / remote main
- clean git status
- schema version
- app version
- frozen contract versions
- current UI navigation/pages
- current Audience Explorer controls
- current Campaign Builder controls
- current API surface
- current saved-audience/campaign lineage
- current system-browser test inventory
- latest CI status

## Business-user gap review
Walk the complete UI as if the user:
- has no ML knowledge
- has no data-science vocabulary
- knows only the campaign they want to run and the type of people they want to reach

Identify:
- technical terms that block understanding
- screens that force technical workflow order
- controls that require analyst knowledge
- outputs that lack plain-language explanation
- places where technical provenance is useful only for advanced users
- current campaign fields missing from business workflow
- missing demographic targeting buckets
- missing “why these people?” explanation
- missing match-strength recommendations
- confusing distinction between historical customers and 5M potential customers

## Frozen behavior inventory
Explicitly list what Phase 9 MUST reuse unchanged:
- historical-analysis engine
- model-training engine
- scoring engine
- Audience estimate/search/profile
- saved-audience immutability
- campaign currentness/finalization/export
- PII/export boundary

## Evidence
Create:
`docs/evidence/phase9/01_PHASE9_BASELINE_AND_GAP_REPORT.md`
`docs/evidence/phase9/01_phase9_gap_register.json`

Do not implement functionality yet.

STOP.
