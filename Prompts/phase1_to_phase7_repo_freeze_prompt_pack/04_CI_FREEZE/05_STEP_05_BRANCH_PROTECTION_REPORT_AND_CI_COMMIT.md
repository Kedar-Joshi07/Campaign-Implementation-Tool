# Step 5 — Branch Protection, Report & Commit

Document exact required check names. If authorized/safe, enable main protection only after CI is green; otherwise create `docs/BRANCH_PROTECTION.md` with exact UI steps.

Create `docs/evidence/CI_FREEZE_REPORT.md`.

Run locally: pytest, clean-room Phase1→7, compileall, pip check, diff check and workflow syntax validation.

Commit: `ci: freeze reproducible phase1-7 quality gates`

Record SHA. STOP.
