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
- [x] No unbounded hot-path materialization retained in validation flow
- [x] `python -m pip check` passed
- [x] `python -m pytest -q` passed (`413 passed in 457.37s`)
- [x] `python -m compileall -q app scripts tests` passed
- [x] `git diff --check` passed for blocking issues (CRLF warnings only)
- [x] `python scripts/validate_data.py --json` passed (`overall_status=OK`)

## Deliverables Updated in Step 10

- [x] `docs/PHASE_6_IMPLEMENTATION_SUMMARY.md`
- [x] `docs/evidence/phase6_5m_acceptance.json`
- [x] `Prompts/phase6_prompt_pack/02_PROGRESS_TRACKER.md`
- [x] `Prompts/phase6_prompt_pack/03_ACCEPTANCE_CHECKLIST.md`
- [x] `Prompts/phase6_prompt_pack/04_PHASE_7_HANDOFF_CONTRACT.md`

## Final Decision

Final Phase 6 decision: GO

