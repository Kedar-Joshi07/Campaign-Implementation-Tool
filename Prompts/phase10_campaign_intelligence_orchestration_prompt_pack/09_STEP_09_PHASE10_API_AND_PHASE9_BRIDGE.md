# Step 9 — Phase 10 API & Phase 9 Bridge

Recommended endpoints under /api/campaign-planner/contexts/{id}:

GET /intelligence-plan
- readiness, Modeling Context identity, reuse summary, no PII

POST /targeting-intelligence/prepare
- idempotent exact resolution
- READY immediately if reusable
- otherwise queue/start orchestration

GET /targeting-intelligence/preparation
- status/stage/progress/business_message/can_retry/is_ready/reuse summary
- nested technical details only

POST /targeting-intelligence/preparation/retry
- restart from highest verified stage

Keep existing Phase 9 GET /targeting-intelligence backward compatible.
Advanced manual link/unlink may remain for analyst/admin compatibility; normal business UI
must not need raw scoring IDs.

On READY bind verified scoring_run_id into Phase 9 source_scoring_run_id and prove existing
Phase 9 target preview/search/save works unchanged.

If Modeling Context changes, old binding cannot be treated as compatible.
If only delivery channel changes, reuse same generation.

Errors:
409 not-ready/stale conflict
422 invalid request
500 stable safe retry message, no internals/PII.

Test end-to-end with TestClient:
context → prepare → poll → READY → Phase9 preview → Save Target Group → Campaign Draft.

Evidence:
`docs/evidence/phase10/09_API_AND_PHASE9_BRIDGE.md`

STOP.
