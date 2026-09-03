# Workstream 5 — Full Fresh Data → Real 5M → Browser Phase 1→7 E2E

Final proof: remove old runtime/generated state, regenerate all synthetic data, create a fresh DB, execute every phase, score all 5M prospects and test the application through real browser interactions.

Where a UI action exists, do not substitute direct DB/service writes. Backend reads are allowed only as independent assertions.
