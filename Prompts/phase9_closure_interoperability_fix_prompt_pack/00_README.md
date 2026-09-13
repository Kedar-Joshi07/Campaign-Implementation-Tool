# Phase 9 Closure & Interoperability Correction Prompt Pack

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Frozen Phase 1–8 baseline: `d6a9f9b963622a334bf3e5c3220e5d0a73e528fe`
Phase 9 baseline to correct: `6934c586780b5f8f5bd57d533b5597ea63dec8cc`

## Purpose
Close the remaining Phase 9 issues without redesigning Phase 9.

Fix only:
1. Legacy Audience Explorer reopening a Phase 9 multi-branch Target Group as only its first branch.
2. Reachable Phase 9 controls marked PASS using only unit/contract/static evidence instead of real browser interaction.
3. Stale Phase 9 summary/evidence values.
4. Missing regression protection for multi-branch interoperability.
5. Exact-SHA final CI/freeze verification.

## Non-goals
Do NOT retrain models, rescore 5M, rebuild rank boundaries, change targeting semantics, change PU/model contracts, introduce Phase 10 orchestration, or redesign the business wizard unless a genuine bug requires it.

## Step order
1. `01_STEP_01_RECONCILE_BASELINE_AND_REPRODUCE_DEFECT.md`
2. `02_STEP_02_FIX_MULTI_BRANCH_REOPEN_INTEROPERABILITY.md`
3. `03_STEP_03_ADD_INTEROPERABILITY_REGRESSION_TESTS.md`
4. `04_STEP_04_REAL_SYSTEM_BROWSER_CONTROL_RECERTIFICATION.md`
5. `05_STEP_05_CORRECT_PHASE9_DOCUMENTATION_AND_EVIDENCE.md`
6. `06_STEP_06_FULL_REGRESSION_AND_NO_HEAVY_WORK_GATE.md`
7. `07_STEP_07_EXACT_SHA_CI_AND_PHASE9_FREEZE.md`

Also included:
- Master guardrails
- Acceptance checklist
- Final report template
- Single master prompt
- Manifest
