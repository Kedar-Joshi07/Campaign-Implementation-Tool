# Phase 9 Closure Evidence Index

This directory is the current authoritative evidence location for the Phase 9
closure and interoperability correction workstream.

The original Phase 9 evidence under `../phase9/` remains historically accurate
for the implementation and browser certification completed on candidate
`00e8588b08b15abb1ad7db200d2bc9b88871fd18`. The closure artifacts in this
directory supersede it for the later multi-branch interoperability correction,
exact-SHA CI, and final freeze decision.

## Current authority

| Artifact | Scope | Status |
|---|---|---|
| `PHASE9_CLOSURE_ACCEPTANCE.md` | Current acceptance status, SHA chain, browser/control totals, completed gates, and GO decision | Authoritative |
| `PHASE9_FINAL_FREEZE_REPORT.md` | Exact implementation SHA, CI run/job results, heavy-work decision, Phase 10 readiness, and final freeze | Authoritative final evidence |
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
- Closure interoperability/final implementation SHA: `111a9205df79ea160f5929dc25cc84f4e7a1fd19`
- Exact-SHA CI: workflow `CI` run `#10`, ID `34740649936`, SUCCESS
- Documentation/freeze evidence SHA: `5dd4537eda6a500ae381e62b013379372ef9568b`
- Exact documentation/freeze-SHA CI: workflow `CI` run `#11`, ID
  `34740956664`, SUCCESS
- Evidence-integrity/fail-closed regression correction SHA:
  `e49e579076e0c6bf78be5026ccafbb2c72e98549`
- Exact correction-SHA CI: workflow `CI` run `#12`, ID `34743755762`, SUCCESS

## Reading order

1. Read `PHASE9_FINAL_FREEZE_REPORT.md` for the final GO/freeze decision.
2. Read `PHASE9_CLOSURE_ACCEPTANCE.md` for the complete acceptance status.
3. Read `01_BASELINE_AND_DEFECT_REPRODUCTION.md` for the original defect.
4. Read `02_MULTI_BRANCH_REOPEN_FIX_REPORT.md` for the chosen safe-block design.
5. Read `03_INTEROPERABILITY_TEST_REPORT.md` for regression protection.
6. Read `04_BROWSER_CONTROL_RECERTIFICATION.md` for real Chrome proof.
7. Read `06_REGRESSION_REPORT.md` for the complete local regression and
   no-heavy-work decision.
8. Use `../phase9/` only for the historically accurate original Phase 9
   implementation, certification, and design records.

## Release status

Closure Steps 1-7 are complete. Full regression, browser recertification,
no-heavy-work verification, and exact-SHA CI passed. The final decision is GO,
and Phase 9 is frozen for handoff to Phase 10.
