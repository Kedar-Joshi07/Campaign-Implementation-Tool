# Pre-Phase-6 Phase 5 Final Corrections Prompt Pack

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Required starting HEAD: `eeed03d052cc75987cc8926b088d906ae0fb7ccc`

Context:
- Original Phase 5 implementation: `0d1425da0bacd020decb79b5d2d7b201b0c894e0`
- Substantive Pre-Phase-6 finalization: `28aa03952e92d74dbe9e4fe0cf0ba0ed87764035`
- Current completion/stamp HEAD: `eeed03d052cc75987cc8926b088d906ae0fb7ccc`

## Purpose

Fix the remaining Phase 5 lifecycle/provenance defects BEFORE Phase 6. This pack does not implement Audience Explorer or any Phase 6 feature.

## Remaining issues

1. Demographic replacement is not failure-atomic.
2. Existing completed scoring runs are checked without matching the currently loaded demographic source.
3. The database currently permits only one COMPLETED score run per model forever.
4. Scoring APIs can report a stale score set as source-verified.
5. Regression coverage does not prove mid-import rollback or same-model rescoring after a source change.

## Recommended order

1. `01_STEP_01_ATOMIC_DEMOGRAPHIC_REPLACEMENT.md`
2. `02_STEP_02_SCORING_CANONICAL_LIFECYCLE.md`
3. `03_STEP_03_API_CURRENT_SOURCE_SEMANTICS.md`
4. `04_STEP_04_REGRESSION_AND_REAL_VALIDATION.md`
5. `05_STEP_05_FINAL_ACCEPTANCE_AND_BASELINE_FREEZE.md`

Use `06_SINGLE_MASTER_CORRECTION_PROMPT.md` only if the coding agent reliably obeys staged stop gates.

## Frozen boundaries

Do NOT redesign PU training, Bagging PU, model-role policy, evaluation contract, the 11-feature contract, artifact loading, chunked/keyset scoring, ProcessPoolExecutor(max_workers=1), one-active-heavy-job policy, or score semantics.

Feature contract remains version `1`, SHA `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`.

Do NOT implement Audience Explorer, score bands/percentiles/deciles, audience selection, campaign builder, export, or activation.
