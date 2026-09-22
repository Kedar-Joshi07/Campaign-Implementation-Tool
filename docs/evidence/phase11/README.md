# Phase 11 Evidence Index

This directory is the authoritative evidence set for Phase 11 Business Workflow, Omnichannel Export, and Smart Result Reuse. Read the final acceptance and freeze report first; numbered artifacts retain step-level implementation rationale and test history.

## Authoritative final evidence

| Artifact | Scope |
|---|---|
| `PHASE11_FINAL_ACCEPTANCE.md` | Historical Phase 11 acceptance; superseded by the runtime-closure acceptance |
| `PHASE11_FINAL_FREEZE_REPORT.md` | Historical Phase 11 freeze; superseded by the runtime-closure freeze |
| `20_FULL_5M_CERTIFICATION.md` | Human-readable full-5M new-build and reuse certification |
| `20_FULL_5M_CERTIFICATION.json` | Machine-readable full-scale identities, counts, hashes, downloads, and gates |
| `19_SYSTEM_BROWSER_CERTIFICATION.md` | Installed-Chrome business-flow certification |
| `18_CLEANROOM_REPORT.md` | Deterministic bounded A/B clean-room certification |

## Implementation and verification evidence

| Step | Artifact | Scope |
|---:|---|---|
| 1 | `01_BASELINE_AUDIT.md` | Phase 10 freeze, extension seams, and guardrails |
| 2 | `02_PRODUCT_INFORMATION_ARCHITECTURE.md` | Three-screen business information architecture and future RBAC seam |
| 3 | `03_OMNICHANNEL_PROFILE_CONTRACTS.md` | Ten backend-owned profiles and privacy contracts |
| 4 | `04_CONTACTABILITY_IDENTIFIER_EXTENSION.md` | Deterministic 40-column source, import, and feature exclusion |
| 5 | `05_SEARCH_RUN_RESULT_SCHEMA.md` | Search, snapshot, and export registry contracts |
| 6 | `06_BUSINESS_NAVIGATION.md` | Three-tab navigation and retained hidden legacy UI |
| 7 | `07_MULTISELECT_COMPONENT.md` | Reusable searchable accessible multi-select |
| 8 | `08_FIND_POTENTIAL_CUSTOMERS_FORM.md` | Single business form and durable submission |
| 9 | `09_SMART_REUSE_ENGINE.md` | Exact-result → intelligence-reuse → new-build decision engine |
| 10 | `10_ATOMIC_SEGMENT_OPTIMIZATION.md` | Optional segment-index benchmark and rejection decision |
| 11 | `11_RESULT_SNAPSHOTS.md` | Atomic immutable membership materialization and recovery |
| 12 | `12_RESULTS_UI.md` | Results history/detail, currentness, and no-PII UI |
| 13 | `13_OMNICHANNEL_EXPORT_ENGINE.md` | Ten-profile bounded streaming download and audit |
| 14 | `14_HOME_OVERVIEW.md` | Bounded metadata-only business Home dashboard |
| 15 | `15_FUTURE_FEEDBACK_LINEAGE.md` | Nullable future feedback/retraining lineage seam |
| 16 | `16_API_BACKWARD_COMPATIBILITY.md` | Additive API inventory and Phase 1–10 compatibility |
| 17 | `17_TEST_MATRIX_PERFORMANCE.md` | Comprehensive bounded test/performance matrix |
| 18 | `18_CLEANROOM_REPORT.md`, `18_cleanroom_phase11.json` | Deterministic A/B reuse/build/recovery certification |
| 19 | `19_SYSTEM_BROWSER_CERTIFICATION.md` and JSON ledgers | Installed-browser business, control, accessibility, responsive, and telemetry proof |
| 20 | `20_FULL_5M_CERTIFICATION.md`, `20_FULL_5M_CERTIFICATION.json` | Full-scale source/build/reuse/download/regression certification |

## Supporting machine evidence

- `10_atomic_segment_benchmark.json` and `10_atomic_segment_benchmark_phase10_frozen.json`
- `17_performance_metrics.json`
- `19_UI_CONTROL_COVERAGE.json`
- `19_SYSTEM_BROWSER_TELEMETRY.json`
- `19_SYSTEM_BROWSER_SCREENSHOTS.json`
- `19_SYSTEM_BROWSER_CERTIFICATION.json`
- `system_browser/step19/screenshots/`
- `system_browser/step20/scenario-a-full-5m-completed.png`

## Reading order

1. Start with `../../PHASE_11_IMPLEMENTATION_SUMMARY.md`.
2. Use `../../PHASE_11_API_AND_SCHEMA.md`, `../../PHASE_11_OMNICHANNEL_PROFILES.md`, `../../PHASE_11_RESULT_SNAPSHOTS_AND_SMART_REUSE.md`, and `../../PHASE_11_BUSINESS_UI.md` for current contracts.
3. Read `../phase11_runtime_closure/PHASE11_RUNTIME_FINAL_ACCEPTANCE.md` for the current consolidated GO criteria.
4. Read `../phase11_runtime_closure/PHASE11_RUNTIME_FINAL_FREEZE_REPORT.md` for current exact SHA/CI authority.
5. Use numbered evidence for design reasoning and step-specific results.

Phase 11 evidence is additive. It does not replace the Phase 8 release-assurance, Phase 9 closure/interoperability, or Phase 10 orchestration freeze evidence for behavior those phases own.
