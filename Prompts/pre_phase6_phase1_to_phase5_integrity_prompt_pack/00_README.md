# Final Phase 1–5 Integrity Pass Before Phase 6

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Required starting HEAD:

`5f54c5e7138afaf615984babd32cac3a6bf2a99b`

## Purpose

Perform one final cross-phase integrity pass before any Phase 6 implementation.

This pack fixes only Phase 1–5 alignment issues discovered during the full repository audit:

1. eliminate crash/partial-publication gaps between authoritative live imports and import-provenance completion for customers, campaign sales, and demographics;
2. guarantee historical campaigns never target a customer before age 18;
3. bind Phase 2 analyses and Phase 3 training to the exact historical customer/campaign source imports;
4. prevent a stale historical model/score chain from being treated as current after historical source replacement;
5. align demographic import validation with the frozen adult Phase 5 scoring universe;
6. refresh stale current-state documentation and schema/index naming;
7. decide data regeneration using measured evidence and, when required, rebuild derived Phase 2–5 state cleanly.

## Frozen contracts

Do NOT change:

- Customer ↔ prospect identity separation.
- `customer_id` never maps to `person_id`.
- Phase 2 Positive / Unlabeled semantics.
- Feature Contract v1.
- Feature SHA `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`.
- Exact 11 model/scoring features.
- Model Role Policy v2.
- Evaluation Contract v2.
- `BAGGING_PU` as governed PRIMARY.
- Shared `ProcessPoolExecutor(max_workers=1)`.
- Keyset 5M scoring.
- Relative look-alike propensity score semantics.

Do NOT implement Phase 6:
- no Audience Explorer;
- no score bands/percentiles/deciles;
- no audience selection;
- no Campaign Builder;
- no export or activation.

## Recommended order

1. `01_STEP_01_DYNAMIC_BASELINE_AND_CROSS_PHASE_AUDIT.md`
2. `02_STEP_02_ATOMIC_LIVE_SWAP_AND_IMPORT_PROVENANCE.md`
3. `03_STEP_03_ADULT_HISTORICAL_CAMPAIGN_ELIGIBILITY.md`
4. `04_STEP_04_HISTORICAL_SOURCE_PROVENANCE_CHAIN.md`
5. `05_STEP_05_DEMOGRAPHIC_IMPORT_CONTRACT_ALIGNMENT.md`
6. `06_STEP_06_CURRENT_STATE_DOCS_AND_SCHEMA_CLEANUP.md`
7. `07_STEP_07_DATA_REGENERATION_AND_END_TO_END_REBUILD.md`
8. `08_STEP_08_FINAL_PHASE1_TO_PHASE5_ACCEPTANCE_FREEZE.md`

Each step has a STOP gate.

Use `09_SINGLE_MASTER_INTEGRITY_PROMPT.md` only if the coding agent reliably obeys stop gates.

## Important data rule

Do NOT regenerate all three datasets automatically.

Step 1 must measure the existing historical under-age-contact count first.

Expected decisions:

- Demographics: no regeneration unless the committed adult 5M source itself fails validation.
- Customer master: no regeneration required for the identified issue.
- Campaign sales: regenerate only if current data contains under-18 historical contacts or if a deterministic regeneration is explicitly chosen to establish the new generator contract.

Any campaign-sales regeneration invalidates the current Phase 2→5 derived chain as the current chain. Preserve old runs as history and create new analysis/model/scoring runs.
