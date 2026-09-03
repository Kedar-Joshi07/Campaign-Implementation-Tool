# Step 3 — Hygiene, LFS & Browser Smoke Gates

CI hygiene must reject tracked DB/WAL/SHM, caches, unapproved model artifacts, outputs/downloads and validation-runtime debris.

Validate `.gitattributes`/LFS pointer configuration without pulling the full 5M object. Run compileall and git diff --check.

Run frontend/API contract tests. If lightweight real-browser smoke is available, use one browser engine only.

No secrets required for normal CI. STOP.
