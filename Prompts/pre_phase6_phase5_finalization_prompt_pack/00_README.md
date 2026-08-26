# Pre-Phase-6 / Phase 5 Finalization Prompt Pack

Repository: https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git
Starting Phase 5 SHA: 0d1425da0bacd020decb79b5d2d7b201b0c894e0

Purpose: finalize Phase 5 without redesigning the accepted scoring architecture.

Execution order:
1. 01_STEP_01_ADULT_DEMOGRAPHIC_REGENERATION.md
2. 02_STEP_02_SCORING_SOURCE_PROVENANCE.md
3. 03_STEP_03_REIMPORT_AND_FULL_5M_RERUN.md
4. 04_STEP_04_FINAL_ACCEPTANCE_AND_PHASE6_FREEZE.md

Use 05_SINGLE_MASTER_FINALIZATION_PROMPT.md only if the coding agent reliably obeys staged stop points.

Frozen:
- PRIMARY = BAGGING_PU
- model role policy = 2
- evaluation contract = 2
- feature contract = 1
- feature SHA = a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535
- exact 11 scoring features unchanged
- no Audience Explorer, audience selection, campaign builder, export, or activation in this pass.
