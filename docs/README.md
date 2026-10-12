# Documentation Index

This folder contains implementation summaries and evidence indexes for the Phase 1 to Phase 11 delivery history.

## Current implementation summaries

- PHASE_1_IMPLEMENTATION_SUMMARY.md
- PHASE_2_IMPLEMENTATION_SUMMARY.md
- PHASE_3_IMPLEMENTATION_SUMMARY.md
- PHASE_4_IMPLEMENTATION_SUMMARY.md
- PHASE_5_IMPLEMENTATION_SUMMARY.md
- PHASE_6_IMPLEMENTATION_SUMMARY.md
- PHASE_7_IMPLEMENTATION_SUMMARY.md
- PHASE_8_IMPLEMENTATION_SUMMARY.md
- PHASE_9_IMPLEMENTATION_SUMMARY.md
- PHASE_10_IMPLEMENTATION_SUMMARY.md
- PHASE_11_IMPLEMENTATION_SUMMARY.md
- PHASE_11_API_AND_SCHEMA.md
- PHASE_11_OMNICHANNEL_PROFILES.md
- PHASE_11_RESULT_SNAPSHOTS_AND_SMART_REUSE.md
- PHASE_11_BUSINESS_UI.md
- PHASE_11_FUTURE_FEEDBACK_LINEAGE.md
- BUYER_SIMILARITY_ARCHITECTURE.md
  - Current schema-33 v3/v2 boundaries, scoring and selection meaning,
    dependency/invalidation matrix, immutable results, and SQLite limits.
- BUYER_SIMILARITY_OPERATOR_AND_DEMO.md
  - Operator preparation, currentness/retry/export/feedback guidance,
    OpenAPI example, monitoring and measured client demonstration.

## Current authoritative references

- ../README.md
  - Master Phase 1 to 7 architecture, workflow, contracts, setup, and operations.
- evidence/README.md
  - Evidence artifact classification with supersession mapping.
- evidence/DOCUMENTATION_FREEZE_REPORT.md
  - Documentation freeze audit, validation gates, and final status.
- evidence/phase8/PHASE8_FINAL_ACCEPTANCE.md
  - Final Phase 8 system-browser, local-regression, CI, and repository-freeze decision.
- evidence/phase8/12_MASTER_ACCEPTANCE_CHECKLIST_RUN.md
  - Completed 28-item Phase 8 acceptance checklist with evidence references.
- evidence/phase9/README.md
  - Historical original Phase 9 evidence index and authority classification.
- evidence/phase9_closure/README.md
  - Current Phase 9 closure/interoperability evidence index and reading order.
- evidence/phase9_closure/PHASE9_CLOSURE_ACCEPTANCE.md
  - Current Phase 9 closure acceptance and final GO status.
- evidence/phase9_closure/06_REGRESSION_REPORT.md
  - Step 6 full regression, compatibility, repository/LFS, and no-heavy-work evidence.
- evidence/phase9_closure/PHASE9_FINAL_FREEZE_REPORT.md
  - Final closure SHA chain, exact-SHA CI results, Phase 10 readiness, and Phase 9 freeze decision.
- evidence/phase9/PHASE9_FINAL_ACCEPTANCE.md
  - Historical original Phase 9 business workflow, regression, CI, and freeze decision.
- evidence/phase9/final_system_browser/PHASE9_SYSTEM_BROWSER_CERTIFICATION_REPORT.md
  - Installed-Chrome certification for the business Campaign Planner and required alternate states.
- evidence/phase10/README.md
  - Phase 10 evidence authority, implementation reading order, and final certification references.
- evidence/phase10/PHASE10_FINAL_ACCEPTANCE.md
  - Final local, browser, full-5M, bounded-CI, lineage, and compatibility acceptance.
- evidence/phase10/PHASE10_FINAL_FREEZE_REPORT.md
  - Exact implementation/documentation SHA chain, exact-SHA GitHub Actions results, and Phase 10 freeze decision.
- evidence/phase11/README.md
  - Phase 11 evidence authority, reading order, and final certification references.
- evidence/phase11/PHASE11_FINAL_ACCEPTANCE.md
  - Historical business workflow acceptance, superseded by the runtime-closure baseline.
- evidence/phase11/PHASE11_FINAL_FREEZE_REPORT.md
  - Historical Phase 11 freeze, retained for lineage.
- evidence/phase11_runtime_closure/PHASE11_RUNTIME_FINAL_ACCEPTANCE.md
  - Current runtime, recovery, browser, full-5M, regression, and exact-SHA acceptance.
- evidence/phase11_runtime_closure/PHASE11_RUNTIME_FINAL_FREEZE_REPORT.md
  - Corrected trusted SHA chain, exact-SHA GitHub Actions results, and final freeze decision.
- evidence/recovery_hardening/13_6_1_LEGACY_MAPPING_CLOSURE.md
  - Latest pre-14 authority: frozen legacy-selection mapping closure, canonical
    scenario proof, regression results, governance status, and exact-SHA CI.
- evidence/recovery_hardening/13_6_1_LEGACY_MAPPING_CLOSURE.json
  - Machine-readable Prompt 13.6.1 defect, mapping, scenario, test, and CI evidence.
- evidence/recovery_hardening/13_6_PRE14_STABILIZATION.md
  - Historical Prompt 13.6 stabilization evidence, superseded as the latest
    pre-14 authority by Prompt 13.6.1 while retained for audit lineage.
- evidence/recovery_hardening/13_6_PRE14_STABILIZATION.json
  - Machine-readable Prompt 13.6 findings, contract changes, test results,
    migration proof, CI state, and retained limitations.
- evidence/lookalike_v3/00_BASELINE.md
  - Stage 14B approved product-buyer-similarity baseline, frozen legacy
    compatibility contract, source inventory, and implementation gap map.
- evidence/lookalike_v3/01_CONTRACT_MIGRATION.md
  - Stage 14B_01 schema-32 migration, explicit v3 API/registry contract,
    preserved v1/v2 behavior, migration proofs, and disclosed certification
    boundary.
- evidence/lookalike_v3/01_FROZEN_INTERFACE.json
  - Machine-readable v3 interface consumed by the later implementation and
    optional C2/C3/C4 lanes; no later lane owns a separate schema allocation.
- evidence/lookalike_v3/02_BUYER_COHORTS.md
  - Stage 14B_02 exact product-buyer cohort, source alignment, deterministic
    union split, canonical support, and generator-reporting correction evidence.
- evidence/lookalike_v3/02_PRODUCT_SUPPORT_MANIFEST.json
  - Count-only canonical 48-product support manifest with no customer IDs or
    contact data.
- evidence/lookalike_v3/03_PROFILE_METHOD.md
  - Stage 14B_03 deterministic mixed-type learned buyer profiles, exact
    distance mathematics, safe JSON artifact contract, bounded canonical
    profile proof, and explicit descriptive-versus-predictive boundary.
- evidence/lookalike_v3/04_SCORING_ATTESTATION.md
  - Stage 14B_04 bounded, resumable and fenced prospect similarity scoring,
    deep generation attestation, atomic publication, deterministic composite
    winners, resource estimation, and current fast-reuse proof.
- evidence/lookalike_v3/04_SCORING_ATTESTATION.json
  - Machine-readable Stage 14B_04 implementation, tests, bounded canonical
    audit, schema/data impact, limitations, and sequential handoff.
- evidence/lookalike_v3/05_PREFLIGHT_SEARCH.md
  - Exact v3 preflight, search, cache isolation, and probability-independent
    readiness on bounded fixtures.
- evidence/lookalike_v3/06_UI.md
  - Explicit Buyer Similarity form mode, advanced probability mode, and browser
    evidence with score semantics kept separate.
- evidence/lookalike_v3/07_MEMBERSHIP_EXPORT_FEEDBACK.md
  - Immutable similarity membership, channel export audit, and feedback lineage.
- evidence/lookalike_v3/08_MODEL_DATA_ASSURANCE.md
  - Bounded descriptive assurance and the explicit predictive-quality no-go.
- evidence/lookalike_v3/09_INTEGRATION_CLOSURE.md
  - Current schema-33 integration, preserved legacy API behavior, full bounded
    regression, browser, cleanroom, and separate readiness decisions.
- evidence/lookalike_v3/15_1_SUPPORT_AWARE_SPLIT_RECOVERY.md
  - Current customer-disjoint descriptive split policy; supersedes earlier
    union-hash support conclusion without rewriting old artifacts.
- evidence/lookalike_v3/16_2_FULL5M_MEASUREMENTS.md
  - Current isolated full-5M scale and resource authority for the named source
    and hardware; earlier Prompt 16 measurements remain historical.
- evidence/lookalike_v3/17_SCENARIOS.md
  - Current unchanged 20-scenario exact preflight, real-run parity,
    system-browser screenshots and governed representative export.
- evidence/lookalike_v3/08_MODEL_FACTSHEET.md
  - Current descriptive meaning and predictive-validation limitations.
- evidence/lookalike_v3/18_DOCUMENTATION.md
  - Prompt 18 documentation reconciliation and client-claim gate.

## Historical phase records

Earlier phase summaries remain valuable as implementation chronology and acceptance context. They should be read as historical records where they describe pre-Phase-7 boundaries.

## Usage guidance

- For current operations and contracts, start at the root README.
- For change history and design rationale by phase, use the phase summary documents.
- For validation proofs and benchmark snapshots, use docs/evidence.
