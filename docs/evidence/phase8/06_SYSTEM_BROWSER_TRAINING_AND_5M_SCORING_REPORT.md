# Phase 8 Step 6 System Browser Training and Full 5M Scoring Report

Generated at: 2026-09-08T10:16:54Z

## Scope
- Prompt executed: Prompts/phase8_release_assurance_system_browser_prompt_pack/06_STEP_06_SYSTEM_BROWSER_MODEL_TRAINING_AND_FULL_5M_SCORING.md
- Training and scoring submissions executed through system-browser UI controls only.

## Browser
- name: system_chrome
- executable: C:\Program Files\Google\Chrome\Application\chrome.exe
- version: 152.0.7977.82
- mode: headless

## Model Training Through UI
- Source analysis: #2 · Phase8 Step5 Narrow 1788862579
- Source analysis run id: 2
- Trained model run id: 1
- Lifecycle observed: QUEUED -> RUNNING -> COMPLETED
- Source selected/P/U: 11662 / 1297 / 10365
- Summary selected/P/U: 11662 / 1297 / 10365
- Selected PRIMARY (UI): BAGGING_PU
- Policy version (UI): 2
- Feature count (UI): 11
- Artifact verification (UI): Verified
- Backend train/validation counts: train=9329, validation=2333, train_positive=1038, validation_positive=259

## Full 5M Scoring Through UI
- Scoring run id: 1
- Lifecycle observed: QUEUED -> RUNNING -> COMPLETED
- Prospect universe (UI): 5000000
- Scored prospects (UI): 5000000
- Reconciliation (UI): 5,000,000 / 5,000,000
- Runtime (UI): 916.16s
- Throughput (UI): 5,458 rows/s

## Independent Backend Assertions
- Contracts and selection: features=11, feature_contract=1, model_role_policy=2, evaluation_contract=2, selected_candidate=BAGGING_PU
- Feature contract SHA-256: a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535
- Artifact SHA-256: 3c5a8e083acaaf86aab03cc44000f0247789ff837d4efdac8cc6c1f7b1ff0a19
- 5M integrity: snapshot=5000000, score_rows=5000000, distinct_ids=5000000, duplicates=0, invalid_fk=0, non_finite=0, out_of_range=0
- Provenance: canonical=True, demographic_source_verified=True, historical_source_verified=True
- Deterministic rescore: sample_size=256, max_abs_diff=0.0, verified=True
- Runtime/chunks/throughput: seconds=916.1634407999954, rows_per_second=5457.541501147428, chunk_size=25000, chunk_count=200, largest_chunk_rows=25000

## UI Error Telemetry
- Console errors: 0
- Page errors: 0
- Request failures: 0

## Inventory Coverage
- Controls updated in this step: 12

## Outcome
- Step 6 completed with UI-only model training submission, UI-only full 5M scoring submission, lifecycle observation, and independent backend integrity/provenance verification.