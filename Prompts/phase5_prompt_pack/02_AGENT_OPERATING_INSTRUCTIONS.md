# Phase 5 Agent Operating Instructions

## Primary rule

Phase 5 adds inference/orchestration/persistence. It does not redesign training.

Reuse the existing authoritative functions/constants, especially:

```text
load_verified_model_artifact()
FEATURE_CONTRACT / VERSION / SHA
ORDERED_FEATURES
validate_and_normalize_feature_frame()
positive_class_scores()
Phase 4 job patterns
Phase 4 ProcessPoolExecutor
```

Do not copy model verification or feature logic into routers.

## Step discipline

For every step: read freeze + step, inspect current code, state planned files, implement only current step, add focused tests, run focused tests, full pytest, compile, diff check, update tracker, STOP.

## Database

Use direct `sqlite3`, parameterized SQL, bounded transactions, no ORM, no per-row commits, no one-transaction 5M write.

## Memory

Never use whole-universe `fetchall`, `SELECT *`, whole-5M pandas, or an accumulated 5M score list. One chunk only.

## Pagination

Use `person_id` keyset pagination; no OFFSET in scoring loop.

## Features

Raw DataFrame columns exactly `ORDERED_FEATURES`. Validate/normalize using frozen contract, then persisted preprocessor. Never fit/refit anything on demographics.

## Artifact

Before first scoring read: completed model, v2 Bagging governance, exact feature contract, verified artifact SHA/payload, DB/artifact candidate agreement. Any failure stops scoring.

## Privacy

`person_id` is internal scoring identity. No customer_id. No prospect PII needed for scoring. Do not log person IDs or score rows.

## Jobs

Generalize the existing job framework backward-compatibly. One active heavy job globally across training/scoring.

## Failure

Error → job FAILED and scoring_run FAILED if created. Partial failed scores remain isolated and ineligible. Public errors sanitized.

## Tests

Use small fixtures for most tests; exactly one final full-data run proves 5M behavior.

## Documentation

Append Phase 5 evidence; preserve Phase 1–4 history. Final Phase 5 HEAD becomes Phase 6 baseline.
