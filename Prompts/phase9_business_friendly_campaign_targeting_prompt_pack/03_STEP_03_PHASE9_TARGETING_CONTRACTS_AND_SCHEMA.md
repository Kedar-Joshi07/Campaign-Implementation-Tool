# Step 3 — Phase 9 Targeting Contracts & Schema

## Objective
Create versioned backend-owned contracts for business targeting criteria and campaign-context capture.

## Contracts

Introduce constants similar to:

`TARGETING_SEGMENT_CONTRACT_VERSION = 1`
`CAMPAIGN_TARGETING_CONTEXT_CONTRACT_VERSION = 1`
`BUSINESS_MATCH_STRENGTH_CONTRACT_VERSION = 1`

## Match-strength thresholds
Business-facing values:

- VERY_STRONG = score >= 0.90
- STRONG = score >= 0.80
- GOOD = score >= 0.70
- BROAD = score >= 0.60

Display numeric threshold for transparency.

These are cumulative thresholds, NOT 0.10 buckets.

Separately define non-overlapping score bands:
- 0.90–1.00
- 0.80–<0.90
- 0.70–<0.80
- 0.60–<0.70
- etc. as needed for distribution.

## Age buckets
Version and own server-side:
- 18–24
- 25–34
- 35–44
- 45–54
- 55–64
- 65–74
- 75+

## Income groups
Version and own server-side:
- <25K
- 25K–49,999
- 50K–74,999
- 75K–99,999
- 100K–149,999
- 150K–249,999
- 250K+

## Campaign context contract
Capture canonical arrays/fields for:
- product IDs
- campaign types
- campaign categories
- offer types
- campaign channel
- optional historical-channel intent if separately represented

Normalize:
- trim strings
- reject unknown values
- remove duplicates
- sort multi-select arrays canonically

## Prospect targeting contract
Map business controls to existing Audience Filter Contract without changing semantics.

## Persistence
Use an additive migration only.

Preferred design:
- a new campaign-targeting-draft/context table OR additive context JSON/hash fields tied to the campaign/draft
- normalized JSON
- contract version
- timestamps
- source targeting/scoring reference where explicitly linked

Do NOT add one database column for every checkbox unless there is a compelling reason.

## Tests
Add schema, normalization, validation, canonicalization, and migration tests.

Create:
`docs/evidence/phase9/03_TARGETING_CONTRACT_AND_SCHEMA_REPORT.md`

STOP.
