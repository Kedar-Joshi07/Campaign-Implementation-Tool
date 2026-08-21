# Single Master Phase 4 Prompt

Implement Phase 4 in `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git` from baseline `04e61caddedcf7963e824e2ccc425ac241d03842`.

Read and obey:
```text
01_PHASE_4_FREEZE_AND_BOUNDARIES.md
02_AGENT_OPERATING_INSTRUCTIONS.md
09_JOB_LIFECYCLE_CONTRACT.md
10_MODEL_API_CONTRACT.md
11_MODEL_TRAINING_UI_CONTRACT.md
14_SECURITY_AND_TEST_MATRIX.md
08_PROGRESS_TRACKER.md
```

Core model roles remain:
```text
PRIMARY = BAGGING_PU + Logistic Regression
CHALLENGER_1 = ELKAN_NOTO_LOGISTIC + Logistic Regression
DIAGNOSTIC_CONTROL = NAIVE_PU_LABEL_BASELINE
```

Execute gated steps:
1. Step 1 schema/jobs, test, update tracker, STOP.
2. Step 2 background orchestration, test, update tracker, STOP.
3. Step 3 APIs, test, update tracker, STOP.
4. Step 4 UI, test, update tracker, STOP.
5. Step 5 hardening/final validation, complete acceptance checklist, STOP.

Non-negotiable:
- no 5M scoring;
- no propensity table;
- no Audience Explorer;
- no campaign workflow/export;
- no customer/person mapping;
- no algorithm picker;
- no Bagging disable;
- no challenger auto-promotion;
- no raw customer/person data in API/UI;
- no Redis/Celery/Kafka.

Required app flow:
```text
Model Training UI
→ completed historical analysis
→ POST training
→ HTTP 202 + job_id
→ bounded local worker
→ poll progress
→ completed model_run_id
→ render model result
```

Final report must include starting/final SHA, files changed, schema version, full tests, data validation, executor type/max_workers, analysis_run_id, job_id, model_run_id, stage progression, selected model, top-10 lift/recall, challenger status/deltas, quality flags, artifact SHA/verification, restart test, concurrency test, UI walkthrough, scope scan, and Go/No-Go for Phase 5.

Do not begin Phase 5.
