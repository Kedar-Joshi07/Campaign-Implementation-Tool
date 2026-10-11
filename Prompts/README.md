# Prompt Packs Guide

This folder preserves implementation prompt packs and freeze workflows used across Phase 1 to Phase 7.

## Current 14B execution authority

The approved [product-buyer-similarity 14B pack](Campaign_Implementation_Tool_14B_Lookalike_Prompt_Pack/00_README_START_HERE.md)
adds explicit descriptive v3 while retaining historical v1/v2 purchase
probability. Its [Prompt 18](Campaign_Implementation_Tool_14B_Lookalike_Prompt_Pack/18_DOCUMENTATION_ARCHITECTURE_AND_CLIENT_EXPLANATION.md)
documents the completed local Prompt 16 full-5M and Prompt 17 unchanged
20-scenario demo evidence. [Architecture](../docs/BUYER_SIMILARITY_ARCHITECTURE.md),
[operator/demo guide](../docs/BUYER_SIMILARITY_OPERATOR_AND_DEMO.md), and
[current evidence](../docs/evidence/lookalike_v3/README.md) are the reading
path. Prompt 19 exact-SHA remote CI/release certification is separate and
has not been claimed by Prompt 18.

The older conditional 14B alternative was superseded by the dated approved
v3 decision; historical prompt/evidence files and v1/v2 semantics remain
available for audit rather than being rewritten.

## Current authoritative pack

- phase1_to_phase7_repo_freeze_prompt_pack/
  - Repository-freeze workflows for housekeeping, documentation freeze, and final hardening.

## Completed historical implementation packs

- phase1_prompt_pack/
- phase2_prompt_pack/
- phase3_prompt_pack/
- phase4_prompt_pack/
- phase5_prompt_pack/
- phase6_prompt_pack/
- phase6_audience_explorer_prompt_pack/
- phase6_final_analytics_optimization_prompt_pack/
- phase6_performance_finalization_focused_pass/
- phase7_two_section_prompt_pack/
- phase7_final_ui_and_hardening_prompt_pack/

These were executed during their respective implementation windows and are retained as historical process records.

## Superseded or pre-freeze packs

- pre_phase6_phase1_to_phase5_integrity_prompt_pack/
- pre_phase6_phase5_finalization_prompt_pack/
- pre_phase6_phase5_final_corrections_prompt_pack/
- pre_phase7_phase6_finalization_prompt_pack/
- FINAL_PRE-PHASE-6_REPOSITORY_FREEZE_&_REPRODUCIBILITY_CORRECTION.md

## Do-not-run guidance

Do not rerun historical or pre-freeze packs on the canonical repository unless you are intentionally reproducing a specific historical checkpoint for audit comparison.

For current repository-freeze tasks, use phase1_to_phase7_repo_freeze_prompt_pack.
