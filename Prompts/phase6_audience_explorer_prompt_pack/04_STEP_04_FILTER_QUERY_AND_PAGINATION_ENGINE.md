# Step 4 — Filter, Estimate, Search, and Keyset Pagination Engine

Use HEAD from successful Step 3. Do not implement profile/save/UI yet.

## Objective

Provide safe bounded access to the 5M scored universe with approved fields, strict filters, prepared rank boundaries, and keyset pagination.

Prefer modules following existing conventions, e.g. audience contracts/repository/service/schema/router.

## Currentness gate

Every options/estimate/search request validates current scoring, historical source, demographic source, and complete rank boundaries. Missing boundaries return readiness error; read endpoints must not silently start preparation.

## GET /api/audience/options

Input scoring_run_id. Return aggregate-only:
- scoring summary and population count;
- score min/max;
- rank definitions;
- numeric min/max for approved fields;
- distinct approved categorical values/counts;
- PII policy and score semantics.

No people/IDs.

## Canonical filter normalizer

One strict normalizer shared by estimate/search/profile/save. Produce typed normalized object, canonical JSON, and SHA-256 filter hash.

Reject unknown keys. Parameterized SQL only.

## Rank predicates

Top P% is bounded by percentile boundary tuple:
```text
score > boundary_score
OR (score = boundary_score AND person_id <= boundary_person_id)
```

Define deterministic range predicates for deciles/bands. Multiple values OR within the same field; different fields AND together. Ranking filters intersect with score/demographic filters.

## POST /api/audience/estimate

Request:
```text
scoring_run_id
filters
selection {mode,target_count?}
```

Return aggregate-only matching_count, selected_count, score min/mean/max as practical, filter hash, normalized selection, source_verified.

TOP_N selected_count = min(target, matching_count).

## POST /api/audience/search

Request scoring_run_id, filters, page_size, cursor.

Page size default 50, min1, max100. Fixed order score DESC/person_id ASC. No arbitrary sorts.

Cursor: opaque/versioned, containing at least scoring_run_id, last score, last person_id, filter hash, rank contract version. Reject malformed/mismatched cursors.

Projection MUST be explicit:
- p.person_id
- p.propensity_score
- d.age
- d.gender
- d.state
- d.individual_yearly_income
- d.marital_status
- d.education
- d.employment_status
- d.resident_status
- d.resident_type
- d.family_member_count
- d.type_of_employment

Never `SELECT d.*`.

Enrich page rows with percentile_bucket, decile, rank_band from 100 boundaries.

Next-page predicate:
```text
p.propensity_score < last_score
OR (p.propensity_score = last_score AND p.person_id > last_person_id)
```

No OFFSET.

Response rows, next_cursor/null, has_more, filter_hash, scoring_run_id, score semantics. Use estimate as authoritative count endpoint rather than counting every page.

## Tests

Cover every filter type, OR-within/AND-across semantics, rank filters/intersections, page no gaps/duplicates, tie ordering, cursor tampering/mismatch, page size, injection strings, exact response allowlist, PII absence, stale/unprepared run, no OFFSET, regressions.

STOP.
