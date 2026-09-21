# Step 5 — Submission, Idempotency & Concurrency Safety

Preserve Phase11 semantics:
every intentional user submit creates a separate immutable search_run.

Different concept:
the SAME search_run_id must never execute twice concurrently.

Test:
- rapid browser double click;
- retry from frontend;
- repeated status polling;
- startup resume racing with new request;
- two exact searches intentionally submitted;
- two different searches sharing the same Phase10 Modeling Context.

Expected:
- separate intentional search history rows where appropriate;
- exact snapshot may be shared;
- same Phase10 generation may be shared;
- no duplicate 5M scoring;
- no duplicate coordinator loop for one run;
- no duplicate snapshot for same result cache key.

Add bounded locking/active-registry strategy.
Do not introduce broad DB locks that serialize unrelated reads.

Create:
`docs/evidence/phase11_runtime_closure/05_CONCURRENCY_IDEMPOTENCY.md`

STOP.
