# 19.3 additional conditional and background cases — 2026-10-15

Status: **case-scoped PASS; overall 19.3 remains NO-GO**. Starting HEAD was
`9bea771940f930504ee8635c7b14fc988a37568c`; the working tree is uncommitted
and contains substantial pre-existing 19.1–19.3 work. These cases do not merge
different QA copies into one all-UI certificate.

## Native headed Chrome cases

- `output/post14b_closure/njqcsf08p/native_home_rejoin.json`: a real aborted
  Home overview fetch produced the unavailable/error state; the visible retry
  fetched the real API, displayed the database-backed zero-run empty state,
  and restored online status. A form-created v3 search was `QUEUED` when its
  application tab closed; a new tab reopened it and observed completion. The
  database recorded one attempt, one generation, one snapshot, 200 selected
  synthetic members, progress through scoring/materialization, and no active job.
- `output/post14b_closure/n0t08lvi7/native_home_restart_rejoin.json`: first
  harness attempt could not open a new page because Chrome closed its last tab.
  Preserved as a harness failure, not product evidence.
- `output/post14b_closure/nmlpovygd/native_home_restart_rejoin.json`: with a
  blank QA keeper tab, the pre-fix copied app timed out after restart. Startup
  rejected the old process's still-fresh execution lease and had no later
  recovery scan. The durable run remained `PROCESSING`; this reproduced the
  product defect without touching operator data.
- `output/post14b_closure/nj175dnfy/native_home_restart_rejoin.json`: the
  repaired copied app passed the same browser action and owned-server restart.
  The run was `QUEUED` at page close; after the two-minute lease-staleness
  window a bounded coordinator sweep fenced the former owner and resumed the
  existing attempt. Chrome reopened a completed result with 200 members;
  database state was one attempt, one generation, one result snapshot, no
  active jobs. No second attempt or duplicate result was created.

Both passing cases used installed headed Chrome 155, loopback production
FastAPI/worker code, isolated QA profiles, and dedicated 200-demographic
synthetic databases. The restart root's guard admissions are in
`output/post14b_closure/nj175dnfy/guard_admissions.jsonl`: every admitted
population was 200 demographics under a 2,000 cap, including both startups,
durable dispatch, worker execution and v3 scoring. No canonical 5M path ran.
The expected single request failure was the intentionally aborted Home fetch.
The browser reports record zero page exceptions and stopped owned servers.

## Repair and tests

`Phase11SearchCoordinator.resume_durable_searches()` now starts a bounded
recovery monitor. It retries durable queued/processing work every 15 seconds
in production; a still-live foreign lease is deferred until the existing
120-second stale threshold, then normal token-rotating claim fencing applies.
The monitor stops with the coordinator. A new unit test proves no premature
takeover, eventual takeover, rotated token, and preservation of attempt 1.

- `pytest tests/test_phase11_runtime_coordinator.py -q`: **14 passed** after
  the final cadence change.
- `pytest tests/test_phase11_attempt_execution_fencing.py
  tests/test_phase11_search_result_registry.py -q`: **84 passed**.
- `git diff --check`: no whitespace errors (only existing CRLF normalization
  warnings in other modified files).

These results close the specific Home failure/retry and page-close/server-
restart recovery paths. They do **not** close the other 19.3 conditional UI,
retained-component, responsive/accessibility, export/feedback and same-candidate
coverage gates listed in `19_3_REMAINING_GATES.md`.
