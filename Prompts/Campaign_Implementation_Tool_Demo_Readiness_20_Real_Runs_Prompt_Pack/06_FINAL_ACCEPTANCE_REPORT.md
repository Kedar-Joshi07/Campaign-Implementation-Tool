# 06 — Final Acceptance Report

Create:
`docs/evidence/demo_readiness/DEMO_READINESS_FINAL.md`

Required sections:

1. Exact starting and final SHA/worktree state.
2. Repository audit verdict with severity table.
3. Dependency/compile/test/data-validation results.
4. Schema-19 and SQLite integrity evidence.
5. Lifecycle/progress/ETA/blocked-failed verification.
6. Smart-reuse and currentness verification.
7. 20-scenario preload table with exact real selected counts and run IDs.
8. Count of scenarios with >100 customers.
9. Any scenario <=100 and proposed-but-not-run fallback.
10. Browser/UI verification.
11. Concurrency-race investigation result.
12. Housekeeping changes made.
13. Housekeeping intentionally deferred until after demo.
14. Accepted POC limitations.
15. Final verdict: `DEMO READY`, `DEMO READY WITH CONDITIONS`, or `NOT DEMO READY`, with evidence.

Do not use a green verdict if any scenario intended for the demo is BLOCKED/FAILED/stale or if canonical DB integrity/currentness fails.
