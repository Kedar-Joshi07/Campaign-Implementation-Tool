# Single Master Prompt — Phase 11 Runtime Closure

Repository:
`https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Baseline:
`9009e23b750000d3f3d29e09204281f3d301e640`

Execute Steps 1–14 sequentially.

Mission:
make the normal documented runtime `python -m uvicorn app.main:app` execute the complete
Home → Find Potential Customers → Smart Reuse/Phase10 → Snapshot → Results → Omnichannel Download workflow.

Critical fix:
`PHASE11_SEARCH_EXECUTOR` must no longer remain None in normal application startup.

Implement a bounded production coordinator, real ResultSnapshotMaterializer wiring,
startup resume for QUEUED/PROCESSING searches, duplicate run suppression and clean shutdown.

Preserve:
- Phase10 heavy-work ownership
- no nested ProcessPool deadlock
- Phase11 exact cache
- immutable no-PII snapshots
- all ten omnichannel profile contracts
- Phase1–10 frozen semantics

Final proof must use real `app.main`, not Step19/20 special servers.

Require:
- real lifespan API tests
- real Chrome/Edge browser tests
- restart recovery
- exact-result reuse
- intelligence reuse
- one correct full 5M path
- all omnichannel downloads
- full regression
- exact-SHA CI
- final freeze.
