# Step 10 — Failure, Retry, Restart & Shutdown Certification

Use the real app composition.

Certify:
- Phase10 BLOCKED → Phase11 BLOCKED with safe message.
- Phase10 FAILED → Phase11 FAILED.
- snapshot materializer failure → no fake COMPLETED state.
- corrupt snapshot → exact cache fails closed.
- export abort → audit reflects failure/abort safely.
- coordinator unexpected exception → run fails safely, app stays alive.

Restart scenario:
1. start real app;
2. create a search that reaches PROCESSING;
3. stop app cleanly;
4. restart same app/main and DB;
5. verify search is resumed automatically;
6. reaches correct terminal state;
7. no duplicate model/scoring/snapshot.

Shutdown:
- coordinator stops accepting new work;
- no unhandled thread/future leaks;
- durable search state remains valid;
- model/scoring executor shutdown behavior remains unchanged.

Create:
`docs/evidence/phase11_runtime_closure/10_FAILURE_RESTART_SHUTDOWN.md`

STOP.
