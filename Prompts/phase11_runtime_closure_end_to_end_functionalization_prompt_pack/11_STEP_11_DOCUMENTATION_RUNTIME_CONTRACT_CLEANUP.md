# Step 11 — Documentation & Runtime Contract Cleanup

Update README and runtime documentation to match reality.

README must accurately state:
- Phase 1–11;
- schema version 18;
- normal command `python -m uvicorn app.main:app --reload`;
- visible UI = Home / Find Potential Customers / Results;
- hidden analyst/legacy views remain implemented but not user-visible;
- Phase11 coordinator is initialized automatically;
- omnichannel profiles;
- smart reuse;
- result snapshot behavior.

Fix the stale README section that currently lists old visible tabs.

Update FastAPI `description` in app.main so it no longer describes only a Phase1–7-style POC.
Mention:
- automatic Phase10 intelligence;
- Phase11 smart result reuse;
- omnichannel governed downloads;
- no outbound activation/send integration yet.

Document runtime ownership:
HTTP → Phase11 coordinator → Phase10 → result snapshot → export.

Document startup/restart behavior.

Do not overclaim:
- no auth/RBAC yet;
- no outbound activation;
- no feedback ingestion/retraining yet.

Create:
`docs/PHASE_11_RUNTIME_ARCHITECTURE.md`
and evidence report.

STOP.
