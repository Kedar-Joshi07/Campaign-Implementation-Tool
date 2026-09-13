# Phase 9 Closure Acceptance

Generated: 2026-09-13

Prompt status: completed through
`06_STEP_06_FULL_REGRESSION_AND_NO_HEAVY_WORK_GATE.md`

## Current decision

LOCAL REGRESSION PASS - closure Steps 1-6 are complete.

Final GO is not yet declared. Step 06 full regression and no-heavy-work
verification passed; Step 07 exact-SHA CI and freeze remain required.

## Correct SHA chain

| Milestone | SHA | Status |
|---|---|---|
| Frozen Phase 1-8 baseline | `d6a9f9b963622a334bf3e5c3220e5d0a73e528fe` | Historical authoritative baseline |
| Original Phase 9 schema/contracts | `d78ad1fb8347060d033b8b7a49902610ca676a53` | Historical intermediate implementation |
| Original final Phase 9 implementation and browser candidate | `00e8588b08b15abb1ad7db200d2bc9b88871fd18` | Historical original certification candidate |
| Original Phase 9 evidence freeze | `f1fc86b7c25b83a82b530876f675cc9ad530a916` | Historical original freeze evidence |
| Corrected Phase 9 documentation/freeze baseline | `6934c586780b5f8f5bd57d533b5597ea63dec8cc` | Closure pre-fix baseline |
| Closure interoperability implementation | Pending commit | Not invented before commit |
| Closure browser recertification/final freeze | Pending Step 07 | Exact SHA and CI not yet run |

## Interoperability acceptance

- Strategy: Option B safe block and redirect.
- Legacy single-branch Saved Audience: exact filters and selection reopen; PASS.
- Phase 9 single-branch Target Group: detected and safely reopenable; PASS.
- Phase 9 multi-branch Target Group: detected by branch count; legacy reopen
  disabled; required guidance and redirects visible; PASS.
- Branch 1 incomplete population: prevented in both rendered state and defensive
  handler path; PASS.
- Branch SHA: canonical SHA-256 validated; PASS.
- Resolved count: exact union equals stored count; PASS.
- Campaign/export members: exact expected IDs, no duplicates, count equals
  stored resolved count; PASS.
- Previous Target Group immutability, stale-source blocking, idempotent retry,
  and planning/detail PII boundary: PASS.

## Browser recertification

- Original historical browser: Google Chrome `152.0.7977.83`.
- Closure recertification browser: installed Google Chrome `153.0.8010.36`.
- Current control ledger: 75 controls.
- PASS: 71.
- JUSTIFIED_EXCLUSIVE: 4.
- FAIL: 0.
- NOT_RUN: 0.
- UNJUSTIFIED_EXCLUSIVE: 0.
- INVALID_STATUS: 0.

Real Chrome proof now covers Very Strong Match, Marital Status, Employment
Status, Resident Status, Resident Type, Type of Employment, Top Matching
Percentage, Clear All, Review-step Back, Reopen definition safe blocking, and
both closure redirect controls.

The four justified exclusions are retained historical mutually exclusive
error/retry states with individual explanations. There is no generic exception
bucket.

## Browser-discovered contract correction

Chrome exposed that the new service fields were missing from the FastAPI saved
audience detail response model. The response model now declares Phase 9
detection, branch count, legacy-reopen capability, and guidance. An API-level
multi-branch regression protects the complete response path. The repeated live
Chrome action returned successfully.

## Completed verification through Step 6

| Gate | Result |
|---|---|
| Deterministic baseline reproduction | PASS |
| Legacy/single/multi-branch focused interoperability tests | PASS |
| Explicit Step 3 tests | 7 passed in 83.68s |
| Modified-module Step 3 regression | 57 passed in 180.81s |
| Browser-discovered API correction regression | 3 passed in 12.85s |
| Python compileall for changed Python files | PASS |
| Control coverage checker | PASS - 71 PASS, 4 justified, 0 fail/unrun/unjustified |
| Documentation stale-value scan | PASS after Step 5 corrections; historical values classified rather than rewritten |
| Model retraining | NOT RUN - prohibited and unnecessary |
| 5M rescoring | NOT RUN - prohibited and unnecessary |
| Full pytest | PASS - 557 passed in 416.48s |
| Focused Phase 9 interoperability | PASS - 7 passed in 40.28s |
| Phase 9 planner/preview/recommendation | PASS - 24 passed in 44.47s |
| Phase 8 browser harness unit tests | PASS - 13 passed in 0.22s |
| Clean-room Phase 1-7 | PASS - deterministic isolated run and cleanup |
| Explicit source/link/export contracts | PASS - 5 passed in 48.23s |
| Full compileall | PASS |
| pip check | PASS - no broken requirements |
| git diff --check | PASS - no whitespace errors |
| Repository/LFS pointer hygiene | PASS |
| Git LFS object integrity | PASS |

## Documentation authority

This report and `README.md` in this directory are authoritative for current
closure status. The original Phase 9 Step 14 report, manifest, and final
acceptance remain historical evidence for their original candidate and browser
run. Historically accurate SHA, browser-version, count, timing, and scenario
facts were not rewritten.

`docs/PHASE_9_IMPLEMENTATION_SUMMARY.md` now records:

- the correct original candidate and freeze chain;
- the pending closure exact SHA without guessing;
- current 75/71/4/0/0 control totals;
- Saved Target Groups, Insights, and Region additions;
- safe-block multi-branch interoperability behavior; and
- unchanged Phase 10 boundaries.

## Pending release gates

- exact committed SHA CI: pending Step 07.
- final freeze and GO decision: pending Step 07.

## Step result

STEP_06_COMPLETE_STOP

Step 07 was not started.
