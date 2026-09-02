# Single Master Prompt — Final Phase 6 Analytics Optimization Before Phase 7

Start from exactly `80c3324f884f448b1eb84e61fafcd1c70415b8b1` and execute Steps 1–11 in strict order with every STOP gate.

Core work: baseline/fine-comb audit; additive schema v10 aggregate snapshot; preparation/backfill/currentness; snapshot-backed options + Unknown/Other/vocabulary fix; exact estimate fast paths; profile static-vs-dynamic redesign; save/frontend async optimization; remove deep scans from ordinary reads and harden lightweight governance; regression/security/scope cleanup; real 5M benchmark/deep acceptance; final Phase 6 freeze.

Frozen: Feature v1/SHA `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`, Role Policy v2, Evaluation v2, BAGGING_PU, exact 11 features, deterministic ranking, Filter/Rank/Selection v1, identity separation. No data regeneration, retraining, 5M rescoring, Phase7 implementation, or comprehensive root README rewrite.

Required final performance policy: options <2s, estimate-all <1s, rank-only <2s, search typical <2s, no-filter profile <2s, top1 profile <=60s, filtered TOP_N 50K <=60s, save-with-profile <=60s, saved currentness <5s, scoring status/detail <5s. Heavy bounded flows in 120-180s are acceptable only when authenticity, data quality, process quality, and output usefulness are unchanged.

Quality-first rule: never accept a speedup that weakens semantic correctness, provenance, contract compliance, or interpretability.

If a step fails, fix/retest before continuing.
