# Phase 11 Runtime Closure & End-to-End Functionalization Prompt Pack

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`
Baseline: `9009e23b750000d3f3d29e09204281f3d301e640`

## Purpose
Close the remaining Phase 11 runtime-composition gap so the documented normal runtime:

`python -m uvicorn app.main:app --reload`

actually executes the full business workflow:

Home → Find Potential Customers → Smart Reuse / Phase 10 Preparation → Result Snapshot → Results → Omnichannel Download.

## Current known blocker
The engine is implemented, but `app.main` does not configure the Phase 11 search executor/materializer.
`PHASE11_SEARCH_EXECUTOR` therefore remains `None` in the normal app and accepted searches can be saved as BLOCKED.

## Goals
- wire the real runtime;
- add bounded Phase 11 coordination;
- resume durable searches after restart;
- preserve Phase 10 heavy-work ownership;
- certify real `app.main`, not a special certification server;
- clean stale runtime documentation;
- verify exact-SHA CI and freeze.

## Steps
1. Reproduce runtime gap
2. Design bounded coordinator
3. Implement coordinator + app composition
4. Startup reconciliation/restart recovery
5. Submission/concurrency safety
6. Snapshot/export runtime wiring
7. Real app API integration tests
8. Real uvicorn browser smoke/reuse tests
9. Real uvicorn full 5M certification
10. Failure/retry/restart/shutdown certification
11. Documentation cleanup
12. Branch governance/release readiness
13. Full regression/hygiene
14. Exact-SHA CI/freeze
