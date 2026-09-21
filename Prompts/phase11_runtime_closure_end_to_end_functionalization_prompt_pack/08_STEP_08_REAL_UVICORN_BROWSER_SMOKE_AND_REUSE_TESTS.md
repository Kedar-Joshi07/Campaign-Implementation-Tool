# Step 8 — Real uvicorn Browser Smoke & Reuse Tests

Launch only:
`python -m uvicorn app.main:app`

Do not use Step19/20 custom servers.
Do not monkeypatch executor/materializer.

Use installed Chrome preferred, Edge fallback.

Browser flow:
1. Home loads.
2. Only Home / Find Potential Customers / Results visible.
3. Find Potential Customers form loads with workflow available.
4. Use searchable multi-selects.
5. Submit a bounded/current-compatible request.
6. Observe PROCESSING/COMPLETED state.
7. Navigate away to Home and back to Results.
8. Refresh browser.
9. Result remains durable.
10. View result detail.
11. Download one governed profile.

Reuse browser scenarios:
A. exact repeat → new search history, same snapshot, EXACT_RESULT_REUSE.
B. filter change → INTELLIGENCE_REUSE, no training/scoring.
C. delivery profile change → no training/scoring.

Capture:
- API requests
- console/page errors
- status transitions
- search/snapshot/generation IDs
- model/scoring counts before/after

Require zero unexplained JS/HTTP/network errors.

Create:
`docs/evidence/phase11_runtime_closure/08_REAL_UVICORN_BROWSER.md`

STOP.
