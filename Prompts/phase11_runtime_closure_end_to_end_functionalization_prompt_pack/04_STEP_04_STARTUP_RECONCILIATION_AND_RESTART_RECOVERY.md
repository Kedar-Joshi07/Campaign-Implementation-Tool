# Step 4 — Startup Reconciliation & Restart Recovery

Wire Phase11 durable recovery into the real FastAPI lifespan.

Startup order must be reasoned carefully with Phase10:
- initialize coordinator/materializer;
- reconcile Phase10 orchestrations;
- identify Phase11 QUEUED/PROCESSING searches;
- submit them to Phase11 coordinator;
- reconcile stale exports.

Do not synchronously process every queued search inside startup.
Resume by bounded scheduling so app startup completes.

For each resumed search:
- re-read durable state;
- reuse current Phase10 orchestration/generation where valid;
- never duplicate result snapshot;
- never create duplicate heavy model/scoring work.

Test:
A. QUEUED before shutdown → resumed.
B. PROCESSING waiting on Phase10 → resumed.
C. PROCESSING waiting on snapshot publication → safely completed/retried.
D. COMPLETED → not re-run.
E. BLOCKED/FAILED → remain terminal unless explicit user retry exists.

Create:
`docs/evidence/phase11_runtime_closure/04_RESTART_RECOVERY.md`

STOP.
