# Step 1 — Adult Demographic Regeneration

Repository: https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git
Required starting SHA: 0d1425da0bacd020decb79b5d2d7b201b0c894e0

Phase 5 architecture is already accepted. Do not redesign scoring, training, APIs, jobs, UI, or the feature contract. Do not begin Phase 6.

## Baseline
Run:
git rev-parse HEAD
git status --short
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
python scripts/validate_data.py --json

HEAD must be 0d1425da0bacd020decb79b5d2d7b201b0c894e0 unless an explicitly approved later documentation-only continuation exists.

## Problem
The original 5M generator created minors, while the frozen scoring feature contract requires age 18..100. The prior remediation rewrote invalid ages after age-dependent fields such as education, marital status, employment status, family composition, employment type, industry, and income had already been generated. This can create semantically inconsistent adult rows.

## Required correction
Inspect data_generation_scripts/generate_us_demographic_synthetic.py.

Generate an adult prospect population from the start:
- remove/zero age bins 0–4 and 5–17;
- renormalize remaining state-specific adult age weights;
- sample age 18..100 first;
- generate education, marital status, household composition, employment, type of employment, industry, income, and remaining attributes from that adult age.

Do not mutate age after dependent fields exist.

Replace post-hoc enforce_age_contract-style mutation with a validation-only assertion that fails if any age is outside 18..100.

## Required coherence checks
Verify:
- age <18 = 0
- age >100 = 0
- employment_status == "Minor / not in labor force" = 0
- education == "Not yet in school" = 0
- education == "Primary/Middle school" = 0
- family_member_count >=1
- number_of_adults_in_family >=1
- number_of_children_in_family >=0
- individual_yearly_income >=0

Do not overconstrain valid adults.

## Reproducibility
Keep seeded deterministic generation.
Summary should record:
population_age_contract = ADULT_18_100
age_contract_adjusted_rows = 0
age_contract_mode = GENERATED_VALID_FROM_SOURCE

## Validation
First generate a bounded ~20,000-row sample and validate all adult constraints.
Then regenerate data/usa_demographic_synthetic_5000000_rows.csv.gz from scratch.

Full source requirements:
- exactly 5,000,000 rows
- exactly 5,000,000 unique person_id
- min age >=18
- max age <=100

Do not change app/ml/feature_contract.py.
Feature version remains 1 and SHA remains a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535.

Run:
python -m pytest -q
python -m compileall -q app scripts tests
python -m pip check
git diff --check

Do NOT run the real 5M scoring yet.

Report starting SHA, files changed, old root cause, new generation strategy, sample/full counts, age min/max, invalid counts, seed, tests, and unresolved issues.

STOP.
