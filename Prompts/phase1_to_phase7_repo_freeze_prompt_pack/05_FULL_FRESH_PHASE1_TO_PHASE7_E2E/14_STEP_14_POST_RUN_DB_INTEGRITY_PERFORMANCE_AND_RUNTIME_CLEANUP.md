# Step 14 — Post-Run DB Integrity, Performance & Runtime Cleanup

Record real timings for:
data generation, imports, historical analysis, training, scoring, audience preparation,
options/search/profile/save, campaign creation/finalization and both exports.

Confirm bounded architecture:
- no whole-5M scoring DataFrame
- keyset/bounded ranking where required
- streaming/fetchmany export
- no permanent 5M campaign-member table
- no accidental full CSV buffering

Inspect final DB state:
current imports, completed analysis/model/scoring, 5M scores, 100 boundaries,
current analytics snapshot, saved audience, finalized campaigns and completed export events.

Verify no abandoned staging tables, active compute jobs, active audience-preparation jobs or STARTED export events remain.

Run `PRAGMA integrity_check`; expected result `ok`.

Clean non-curated browser temp/cache/profiles/traces/videos/downloads, validation DBs/models,
caches, WAL/SHM and temporary logs. Default local runtime DB may remain if intended and ignored. STOP.
