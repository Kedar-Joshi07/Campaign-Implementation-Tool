# Step 7 — Exact-SHA CI & Phase 9 Freeze

Before commit require:
- all tests PASS
- browser recertification PASS
- control ledger consistent
- documentation consistent
- no runtime artifacts staged
- no unintended LFS changes

Suggested commit:
`fix: close phase9 targeting interoperability and certification gaps`

Push and verify exact final SHA in GitHub Actions.

Required successful jobs:
- Repository Hygiene
- Python Validation
- Tests
- Clean-Room Phase1-7
- Frontend Contract / bounded Phase 9 validation

Create:
`docs/evidence/phase9_closure/PHASE9_FINAL_FREEZE_REPORT.md`

Include:
- Phase 1–8 baseline
- Phase 9 pre-fix SHA
- final Phase 9 SHA
- chosen reopen strategy
- exact test counts
- browser/version
- final control totals
- exact CI run ID/results
- whether retraining/rescoring was required
- Phase 10 readiness
- FINAL DECISION

GO only if:
- no lossy first-branch reopen remains
- all reachable controls have real browser proof
- docs are consistent
- regression is green
- exact-SHA CI is green

After GO, freeze Phase 9 and move to Phase 10.

STOP.
