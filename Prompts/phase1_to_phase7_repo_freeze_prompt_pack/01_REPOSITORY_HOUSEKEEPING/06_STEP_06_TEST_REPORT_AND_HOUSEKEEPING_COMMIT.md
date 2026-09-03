# Step 6 — Validation & Housekeeping Commit

Run full pytest, compileall app/scripts, pip check, git diff --check, current data validation where safe and LFS validation.

PASS only if no tracked runtime DB/WAL/SHM/cache exists, no unintended validation artifact remains, redundant regen workspaces are gone, scripts/data are clear, LFS is valid and no functionality regressed.

Create `docs/evidence/REPOSITORY_HOUSEKEEPING_REPORT.md`.

Commit: `chore: complete repository housekeeping and runtime artifact cleanup`

Record SHA. STOP.
