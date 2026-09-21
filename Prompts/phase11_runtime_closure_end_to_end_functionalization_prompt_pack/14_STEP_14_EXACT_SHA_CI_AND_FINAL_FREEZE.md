# Step 14 — Exact-SHA CI & Final Freeze

Require all Steps 1–13 PASS.

Commit implementation.
Suggested message:
`fix: wire phase11 search runtime and close end-to-end execution gap`

If docs/evidence require a later commit, distinguish:
- runtime implementation SHA
- browser/full-5M tested SHA
- final docs/freeze SHA

Push and verify GitHub Actions against exact final head SHA.

Required jobs:
- Repository Hygiene
- Python Validation
- Tests
- Clean-Room Phase1-7
- Frontend Contract / bounded Phase9+10+11+runtime validation

Normal CI does not need a full 5M rerun, but the clean-head real-app full-5M evidence from Step 9 must reference an implementation SHA with no later application-code changes.

Create:
- `docs/evidence/phase11_runtime_closure/PHASE11_RUNTIME_FINAL_ACCEPTANCE.md`
- `docs/evidence/phase11_runtime_closure/PHASE11_RUNTIME_FINAL_FREEZE_REPORT.md`

Final GO only if:
- real app.main executes searches;
- workflow_available=true;
- restart recovery works;
- reuse/build paths work;
- omnichannel downloads work;
- full 5M real-app certification passes;
- Phase1–11 regression passes;
- exact-SHA CI passes;
- docs are consistent.

After GO, replace the prior Phase11 frozen status with the corrected trusted baseline.

STOP.
