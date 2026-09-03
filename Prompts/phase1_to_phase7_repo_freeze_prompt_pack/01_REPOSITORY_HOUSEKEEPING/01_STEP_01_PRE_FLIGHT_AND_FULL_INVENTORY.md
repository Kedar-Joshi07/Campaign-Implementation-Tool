# Step 1 — Pre-flight & Full Repository Inventory

Record branch, local/remote HEAD, git status, Python/pip/Git/Git LFS versions, schema/app version and current test count. Do not discard uncommitted user work.

Recursively inventory every tracked/untracked file and classify it as runtime code, frontend, schema, ML, generator, canonical data, fixture/sample, runtime DB, model artifact, cache/temp/log, validation material, operational script, historical debug/benchmark script, browser artifact, docs, evidence, prompts, tests, output or orphan.

Create `docs/evidence/repository_housekeeping_inventory.json` with path, category, tracked status, size, LFS status, references, keep/archive/delete decision and reason.

Do not delete anything yet. STOP.
