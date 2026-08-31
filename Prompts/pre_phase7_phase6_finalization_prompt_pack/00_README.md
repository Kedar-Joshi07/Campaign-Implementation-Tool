# Pre-Phase-7 Phase 6 Finalization Prompt Pack

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Required starting HEAD:

`b2cdfa95713aa2f8d9309be4881079f703df1831`

## Purpose

Phase 6 is functionally complete, but this finalization pass must close the remaining contract/evidence/repository issues before Phase 7.

Fix only:

1. TOP_N runtime behavior contradicting Selection Contract v1.
2. Preparation readiness/currentness semantics.
3. Missing real Phase 6 rank-preparation metrics.
4. Missing real 5M search/profile timing evidence.
5. Committed synthetic SQLite performance DB.
6. Incomplete PII blocked-field metadata.
7. Final regression/evidence refresh on the actual final SHA.

## Do NOT

- regenerate customer data;
- regenerate campaign data;
- regenerate demographics;
- retrain model 8;
- rerun Phase 5 5M scoring;
- change Feature Contract v1;
- change BAGGING_PU governance;
- create a 5M rank table;
- create an audience-members table;
- implement Campaign Builder;
- implement export;
- implement activation.

## Recommended order

1. `01_STEP_01_BASELINE_AND_FINALIZATION_AUDIT.md`
2. `02_STEP_02_TOP_N_SELECTION_CONTRACT_FIX.md`
3. `03_STEP_03_PREPARATION_CURRENTNESS_AND_READINESS.md`
4. `04_STEP_04_RANK_PREPARATION_METRICS.md`
5. `05_STEP_05_REAL_5M_PERFORMANCE_EVIDENCE.md`
6. `06_STEP_06_REPOSITORY_AND_PII_METADATA_CLEANUP.md`
7. `07_STEP_07_FINAL_REGRESSION_AND_PHASE7_FREEZE.md`

Use the master prompt only if the coding agent reliably obeys STOP gates.

Do not begin Phase 7 in this pack.
