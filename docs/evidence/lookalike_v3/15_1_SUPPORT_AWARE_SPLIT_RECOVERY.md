# Prompt 15.1 — support-aware split recovery and Prompt 15 gate

Recorded 2026-10-09. Starting HEAD `336875c30fc32b00323d916ecc45b232016168a1`; candidate **UNCOMMITTED**. This is a dated, superseding Prompt 15 authority for the new split policy. The earlier [Prompt 15 fault report](15_FAULT_RECOVERY.md) and [Prompt 16 NO-GO](16_FULL5M.md) remain unchanged historical evidence. The worktree already contained extensive uncommitted 14B code/evidence. No operator database, raw canonical input, historical profile, score, snapshot, campaign action, remote branch or deployment was changed. Current schema is 33; this refinement needed no additive database migration.

## Outcome and cause

**PROMPT 15 = GO. PROMPT 16 = pending separate full-scale certification.** The old `CUSTOMER_UNION_HASH_ORDER_80_20_V1` policy partitioned the *union* by one hash order. A union-wide approximate 80/20 split did not guarantee per-product support: the exact recorded PRD001 cohort had 200 buyers but only 158 fit and 42 holdout, below the 160 fit floor. The unmodified source/import context was reproduced on the existing isolated 5M certification database. The recorded context has PRD001, PRD003, PRD004, historical window 2024-01-01 through 2025-12-31, attributed-purchase definition, empty historical context-filter lists, and EMAIL search channel. This does not reinterpret old artifacts.

The new `SIMILARITY_CUSTOMER_SPLIT_V2` policy solves exact, bounded integer holdout counts across the six nonempty product-membership signatures. Hard constraints are at least 200 total, 160 fit and 40 holdout buyers per product, with one assignment per customer across all products. Integer targets use `floor(0.20*n + 0.5)` and seed `20261005`. Frozen objective order: per-product absolute 20% target deviation, union deviation, assignment flips against the verified old policy, then stable signature-hash lexicographic tie breaks; within signatures, baseline holdouts are retained first and identities use a stable seeded hash. Each stage must be proved optimal by the bounded MILP; timeout/capacity is `UNRESOLVED`, never mathematical infeasibility. No demographic value, score, validation metric, or scenario yield enters the solver.

| Product | Old total / fit / holdout | New total / fit / holdout | New support |
|---|---:|---:|---|
| PRD001 | 200 / 158 / 42 | 200 / 160 / 40 | ELIGIBLE |
| PRD003 | 251 / 206 / 45 | 251 / 201 / 50 | ELIGIBLE |
| PRD004 | 1461 / 1164 / 297 | 1461 / 1169 / 292 | ELIGIBLE |

The exact solver returned **FEASIBLE** with zero product-target deviation, zero union-target deviation, and 11 baseline assignment changes. The union has 1,892 unique buyers: 1,514 fit and 378 holdout. The implementation independently verifies each actual product set after selecting identities, and each customer has one union-level assignment. Frozen private lineage hashes (no customer IDs): partition `371a8f7d92393c767fd54797202d2a9a582364fab04285df47578411320b3467`; union fit `780e56fc4b6708a06c86d83da8fcb1e530186297ab07aff2518f23ab40806011`; union holdout `d2d92d6ee4fc49951689f9e5d56fca598138fe7fec14bdbec3f25d669f0bc868`; context `63c250de563d31c5b111b5dc83b8d847223621828aca77c4b6b4d539d319e4b0`. Per-product fit/holdout hashes are in the companion [machine-readable report](15_1_SUPPORT_AWARE_SPLIT_RECOVERY.json). These hashes are lineage, not reversible identifiers.

The partition is frozen atomically before V2 profile fitting. Profile artifacts carry policy, objective, partition and fit/holdout hashes. Loading a V2 artifact rechecks the frozen partition; missing/tampered files fail closed. The existing V1 artifact shape remains readable under V1. Source, profile, generation, attestation, context, preflight, cache, snapshot and export identities remain transitively bound to the compatible profile/partition lineage. PRD003/PRD004 old-policy profiles and scores cannot be reused for V2: their fit/holdout sets changed, as did PRD001's; all three require new fitting/scoring. Old v1/v2 probability semantics and calibration artifacts are untouched.

## Validation and fault matrix

Each command ran on disposable databases and artifact roots; no command here operated on the operator canonical database. A first browser test launch encountered Windows sandbox `WinError 5`; the same browser suite passed when run with browser-launch permission. The former is not counted as a product failure.

| Command / area | Result |
|---|---:|
| `python -m pytest tests/test_buyer_similarity_support_aware_split.py -q --maxfail=1 --tb=short` | 12 passed |
| `python -m pytest tests/test_buyer_similarity_cohort_service.py -q --maxfail=1` | 10 passed |
| `python -m pytest tests/test_buyer_similarity_profile_service.py -q --maxfail=1` | 11 passed |
| `python -m pytest tests/test_buyer_similarity_scoring_service.py -q --maxfail=1` | 13 passed |
| `python -m pytest tests/test_lookalike_v3_preflight_search.py -q --maxfail=1 --tb=short` | 7 passed |
| `python -m pytest tests/test_lookalike_v3_fault_recovery.py -q --maxfail=1 --tb=short` | 27 passed |
| `python -m pytest tests/test_lookalike_v3_snapshot_export_feedback.py tests/test_lookalike_v3_baseline_compatibility.py tests/test_lookalike_v3_contract_migration.py tests/test_phase11_attempt_execution_fencing.py tests/test_phase11_runtime_coordinator.py tests/test_phase11_restart_recovery.py tests/test_search_recovery_calibration_feedback.py tests/test_buyer_similarity_assurance_service.py -q --maxfail=1 --tb=short` | 95 passed |
| `python -m pytest tests/test_lookalike_v3_integration_closure.py tests/test_lookalike_v3_business_ui.py -q --maxfail=1 --tb=short` | 12 passed |
| `python -m ruff check` on changed services and split/preflight tests | passed |

The prior 27-case fault matrix directly exercises score chunk interruption and fenced restart, verification/publication rollback, attestation, dependency rejoin, heavy-slot heartbeat and cheap reuse, preflight source replacement/cache failure, result-file crash and registry recovery, export write failure, feedback rollback/idempotence, shutdown/startup takeover, mixed v2/v3 and browser response races. The new split suite adds deterministic ordering/restart, independently infeasible overlap, capacity/timeout classification, feature and holdout-fit isolation, atomic publication/reuse, true child death after partition link, source replacement, V2 stale-owner fencing, and missing partition invalidating current attestation. The combined runs did not reveal an unresolved correctness failure. Insufficient data and mathematically infeasible support remain safe nonretryable outcomes; unresolved solver work is separately retryable.

For uncommitted tree identification, the SHA-256 hashes of key files at this gate are: split service `c09898ae89e6b6e7e7252de133844f1fcfbaedda013d350f23b5fbe058245980`; partition service `206baed8fab98f74c3b67ae53f12b47bdc85b16f06ad5c35d7800862d8fe7725`; cohort service `91bfb896c258a43d96cb8818f10730cbbb7199fce77d0632eff6e2bd38047687`; profile service `51b7a75be0206962b746f1e100e5cfad96591130ec8d28820b36c576db9751b`; orchestration service `4c3f51ee29927b4f205541072f7a5cdef860f1e886ddcf4f252c7203300e3569`; split tests `a90eef640f27bda0f51ad430bd45b0e7048862f4e746698ffd2461cbf7c486c9`. This is not a full worktree fingerprint and is not an exact-SHA release gate.

Limitations: this descriptive customer-disjoint holdout is not campaign-isolated purchase-response validation, and SQLite certification is single-node. Full-5M generation, three-product context materialization/performance, and Prompt 17 demo qualification are separate gates. Prompt 16 may now start automatically on an isolated certification database under the requested handoff.

## Post-gate Prompt 16 handoff regression addendum

The full-scale count path exposed an expensive window-rank used solely for exact preflight. A count-only indexed composite maximum path and a threshold-prefiltered membership path were added without changing score mathematics, winner ordering or selection boundaries. After those changes: `tests/test_lookalike_v3_preflight_search.py` **9 passed**; combined snapshot/export/fault suite **36 passed**; retained v1/v2 compatibility/calibration suite **32 passed**; changed-file Ruff passed. Two earlier combined-suite attempts hit a 30-second *test subprocess watchdog*; the same cases passed alone. The child watchdog was extended to a still-bounded 90 seconds for slow Windows process startup, with exit-code, rollback and fencing assertions unchanged. The subsequent clean combined run passed 36/36 in 643.09 seconds. This addendum records the final tested tree, while the earlier gate measurements remain historical.

The final affected browser/integration rerun also passed **12/12** in 170.45 seconds with local browser-launch permission. No browser failure remains on this tree.
