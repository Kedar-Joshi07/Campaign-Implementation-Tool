# Step 4 — Ignore Rules, Attributes & Structure

Strengthen `.gitignore` for caches, venv/env, DB/WAL/SHM, logs/output, staging, model artifacts, validation-runtime dirs, temp dirs, browser traces/downloads and nested regen/runtime folders. Do not ignore canonical data or intended fixtures.

Audit `.gitattributes` and line endings. Normalize Python/JS/CSS/MD/JSON conservatively while preserving binary/GZIP/LFS behavior. Avoid unnecessary whole-repo churn.

Keep repo structure clear and minimal. STOP.
