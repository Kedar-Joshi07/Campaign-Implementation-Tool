# Step 4 — Final Acceptance, Documentation, and Phase 6 Baseline Freeze

Use the HEAD after successful Step 3. Do not implement Phase 6.

## Documentation
Update docs/PHASE_5_IMPLEMENTATION_SUMMARY.md with:
- original failed scoring due age contract;
- first post-hoc remediation issue;
- final adult-from-source regeneration;
- provenance hardening;
- final real 5M rerun evidence.

Preserve historical evidence.

Update Prompts/phase5_prompt_pack/19_PHASE_5_ACCEPTANCE_CHECKLIST.md:
- remove stale SHA/worktree wording;
- record coherent adult source;
- provenance recorded;
- exact 5M completed;
- deterministic re-score;
- no Critical failures.

Update Prompts/phase5_prompt_pack/10_PROGRESS_TRACKER.md with a Pre-Phase-6 Phase 5 Finalization section including starting implementation SHA 0d1425da0bacd020decb79b5d2d7b201b0c894e0, dataset regeneration, import ID/checksum, model/job/scoring IDs, reconciliation, score stats, runtime, throughput, direct re-score, and tests.

Update Prompts/phase5_prompt_pack/20_PHASE_6_HANDOFF_CONTRACT.md with:
- canonical model_run_id
- canonical scoring_run_id
- demographic_import_id
- demographic_source_checksum
- 5M scored count
- feature contract version/hash
- artifact SHA

Phase 6 must reject a score set whose demographic source provenance no longer matches the loaded source.

## Scope
Confirm absent:
Audience Explorer
individual prospect API
person lookup
score bands/percentiles/deciles
audience selection/persistence
campaign builder
export
activation

Audience Explorer remains disabled.

## Final validation
Run:
git status --short
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
python scripts/validate_data.py --json

Verify canonical completed scoring run one final time.

## Commit
Create a dedicated finalization commit such as:
Phase 5 finalization before Phase 6

If a final documentation-only SHA update is needed, that extra commit is acceptable.

The actual final repository HEAD after all corrective/doc commits becomes the authoritative Phase 5 baseline for Phase 6. Do not leave the handoff pointing to an intermediate SHA.

## Final report
Include:
1 original Phase 5 SHA 0d1425da0bacd020decb79b5d2d7b201b0c894e0
2 final Phase 5 SHA
3 commits created
4 files changed
5 root cause
6 final adult-generation correction
7 demographic_import_id
8 demographic_source_checksum
9 demographic row count
10 age min/max
11 invalid age/child-state counts
12 model_run_id
13 scoring job_id
14 scoring_run_id
15 exact 5M reconciliation
16 score min/mean/max
17 runtime
18 rows/sec
19 chunk size/count
20 direct re-score max_abs_diff
21 provenance verification
22 restart/concurrency evidence
23 full pytest
24 pip check
25 compileall
26 data validation
27 no Phase 6 functionality
28 authoritative Phase 5 SHA for Phase 6
29 GO / CONDITIONAL GO / NO-GO Phase 6

STOP.
