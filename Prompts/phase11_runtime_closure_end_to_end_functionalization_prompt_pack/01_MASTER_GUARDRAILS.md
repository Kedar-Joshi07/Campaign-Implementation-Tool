# Master Guardrails

Baseline: `9009e23b750000d3f3d29e09204281f3d301e640`

Preserve all Phase 1–11 analytical semantics. Do not redesign model/scoring/ranking, Phase 9 targeting,
Phase 10 compatibility, Phase 11 cache, snapshots, or omnichannel contracts.

Runtime coordinator rules:
- bounded workers only;
- no unbounded thread-per-click design;
- no 5M work in the HTTP request thread;
- no duplicate Phase 10 heavy executor;
- no recursive submit/wait on the existing single-worker ProcessPool;
- SQLite remains durable authority;
- result snapshots remain contact-PII-free.

Normal app startup MUST configure the Phase 11 workflow so `workflow_available=true`.
If runtime composition fails, surface explicit service unavailability rather than silently freezing Phase 11 as GO.

Final certification MUST use `python -m uvicorn app.main:app`.
Special Step19/20 servers may remain utilities but cannot be the decisive release proof.
