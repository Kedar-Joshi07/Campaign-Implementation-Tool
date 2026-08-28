# Phase 6 — Audience Explorer Prompt Pack

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Authoritative Phase 6 starting SHA:

`2d90fc1c77d7e332e789d2b0b233e8044148977d`

## Phase 6 objective

Turn the canonical Phase 5 propensity-scored 5M prospect universe into an interactive, governed **Audience Explorer**.

Phase 6 enables:
- current canonical scoring-run discovery;
- deterministic score ranking;
- percentile buckets, deciles, and score-rank bands;
- approved demographic filters;
- bounded keyset-paginated prospect exploration;
- audience-size estimation;
- aggregate audience profiling;
- selected audience vs total prospect universe comparison;
- selected audience vs historical known-positive comparison;
- deterministic `ALL_MATCHING` and `TOP_N` selection;
- immutable saved audience definitions;
- Audience Explorer UI;
- clean Phase 7 handoff.

Phase 6 does NOT activate campaigns and does NOT export target files.

## Accepted Phase 5 handoff evidence

Use current repository/database evidence dynamically. The accepted pre-Phase-6 reference at the starting SHA is:
- schema version `8`;
- analysis_run_id `12`;
- training job_id `20`;
- model_run_id `8`;
- scoring job_id `21`;
- scoring_run_id `8`;
- customer_import_id `8`;
- campaign_sales_import_id `9`;
- demographic_import_id `5`;
- Feature Contract v1 SHA `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`;
- selected model `BAGGING_PU`;
- Model Role Policy v2;
- Evaluation Contract v2;
- artifact SHA `755e8f81bc1238673d17f59fb52044f44b5f00a8810fee82e694b4c4b8709d18`;
- 5,000,000 scored prospects;
- deterministic re-score verified with max abs diff `0.0`.

These IDs are acceptance evidence, never values to hard-code into runtime logic.

## Identity contract

```text
Historical customer_id -> Phase 2 analysis -> Phase 3/4 model
Prospect person_id -> Phase 5 score -> Phase 6 audience
```

Never match `customer_id` to `person_id`.

`propensity_score` remains model-specific relative look-alike affinity, not calibrated purchase probability.

## Phase 6 non-PII display contract

Audience Explorer may expose ONLY:
- person_id
- propensity_score
- percentile_bucket
- decile
- rank_band
- age
- gender
- state
- individual_yearly_income
- marital_status
- education
- employment_status
- resident_status
- resident_type
- family_member_count
- type_of_employment

Phase 6 MUST NOT expose names, addresses, street, postal code, city, phone, email, ethnicity, religion, occupation industry, family income, or child/adult household counts.

## Ranking Contract v1

Global deterministic order:
`propensity_score DESC, person_id ASC`

Percentile bucket:
- 1 = top 1%
- 100 = bottom percentile bucket

Decile:
- 1 = top 10%
- 10 = bottom 10%

Rank bands:
- ELITE = percentile 1
- VERY_HIGH = percentiles 2–5
- HIGH = percentiles 6–10
- MEDIUM = percentiles 11–25
- LOW = percentiles 26–50
- VERY_LOW = percentiles 51–100

Ties are resolved by `person_id ASC`.

## Saved audience contract

Phase 6 saves definitions, not a second 5M member table.

Selection modes:
- ALL_MATCHING
- TOP_N

A saved audience records scoring/model/analysis provenance, historical and demographic import provenance, normalized filters, ranking/selection contract versions, resolved count, and aggregate snapshot. Saved audiences are immutable; changes create a new audience.

## Execution order

1. `01_STEP_01_BASELINE_AND_CONTRACT_FREEZE.md`
2. `02_STEP_02_SCHEMA_V9_AND_AUDIENCE_PERSISTENCE.md`
3. `03_STEP_03_RANK_PREPARATION_ENGINE.md`
4. `04_STEP_04_FILTER_QUERY_AND_PAGINATION_ENGINE.md`
5. `05_STEP_05_AUDIENCE_PROFILE_AND_COMPARISON_ENGINE.md`
6. `06_STEP_06_SAVED_AUDIENCE_SERVICE_AND_APIS.md`
7. `07_STEP_07_AUDIENCE_EXPLORER_UI.md`
8. `08_STEP_08_PERFORMANCE_SECURITY_AND_PROVENANCE_HARDENING.md`
9. `09_STEP_09_REAL_5M_END_TO_END_VALIDATION.md`
10. `10_STEP_10_FINAL_ACCEPTANCE_AND_PHASE7_HANDOFF.md`

Each step ends with STOP. A single-master prompt and acceptance matrix are also included.

The comprehensive root README rewrite remains intentionally deferred until all functional phases are complete.
