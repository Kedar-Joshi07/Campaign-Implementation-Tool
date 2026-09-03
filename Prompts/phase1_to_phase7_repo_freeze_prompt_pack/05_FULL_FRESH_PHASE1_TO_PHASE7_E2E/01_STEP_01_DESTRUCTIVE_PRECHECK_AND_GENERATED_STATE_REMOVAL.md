# Step 1 — Destructive Precheck & Generated-State Removal

Before deleting anything record branch/local+remote HEAD/git status/schema/app version/current data checksums/DB counts/model/scoring/audience/campaign/export state.

STOP destructive work if uncommitted user changes exist. Never delete `.git`, source code, schemas, tests, docs or generators.

Remove generated/runtime state:
DB/WAL/SHM, generated model artifacts, exports/downloads/output, browser temp/cache, old logs/caches, validation DBs and temporary generation/runtime folders.

Remove current generated source outputs that the generators are expected to recreate, while preserving only proven static non-generated lookups, `.gitkeep` and README metadata.

Verify empty runtime state and create pre-run manifest. STOP.
