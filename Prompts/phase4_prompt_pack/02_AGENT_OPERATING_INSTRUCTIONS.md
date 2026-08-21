# Phase 4 Agent Operating Instructions

## Core rule
Phase 4 orchestrates Phase 3. It does not rewrite Phase 3.

Never duplicate cohort reconstruction, feature engineering, preprocessing, Bagging training, Elkan training, diagnostic training, evaluation, selection, artifact writing, or artifact verification in routers or frontend code.

## Per-step workflow
1. Read freeze + current step.
2. Inspect existing code/tests.
3. State intended files.
4. Implement only current step.
5. Add focused tests.
6. Run focused tests.
7. Run full regression.
8. Run compileall and diff check.
9. Update progress tracker.
10. Stop before next step.

## Architecture discipline
- Router: HTTP only.
- Service: business flow.
- Repository: SQL.
- Worker/executor: concurrency only.
- JavaScript: presentation/API orchestration only.

## Concurrency discipline
- max one active model-training job;
- bounded executor;
- no executor at import time;
- no DB connection shared across processes;
- no hidden infinite queue.

## Progress discipline
Centralize stage names and percentages. Do not fake sub-estimator progress the underlying library cannot report.

## Error discipline
Public API/UI gets sanitized messages. Internal local metadata may retain bounded diagnostics consistent with existing Phase 3 behavior. Never expose traceback, SQL, PII, raw customer IDs, or absolute local paths.

## Frontend discipline
Preserve current visual language and Vanilla JS architecture. Enable only Model Training. Audience Explorer and Campaigns stay disabled.

## Testing discipline
Do not mark PASS based on code presence. Provide test/runtime evidence.
