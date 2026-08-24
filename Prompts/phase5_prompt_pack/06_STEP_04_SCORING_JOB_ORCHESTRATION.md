# Step 4 — Scoring Job Orchestration

## Objective

Execute scoring through the existing bounded process framework.

Do not create a second executor. Reuse `ProcessPoolExecutor(max_workers=1)` and add `submit_prospect_scoring_job` plus top-level `prospect_scoring_worker.py`.

## Worker

Fetch queued scoring job → mark RUNNING → call scoring service → persist progress → mark COMPLETED. Worker opens its own DB connections.

## Generalize job repository

Preserve training methods while adding `create_scoring_job`, global `find_active_compute_job`, generalized progress/result validation and stale handling. One active job across training/scoring.

Scoring request JSON only:

```json
{"model_run_id": 7}
```

No chunk-size control.

Completion result bounded to scoring_run_id/model_run_id/counts/min/max/mean/runtime/throughput/feature/artifact provenance. No person IDs.

## Submit service

Before queueing: model preliminarily scoreable, no completed canonical scoring run, no active heavy job. Worker re-verifies before scanning.

## Startup

Stale active jobs of either type FAILED; associated/orphan RUNNING scoring_runs FAILED; completed/failed history unchanged. No auto-resume.

## Tests

Immediate queued return; same executor; training blocks scoring; scoring blocks training/second scoring; success/fail/artifact fail; result bounded; stale/orphan scoring run handling; Phase 4 training regressions.

STOP after Step 4.
