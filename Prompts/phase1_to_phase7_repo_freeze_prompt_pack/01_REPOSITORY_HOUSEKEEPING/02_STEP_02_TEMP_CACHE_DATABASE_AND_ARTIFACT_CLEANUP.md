# Step 2 — Temp, Cache, Database & Artifact Cleanup

Audit recursively for __pycache__, pytest/coverage caches, DB/WAL/SHM, temp/bak files, outputs/downloads, logs, browser traces/videos, model joblib files outside approved artifact paths, staging data, profiling DBs and duplicate generated CSV/GZIP files.

Explicitly inspect `data/step7_regen/` and `data/step7_validation_runtime/`. If no active runtime/test reference exists, remove them and preserve only useful summarized evidence.

No runtime DB/WAL/SHM/cache or validation joblib should remain tracked. Preserve canonical data. STOP.
