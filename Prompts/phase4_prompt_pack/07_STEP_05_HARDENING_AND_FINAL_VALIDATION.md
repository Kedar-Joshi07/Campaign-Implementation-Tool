# Step 5 — Hardening, Full Validation, Documentation, and Phase 5 Handoff

## Objective
Prove Phase 4 is reliable under restart/failure/conflict and freeze it for Phase 5.

## Restart tests
Persist QUEUED and RUNNING jobs, simulate startup reconciliation, verify both become FAILED. COMPLETED/FAILED remain unchanged.

## Failure tests
Simulate:
- executor submission failure;
- worker crash;
- Phase 3 failure before model_run_id;
- Phase 3 failure after model_run_id;
- artifact completion failure.
No stuck RUNNING and no fake success.

## Concurrency test
Two near-simultaneous submissions: exactly one accepted, the other conflicts. No concurrent model training.

## Model-detail artifact drift
After a completed job, simulate missing/corrupt artifact. Job may remain completed historically, but model detail must report artifact verification failure safely.

## Shutdown
Executor shutdown must be handled. Do not block shutdown indefinitely. Next startup reconciles stale active jobs.

## Full-data workflow
Use a valid completed historical analysis (the established reference analysis if still valid):
1. load training options;
2. submit via application/API path;
3. verify immediate response;
4. poll stages;
5. complete;
6. obtain model_run_id;
7. fetch model detail;
8. verify Bagging PRIMARY selected;
9. verify challenger/control metrics;
10. verify artifact checksum;
11. verify no customer/person rows returned.

Record analysis_run_id, job_id, model_run_id, stage progression, timestamps, selected model, top-10 lift/recall, flags, artifact SHA, total duration.

## Full commands
```text
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
python scripts/validate_data.py --json
```

## UI walkthrough
```text
Historical Analysis
→ Model Training
→ choose analysis
→ train
→ observe progress
→ completed result
→ comparison
→ recent model list
→ reopen detail
```

Audience Explorer and Campaigns must remain disabled.

## Documentation
Update:
```text
README.md
docs/PHASE_4_IMPLEMENTATION_SUMMARY.md
08_PROGRESS_TRACKER.md
12_PHASE_4_ACCEPTANCE_CHECKLIST.md
13_PHASE_5_HANDOFF_CONTRACT.md
```
State baseline `04e61caddedcf7963e824e2ccc425ac241d03842` and document schema v4, executor choice, APIs, progress, restart semantics, limitations, and Phase 5 boundary.

## Scope scan
Prove absent: propensity_scores, demographic model scoring, score bands, Audience Explorer implementation, Campaign Builder, audience persistence, CSV export, activation adapters.

## Exit
Every Critical acceptance item passes and Phase 4 is ready for Phase 5.
