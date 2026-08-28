# Phase 6 Scope and Contracts

## Baseline freeze

Step 1 was executed against required HEAD:
- `2d90fc1c77d7e332e789d2b0b233e8044148977d`

Phase 6 must consume canonical Phase 5 outputs dynamically and must not hard-code run IDs.

## Canonical input gate (frozen)

Audience Explorer actions are allowed only when the selected scoring run passes current provenance validation:
- scoring run `COMPLETED`
- score count reconciled to snapshot
- model run `COMPLETED`
- selected candidate `BAGGING_PU`
- Model Role Policy v2
- Evaluation Contract v2
- Feature Contract v1 with exact SHA
- artifact SHA verification passes
- linked historical analysis provenance current
- customer/campaign provenance current
- demographics provenance current
- demographics count and min/max envelope current

Any stale completed run is history-only and cannot power current audience actions.

## Audience filter contract v1 (frozen)

- `AUDIENCE_FILTER_CONTRACT_VERSION = "1"`

Allowed numeric filters:
- `score_min`, `score_max`
- `age_min`, `age_max`
- `individual_yearly_income_min`, `individual_yearly_income_max`
- `family_member_count_min`, `family_member_count_max`

Allowed ranking filters:
- `top_percentile_max` integer in `1..100`
- `deciles` list values in `1..10`
- `rank_bands` values in `{ELITE, VERY_HIGH, HIGH, MEDIUM, LOW, VERY_LOW}`

Allowed categorical filters:
- `gender`
- `state`
- `marital_status`
- `education`
- `employment_status`
- `resident_status`
- `resident_type`
- `type_of_employment`

Normalization and validation rules:
- empty list means all values
- lists are deduplicated and deterministically sorted
- score range must be within `[0, 1]`
- all `min <= max`
- unknown keys are rejected
- PII/campaign/product/behavior/ethnicity/religion filters are forbidden
- canonical filter JSON is persisted and hashed

## Rank contract v1 (frozen)

- `AUDIENCE_RANK_CONTRACT_VERSION = "1"`
- Global order: `propensity_score DESC, person_id ASC`
- Percentile boundary rank for percentile `p`: `ceil(total_population * p / 100)`
- Percentile 1 is top 1%
- Decile: `ceil(percentile_bucket / 10)`

Rank band mapping:
- `ELITE` = percentile `1`
- `VERY_HIGH` = percentiles `2..5`
- `HIGH` = percentiles `6..10`
- `MEDIUM` = percentiles `11..25`
- `LOW` = percentiles `26..50`
- `VERY_LOW` = percentiles `51..100`

## Selection contract v1 (frozen)

- `AUDIENCE_SELECTION_CONTRACT_VERSION = "1"`

Modes:
- `ALL_MATCHING`
- `TOP_N`

Rules:
- `TOP_N` must be `>=1` and `<= prospect universe`
- selected count = `min(N, matching count)`
- order is always global score order after filters
- no manual member persistence
- no separate 5M audience-member table

## API target freeze (Phase 6)

- `GET  /api/audience/runs`
- `POST /api/audience/runs/{scoring_run_id}/prepare`
- `GET  /api/audience/runs/{scoring_run_id}/preparation-status`
- `GET  /api/audience/options?scoring_run_id=...`
- `POST /api/audience/estimate`
- `POST /api/audience/search`
- `POST /api/audience/profile`
- `POST /api/audiences`
- `GET  /api/audiences`
- `GET  /api/audiences/{audience_id}`

## Non-goals (frozen)

- no Campaign Builder
- no campaign object
- no export/contact file
- no activation
- no PII exposure
- no customer/prospect identity matching
- no model retraining
- no calibration/SHAP
- no score recomputation
