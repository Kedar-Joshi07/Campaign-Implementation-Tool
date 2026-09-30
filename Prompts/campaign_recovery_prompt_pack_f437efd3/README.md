# Campaign Implementation Tool — Recovery Hardening Prompt Pack

**Canonical baseline supplied by operator:** `f437efd3be9e6d4945b0ee12bff91ccce2697088`

This pack is designed to address the blockers, incomplete implementations, correctness defects, governance gaps, and certification gaps found in the fine-comb review of the Phase 11 recovery work.

## Why the pack is sequenced this way

Do not start with the zero-customer model problem. First make execution safe:

1. CI/API/mobile correctness
2. stale-worker fencing
3. true dependency retry
4. attestation and source currentness
5. import invalidation
6. preflight parity
7. fast reuse + timing
8. progress/ETA
9. v2 score semantics
10. catalog lifecycle
11. calibration isolation
12. feedback-learning semantics
13. business selection-policy decision
14. chosen conditional implementation path
15. fault/restart certification
16. canonical performance
17. 20-scenario qualification and real runs
18. documentation/evidence cleanup
19. final CI/release gate

## Files

- `00_MASTER_GUARDRAILS_AND_EXECUTION_ORDER.md`
- `01_EXACT_SHA_CI_API_COMPATIBILITY_AND_MOBILE_FIX.md`
- `02_DURABLE_ATTEMPT_FENCING_LEASES_AND_STALE_WORKER_PROTECTION.md`
- `03_TRUE_PHASE10_DEPENDENCY_RETRY_AND_REJOIN.md`
- `04_ATTESTATION_DEEP_VERIFICATION_AND_SOURCE_CURRENTNESS.md`
- `05_IMPORT_INVALIDATION_GENERATION_CALIBRATION_AND_PREFLIGHT_CURRENTNESS.md`
- `06_PREFLIGHT_EXACTNESS_CACHE_IDENTITY_AND_MATERIALIZATION_PARITY.md`
- `07_DIRECT_REUSE_FAST_PATH_HEAVY_GATE_AND_TIME_ACCOUNTING.md`
- `08_PROGRESS_HEARTBEAT_PHASE10_STAGE_PROPAGATION_AND_ETA.md`
- `09_V2_SCORE_SEMANTICS_MEMBERSHIP_CONTRACT_RESULTS_UI.md`
- `10_TARGETING_CATALOG_LIFECYCLE_AND_OPTION_LOAD_CORRECTNESS.md`
- `11_CALIBRATION_TRAIN_CALIBRATE_TEST_ISOLATION_AND_GOVERNANCE.md`
- `12_FEEDBACK_RECALIBRATION_PSI_AND_TRUE_MODEL_LEARNING_BOUNDARY.md`
- `13_ZERO_CUSTOMER_ROOT_CAUSE_AND_SELECTION_POLICY_DECISION_GATE.md`
- `14A_KEEP_ABSOLUTE_PROBABILITY_MODEL_IMPROVEMENT_PATH.md`
- `14B_VERSIONED_SELECTION_CONTRACT_V3_IF_APPROVED.md`
- `15_FAULT_INJECTION_RESTART_CONCURRENCY_AND_CRASH_RECOVERY_MATRIX.md`
- `16_PERFORMANCE_AND_5M_CANONICAL_CERTIFICATION.md`
- `17_20_SCENARIO_PREFLIGHT_REAL_RUN_AND_DEMO_READINESS.md`
- `18_DOCUMENTATION_EVIDENCE_BASELINE_AND_HOUSEKEEPING.md`
- `19_FULL_REGRESSION_CI_RELEASE_GATE_AND_FINAL_NO_GO_GO_REPORT.md`

## Execution rules

Run one prompt at a time. Review the result before moving on. A later prompt may depend on schema/API invariants introduced by an earlier prompt.

**Prompt 13 is an explicit policy gate.** Do not run both 14A and 14B. Run the one matching the approved business decision.

If any step returns NO-GO, fix that step before continuing unless the prompt explicitly permits a documented limitation.

## Operator checklist after every prompt

Record:
- new HEAD SHA if you commit;
- failing/passing tests;
- database migration version;
- whether canonical data was mutated;
- evidence artifact path;
- unresolved risks.

The pack deliberately prohibits fabricated counts, silent threshold changes, demographic filter widening, duplicate customers, and evidence claims from unexecuted paths.
