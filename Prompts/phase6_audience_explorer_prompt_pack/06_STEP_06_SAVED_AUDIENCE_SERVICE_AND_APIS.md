# Step 6 — Immutable Saved Audiences and APIs

Use HEAD from successful Step 5. Do not implement UI yet.

## Objective

Persist reproducible audience definitions Phase 7 can consume later without copying millions of member IDs.

## POST /api/audiences

Request:
```text
audience_name
description?
scoring_run_id
filters
selection
```

Flow:
1. validate current canonical scoring run;
2. validate prepared rank metadata;
3. normalize filters;
4. normalize selection;
5. estimate audience;
6. require selected_count >=1;
7. optionally generate aggregate profile snapshot using existing profile service;
8. capture full historical + demographic + model provenance;
9. persist immutable saved audience;
10. return bounded detail.

No row-level member persistence.

## Persist exact provenance

Store scoring_run_id, model_run_id, analysis_run_id, customer/campaign/demographic import IDs and checksums, artifact SHA, feature contract version/SHA, filter/rank/selection contract versions, canonical filters/selection JSON, resolved_count, profile summary.

## Currentness helper

Implement `validate_saved_audience_currentness(audience_id)` or equivalent.

Verify saved scoring run/model/artifact/feature governance, historical source, demographic source, supported contracts, and available rank boundaries. Return is_current + issues. Do not mutate the saved row when it becomes stale.

## GET /api/audiences

Bounded metadata pagination: default 20, max100. OFFSET is acceptable only here because this table is small.

Return audience_id, name, description, created_at, mode, resolved count, scoring/model IDs, currentness and compact stale reason. No people.

## GET /api/audiences/{audience_id}

Return normalized definition, selection, captured provenance, aggregate profile snapshot, currentness, score semantics, PII/export policy. Do not silently recompute profile.

## Immutability

No UPDATE/PATCH in Phase 6. Changes create a new saved audience. Prefer no destructive DELETE endpoint.

Duplicate names are allowed; identity is audience_id.

Add a replay helper that reconstructs the saved definition for preview/profile and future Phase7 use without materializing all members.

## Tests

Save ALL_MATCHING and TOP_N, count correctness, empty rejection, name/description validation, deterministic JSON, complete provenance, stale demographic/historical/artifact cases, immutable history, list pagination, no member table, no PII, no export API, regressions.

STOP.
