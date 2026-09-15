# Phase 10 Evidence Index

This directory is the authoritative evidence set for Phase 10 Campaign Intelligence Orchestration. Read the final acceptance and freeze report first; numbered documents retain step-level reasoning, implementation, and test history.

## Authoritative final evidence

| Artifact | Scope |
|---|---|
| `PHASE10_FINAL_ACCEPTANCE.md` | Consolidated functional, compatibility, browser, full-5M, regression, privacy, and release acceptance |
| `PHASE10_FINAL_FREEZE_REPORT.md` | Exact implementation/documentation SHA chain, exact-SHA GitHub Actions evidence, and freeze decision |
| `15_FULL_5M_CERTIFICATION.md` | Human-readable clean-head installed-browser full-5M certification |
| `15_FULL_5M_CERTIFICATION.json` | Machine-readable identities, hashes, counts, timings, linkage, and gate results |
| `15_CLEANROOM_PHASE1_TO_PHASE7_REPORT.md` | Phase 1–7 clean-room report executed during Step 15 |
| `15_cleanroom_phase1_to_phase7.json` | Structured Phase 1–7 clean-room evidence executed during Step 15 |

## Implementation and verification evidence

| Step | Artifact | Scope |
|---:|---|---|
| 1 | `01_BASELINE_AND_ARCHITECTURE.md` | Phase 9 freeze reconciliation, architecture, executor constraints, and gaps |
| 2 | `02_CONTEXT_IDENTITY_AND_POLICIES.md` | Modeling Context and layered compatibility contracts |
| 3 | `03_HISTORICAL_CONTEXT_EXTENSION.md` | Context-aware historical filtering and deterministic reconstruction |
| 4 | `04_SCHEMA_AND_REGISTRY.md` | Schema v15 generation/orchestration/binding registry |
| 5 | `05_HISTORICAL_COMPATIBILITY_AND_ELIGIBILITY.md` | Exact historical reuse and P/U eligibility |
| 6 | `06_MODEL_COMPATIBILITY.md` | Model reuse, validation, role governance, and artifact integrity |
| 7 | `07_SCORING_RANK_COMPATIBILITY.md` | Full-universe scoring, rank, and analytics compatibility |
| 8 | `08_ORCHESTRATION_ENGINE.md` | Durable reuse/build orchestration, idempotency, and recovery |
| 9 | `09_API_AND_PHASE9_BRIDGE.md` | API contracts and atomic Phase 9 READY publication |
| 10 | `10_BUSINESS_UI.md` | Automatic business flow, progress, retry, and progressive disclosure |
| 11 | `11_LIFECYCLE_RETENTION.md` | Lifecycle classification, protection, usage tracking, and no deletion |
| 12 | `12_TEST_MATRIX.md` | Requirement-to-test matrix and full regression |
| 13 | `13_CLEANROOM_PHASE10_REPORT.md` | Bounded clean-room reuse/build/recovery scenarios |
| 13 | `13_cleanroom_phase10.json` | Machine-readable bounded clean-room results |
| 14 | `14_SYSTEM_BROWSER_CERTIFICATION.md` | Installed-Chrome business-flow and control certification |
| 14 | `14_UI_COVERAGE.json` | Complete actionable-control ledger |
| 14 | `14_SYSTEM_BROWSER_TELEMETRY.json` | Browser console/network telemetry |
| 14 | `14_SYSTEM_BROWSER_SCREENSHOTS.json` | Responsive screenshot manifest |

## Authority and reading order

1. Start with `../../PHASE_10_IMPLEMENTATION_SUMMARY.md` for architecture, flows, API, invalidation, and lifecycle behavior.
2. Read `PHASE10_FINAL_ACCEPTANCE.md` for consolidated GO criteria.
3. Read `PHASE10_FINAL_FREEZE_REPORT.md` for the exact trusted SHA and CI result.
4. Use `15_FULL_5M_CERTIFICATION.json` for exact production-scale machine facts.
5. Use numbered reports for detailed design rationale and historical step results.

Phase 10 evidence is additive. It does not replace the Phase 8 release-assurance evidence or the Phase 9 closure/interoperability freeze for the behavior those phases own.
