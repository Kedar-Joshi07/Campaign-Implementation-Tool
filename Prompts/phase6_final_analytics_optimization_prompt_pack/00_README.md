# Phase 6 Final Analytics Optimization & Hardening Prompt Pack

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Required starting HEAD: `80c3324f884f448b1eb84e61fafcd1c70415b8b1`

## Purpose

This is the **final Phase 6 engineering pass before Phase 7**. Phase 6 functionality/currentness is accepted, but real 5M service benchmarking exposed major analytics latency: options ~82.52 sec, estimate-all ~48.46 sec, top-1% profile ~460.22 sec, filtered TOP_N 50K profile ~971.87 sec. The previous focused pass already reduced saved-audience currentness from ~509 sec to ~0.94 sec. **Do not undo that architecture.**

## Execute strictly in this order

1. `01_STEP_01_FREEZE_AND_BASELINE_AUDIT.md`
2. `02_STEP_02_SCHEMA_V10_ANALYTICS_SNAPSHOT.md`
3. `03_STEP_03_ANALYTICS_PREPARATION_AND_BACKFILL.md`
4. `04_STEP_04_OPTIONS_AND_FILTER_SEMANTICS.md`
5. `05_STEP_05_ESTIMATE_OPTIMIZATION.md`
6. `06_STEP_06_PROFILE_OPTIMIZATION.md`
7. `07_STEP_07_SAVE_AUDIENCE_AND_FRONTEND_ASYNC.md`
8. `08_STEP_08_INTERACTIVE_CURRENTNESS_AND_SCORING_READS.md`
9. `09_STEP_09_TESTS_SECURITY_AND_FINE_COMB.md`
10. `10_STEP_10_REAL_5M_BENCHMARK_AND_ACCEPTANCE.md`
11. `11_STEP_11_FINAL_PHASE6_FREEZE_AND_PHASE7_HANDOFF.md`

Use `12_SINGLE_MASTER_PROMPT.md` only if the agent reliably obeys STOP gates. Use `13_ACCEPTANCE_CHECKLIST.md` and `14_PROGRESS_TRACKER.md` for final control.

## Frozen contracts

Do not change Feature Contract v1, Feature SHA `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`, Model Role Policy v2, Evaluation Contract v2, `BAGGING_PU`, exact 11 scoring features, ranking `propensity_score DESC, person_id ASC`, Filter/Rank/Selection Contract v1, `customer_id`/`person_id` separation, shared single-worker heavy compute, exact 5M score semantics, or saved-audience immutability.

## Non-goals

Do not regenerate source data, retrain, rerun 5M scoring, create 5M rank/member tables, expose PII, implement Campaign Builder/export/activation, add SHAP/calibration, or perform the comprehensive root README rewrite.

## Final GO rule

GO only if quality and authenticity are preserved (no semantic drift, no sampling/approximation, no provenance or contract regressions), and performance remains operationally acceptable under the final policy: profile top-1% <=60 sec threshold, filtered TOP_N 50K profile <=60 sec threshold, save-with-profile <=60 sec threshold, and 120-180 sec considered acceptable for heavy bounded flows when data/process quality is unchanged. Keep options/estimate/search/currentness/scoring reads responsive for interactive use, pass semantic/provenance/security tests, and do not introduce Phase 7 functionality.
