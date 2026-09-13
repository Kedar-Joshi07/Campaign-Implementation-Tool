# Phase 9 Closure Evidence Index

This directory is the current authoritative evidence location for the Phase 9
closure and interoperability correction workstream.

The original Phase 9 evidence under `../phase9/` remains historically accurate
for the implementation and browser certification completed on candidate
`00e8588b08b15abb1ad7db200d2bc9b88871fd18`. It must not be read as evidence
that the later multi-branch interoperability correction has completed exact-SHA
CI or final freeze.

## Current authority

| Artifact | Scope | Status |
|---|---|---|
| `PHASE9_CLOSURE_ACCEPTANCE.md` | Current acceptance status, SHA chain, browser/control totals, completed gates, and pending release gates | Authoritative |
| `06_REGRESSION_REPORT.md` | Full regression, clean-room, compatibility, static, dependency, repository/LFS, and no-heavy-work gates | Authoritative supporting evidence |
| `04_BROWSER_CONTROL_RECERTIFICATION.md` | Installed-Chrome proof for previously static-only controls and multi-branch safe block/redirect | Authoritative supporting evidence |
| `03_INTEROPERABILITY_TEST_REPORT.md` | Explicit legacy, single-branch, multi-branch, membership, immutability, PII, stale, and retry regressions | Authoritative supporting evidence |
| `02_MULTI_BRANCH_REOPEN_FIX_REPORT.md` | Option B safe-block design and compatibility behavior | Authoritative supporting evidence |
| `01_BASELINE_AND_DEFECT_REPRODUCTION.md` | Baseline reconciliation and deterministic defect reproduction | Historical closure baseline |

The regenerated actionable-control ledger remains at
`../phase9/final_system_browser/ui_control_coverage.json` because existing
validation tooling consumes that path. Its current totals are 75 controls: 71
PASS, 4 JUSTIFIED_EXCLUSIVE, 0 FAIL, and 0 NOT_RUN.

## SHA authority

- Frozen Phase 1-8 baseline: `d6a9f9b963622a334bf3e5c3220e5d0a73e528fe`
- Original Phase 9 implementation/browser candidate: `00e8588b08b15abb1ad7db200d2bc9b88871fd18`
- Original Phase 9 evidence-freeze commit: `f1fc86b7c25b83a82b530876f675cc9ad530a916`
- Corrected Phase 9 documentation/freeze baseline: `6934c586780b5f8f5bd57d533b5597ea63dec8cc`
- Closure interoperability implementation SHA: pending commit
- Closure exact-SHA CI/freeze SHA: pending Step 07

Pending values are intentionally not replaced with a working-tree or guessed
hash.

## Reading order

1. Read `PHASE9_CLOSURE_ACCEPTANCE.md` for current status.
2. Read `01_BASELINE_AND_DEFECT_REPRODUCTION.md` for the original defect.
3. Read `02_MULTI_BRANCH_REOPEN_FIX_REPORT.md` for the chosen safe-block design.
4. Read `03_INTEROPERABILITY_TEST_REPORT.md` for regression protection.
5. Read `04_BROWSER_CONTROL_RECERTIFICATION.md` for real Chrome proof.
6. Read `06_REGRESSION_REPORT.md` for the complete local regression and
   no-heavy-work decision.
7. Use `../phase9/` only for the historically accurate original Phase 9
   implementation, certification, and design records.

## Release status

Closure Steps 1-6 are complete. Full regression and no-heavy-work verification
passed. Exact-SHA CI/freeze remains reserved for Step 07. The current decision
is LOCAL REGRESSION PASS, not final GO.
