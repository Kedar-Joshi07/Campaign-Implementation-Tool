# Step 5 — Audience Profile and Aggregate Comparison Engine

Use HEAD from successful Step 4. Do not implement save/UI yet.

## Objective

Add aggregate analytics for total prospect universe, matching prospects, selected audience, and historical known-positive customers linked to the model's Phase 2 analysis.

There must be NO row-level matching between prospects and historical customers.

## POST /api/audience/profile

Request scoring_run_id, filters, selection. Reuse exact filter/selection normalizers.

Population definitions:
- Universe: all current scored prospects.
- Matching: prospects satisfying filters.
- Selected: matching set for ALL_MATCHING; deterministic top N for TOP_N.
- Historical positives: distinct historical customers positive under the saved analysis linked to the model.

Use current verified historical source and saved analysis conversion/filter semantics.

## Shared comparison attributes

Only exact prospect-compatible features:
- age
- individual_yearly_income
- family_member_count
- gender
- state
- marital_status
- education
- employment_status
- resident_status
- resident_type
- type_of_employment

Historical age must use the same saved analysis reference date as Phase 3.

## Aggregate outputs

Summary counts and averages. Prospect sets may include score min/mean/max; historical positives have no prospect propensity score and must return null/N/A, never fabricated values.

Numeric bands:
Age: 18–24,25–34,35–44,45–54,55–64,65+.
Income: <50k,50k–74,999,75k–99,999,100k–149,999,150k–199,999,200k+.
Family: 1,2,3,4,5+.

Categorical distributions: category,count,share for approved fields.

Comparison selected vs universe and selected vs historical positives:
- selected_share
- reference_share
- share_point_difference
- index = selected_share/reference_share, null when reference share zero

Optionally return bounded top_overindexed_traits derived only from aggregates.

## TOP_N profiling

Do not fetch all selected IDs into Python. Prefer keyset determination of the Nth selected boundary then aggregate using the same filters plus boundary. An index-backed LIMIT CTE is acceptable only if measured and demonstrated safe.

## Historical reuse

Reuse Phase2/3 cohort logic where semantically correct. Never expose historical customer IDs or use campaign behavior as prospect filters.

## Tests

ALL_MATCHING/TOP_N counts, universe profile, historical count reconciliation, age reference, no identity linkage, no IDs/PII in aggregate payload, share sums, comparison math, zero reference handling, finite JSON, stale historical/demographic rejection, bounded TOP_N memory, regressions.

STOP.
