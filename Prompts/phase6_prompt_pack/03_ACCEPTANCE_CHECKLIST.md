# Phase 6 Acceptance Checklist

All critical checks must pass for final Phase 6 GO.

## Baseline and Governance

- [x] **Critical** required starting HEAD matched `2d90fc1c77d7e332e789d2b0b233e8044148977d`
- [x] Current Phase 5 scoring run verified as canonical for current sources
- [x] Historical source provenance verified current
- [x] Demographic source provenance verified current
- [x] BAGGING_PU selected-candidate chain preserved
- [x] Feature contract/evaluation/artifact provenance unchanged

## Ranking Contract

- [x] Rank contract version is `1`
- [x] Ordering contract is `propensity_score DESC, person_id ASC`
- [x] Exactly 100 boundary rows persisted
- [x] Percentile 1 rank equals 50,000 for 5,000,000 universe
- [x] Percentile 10 rank equals 500,000 for 5,000,000 universe
- [x] Bands exactly reconcile:
	- [x] ELITE 50,000
	- [x] VERY_HIGH 200,000
	- [x] HIGH 250,000
	- [x] MEDIUM 750,000
	- [x] LOW 1,250,000
	- [x] VERY_LOW 2,500,000
- [x] Band total equals 5,000,000
- [x] No dedicated 5M rank/member persistence table introduced
- [x] Rank scan hot path uses no OFFSET

## Search and Filters

- [x] Approved filter allowlist enforced (numeric/rank/categorical only)
- [x] Search SQL is parameterized
- [x] Keyset pagination enforced with `page_size <= 100`
- [x] Row payload remains exact non-PII allowlist
- [x] Stale/non-canonical scoring runs are rejected

## Profile

- [x] Universe/matching/selected/historical-positive aggregate semantics validated
- [x] Selected vs universe index comparisons validated
- [x] Selected vs historical positives comparisons validated
- [x] No identity linkage fields exposed
- [x] Finite JSON and finite comparison metrics validated

## Saved Audiences

- [x] Supports `ALL_MATCHING` and `TOP_N`
- [x] Immutable definition persistence validated
- [x] Normalized filters/selection persisted and reopened exactly
- [x] Full provenance fields persisted on saved audience
- [x] No member-level copy table introduced
- [x] Currentness/staleness detection validated

## UI and Scope Boundaries

- [x] Audience Explorer enabled and functional
- [x] Campaigns remains disabled in Phase 6
- [x] Prepare/filter/search/profile/save/reopen surfaces present
- [x] Score semantics/disclaimer present
- [x] No export surface
- [x] No activation surface
- [x] No contact-PII exposure

## Performance and Regression

- [x] Bounded rank preparation behavior validated
- [x] Query plan/timing evidence captured
- [x] Real 5M performance evidence captured in `docs/evidence/phase6_real_5m_performance.json`
- [x] Synthetic Step 8 evidence remains explicitly labeled synthetic
- [x] No unbounded hot-path materialization retained in validation flow
- [x] `python -m pip check` passed
- [x] `python -m pytest -q` passed (`435 passed in 602.43s`)
- [x] `python -m compileall -q app scripts tests` passed
- [x] `git diff --check` passed for blocking issues (CRLF warnings only)
- [x] `python scripts/validate_data.py --json` passed (`overall_status=OK`)

## Focused Performance Finalization

- [x] **Critical** focused-pass starting HEAD matched `77398d91f126d47d021e7835581848d655701b3a`
- [x] Interactive currentness explicitly split from deep 5M integrity validation
- [x] Lightweight helper introduced: `resolve_current_scoring_context_lightweight`
- [x] Lightweight canonical resolver introduced: `find_current_canonical_run_for_model_lightweight`
- [x] Deep integrity helper retained: `validate_completed_scoring_run_integrity_deep`
- [x] Interactive callers migrated to lightweight currentness validation
- [x] Duplicate deep-validation path removed from interactive flow
- [x] Deep validation retained for scoring completion/preparation/audit boundaries
- [x] Real service timings captured in `docs/evidence/phase6_real_5m_service_performance.json`
- [x] Baseline blocker captured in `docs/evidence/phase6_performance_finalization_baseline.json`
- [x] Saved audience currentness timing improved from `509.16243s` to `0.94332s`
- [x] Saved audience currentness target met (`< 5s` and preferred `< 1s`)
- [x] Saved audience list target met (`0.916491s`)
- [x] Saved audience detail target met (`0.880576s`)
- [x] Preparation status/list no longer rely on deep 5M score scans in interactive path
- [x] No schema migration required for focused pass
- [x] No Phase 7 runtime implementation added

## Pre-Phase-7 Finalization Closure

- [x] Dynamic `TOP_N` universe-bound contract fix verified (`1 <= target_count <= scored_person_count`)
- [x] Preparation readiness semantics include `ready_for_current_audience_actions`
- [x] Audience preparation metrics persistence includes bounded scan/runtime fields
- [x] Generated SQLite performance artifact DB is not tracked in git
- [x] Runtime PII blocked-field metadata aligned to frozen deny-list

## Deliverables Updated in Step 10

- [x] `docs/PHASE_6_IMPLEMENTATION_SUMMARY.md`
- [x] `docs/evidence/phase6_5m_acceptance.json`
- [x] `docs/evidence/phase6_real_5m_performance.json`
- [x] `Prompts/phase6_prompt_pack/02_PROGRESS_TRACKER.md`
- [x] `Prompts/phase6_prompt_pack/03_ACCEPTANCE_CHECKLIST.md`
- [x] `Prompts/phase6_prompt_pack/04_PHASE_7_HANDOFF_CONTRACT.md`

## Deliverables Updated in Focused Pass

- [x] `docs/evidence/phase6_performance_finalization_baseline.json`
- [x] `docs/evidence/phase6_real_5m_service_performance.json`
- [x] `docs/PHASE_6_IMPLEMENTATION_SUMMARY.md`
- [x] `Prompts/phase6_prompt_pack/02_PROGRESS_TRACKER.md`
- [x] `Prompts/phase6_prompt_pack/03_ACCEPTANCE_CHECKLIST.md`
- [x] `Prompts/phase6_prompt_pack/04_PHASE_7_HANDOFF_CONTRACT.md`

## Final Decision

Final Phase 6 decision: GO

