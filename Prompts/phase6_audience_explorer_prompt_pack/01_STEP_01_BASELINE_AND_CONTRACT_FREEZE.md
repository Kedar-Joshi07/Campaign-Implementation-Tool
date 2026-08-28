# Step 1 — Baseline Audit and Phase 6 Contract Freeze

Required starting HEAD:
`2d90fc1c77d7e332e789d2b0b233e8044148977d`

Do not implement Phase 6 runtime yet.

## Baseline gate

Run:
```text
git rev-parse HEAD
git status --short
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
python scripts/validate_data.py --json
```

Require the expected HEAD, no unexplained worktree changes, passing Phase 1–5 tests, and reconciliation OK.

Read and validate:
- `Prompts/phase5_prompt_pack/20_PHASE_6_HANDOFF_CONTRACT.md`
- `docs/evidence/phase1_to_phase5_final_integrity.json`
- current schema/indexes
- scoring/provenance services
- disabled Audience Explorer navigation

Record current canonical chain dynamically; never hard-code IDs.

## Create Phase 6 documentation skeleton

Create:
```text
Prompts/phase6_prompt_pack/00_README.md
Prompts/phase6_prompt_pack/01_SCOPE_AND_CONTRACTS.md
Prompts/phase6_prompt_pack/02_PROGRESS_TRACKER.md
Prompts/phase6_prompt_pack/03_ACCEPTANCE_CHECKLIST.md
Prompts/phase6_prompt_pack/04_PHASE_7_HANDOFF_CONTRACT.md
docs/PHASE_6_IMPLEMENTATION_SUMMARY.md
```

Do NOT rewrite root README.

## Freeze canonical Phase 6 input gate

Every Audience Explorer action requires a Phase 5 scoring run that passes the existing current-provenance validator:
- scoring COMPLETED;
- score count reconciled;
- model COMPLETED;
- BAGGING_PU selected;
- Model Role Policy v2;
- Evaluation Contract v2;
- Feature Contract v1 + exact SHA;
- artifact verified;
- linked historical analysis provenance current;
- customer/campaign import provenance current;
- demographic import provenance current;
- demographic count/min/max current.

Stale runs are history only and cannot drive current audience actions or saves.

## Freeze Filter Contract v1

Create `AUDIENCE_FILTER_CONTRACT_VERSION = "1"`.

Allowed numeric filters:
- score_min / score_max
- age_min / age_max
- individual_yearly_income_min / max
- family_member_count_min / max

Allowed ranking filters:
- top_percentile_max: integer 1..100
- deciles: list values 1..10
- rank_bands: ELITE/VERY_HIGH/HIGH/MEDIUM/LOW/VERY_LOW

Allowed categorical filters:
- gender
- state
- marital_status
- education
- employment_status
- resident_status
- resident_type
- type_of_employment

Rules:
- empty list means all;
- lists deduplicated and deterministically sorted;
- score range inside [0,1];
- min <= max;
- unknown keys rejected;
- no PII/campaign/product/behavior/ethnicity/religion filters;
- canonical JSON persisted and hashed.

## Freeze Rank Contract v1

Create `AUDIENCE_RANK_CONTRACT_VERSION = "1"`.

Order:
`propensity_score DESC, person_id ASC`

Boundary rank for percentile p:
`ceil(total_population * p / 100)`

Percentile 1 is top 1%. Decile is `ceil(percentile_bucket/10)`.

Bands:
ELITE=1; VERY_HIGH=2..5; HIGH=6..10; MEDIUM=11..25; LOW=26..50; VERY_LOW=51..100.

## Freeze Selection Contract v1

Create `AUDIENCE_SELECTION_CONTRACT_VERSION = "1"`.

Modes:
- ALL_MATCHING
- TOP_N

TOP_N must be >=1 and <= prospect universe; selected count = min(N, matching count). Order is always global score order after filters.

No manual member persistence and no 5M audience-member table.

## Freeze API target

```text
GET  /api/audience/runs
POST /api/audience/runs/{scoring_run_id}/prepare
GET  /api/audience/runs/{scoring_run_id}/preparation-status
GET  /api/audience/options?scoring_run_id=...
POST /api/audience/estimate
POST /api/audience/search
POST /api/audience/profile
POST /api/audiences
GET  /api/audiences
GET  /api/audiences/{audience_id}
```

## Non-goals

No Campaign Builder, campaign object, export, contact file, activation, PII, customer/prospect identity matching, model retraining, calibration, SHAP, or score recomputation.

Update progress tracker and report contracts/baseline.

STOP.
