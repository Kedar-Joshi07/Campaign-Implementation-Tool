# Step 16 — Exact-SHA CI, Documentation & Phase 10 Freeze

Create/update:
- docs/PHASE_10_IMPLEMENTATION_SUMMARY.md
- docs/evidence/phase10/README.md
- docs/evidence/phase10/PHASE10_FINAL_ACCEPTANCE.md
- docs/evidence/phase10/PHASE10_FINAL_FREEZE_REPORT.md
- docs indexes
- architecture/data-flow/API/lifecycle documentation

Document diagrams/flows:
Business: Campaign Planner → automatic intelligence → Target Group → Campaign.
Analytical: Modeling Context → analysis? → model? → scoring? → rank? → reuse/build → READY.
Invalidation matrix.
Provenance: Context → Modeling hash → Analysis → Model → artifact → Scoring → Rank/Analytics
→ Generation → Saved Target Group → Campaign → Export.

Run final clean regression and hygiene checks.

Suggested implementation commit:
`feat: implement phase10 automatic campaign intelligence orchestration`

If docs/evidence require separate commit, distinguish tested implementation SHA from
documentation/freeze SHA.

Push and verify GitHub Actions by exact head SHA.
Required successful jobs:
Repository Hygiene, Python Validation, Tests, Clean-Room Phase1-7,
Frontend Contract / bounded Phase9+10 validation.
Add bounded Phase10 CI if appropriate; do NOT put full 5M scoring in normal CI.

GO only if:
- no latest-run fallback
- exact compatibility and reuse/build paths proven
- clean-head full 5M certification PASS
- Phase1–9 regression green
- installed-browser business flow PASS
- exact-SHA CI green
- docs/evidence internally consistent

Record final trusted Phase10 SHA and freeze Phase10.

STOP.
