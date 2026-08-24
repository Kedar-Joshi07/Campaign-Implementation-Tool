# Phase 5 Schema v5 Contract

## jobs

Single compute-job framework with `MODEL_TRAINING` and `PROSPECT_SCORING`; old training rows and semantics preserved. Scoring jobs require model_run_id and no analysis_run_id. Type-specific stages enforced.

## scoring_runs

One row per scoring attempt. FAILED may have isolated partial scores. Only COMPLETED is usable. Partial unique index permits only one COMPLETED run per model while allowing failed retry attempts.

Include job/model FKs, prospect snapshot count/min/max, processed count/chunk/last key, model/feature/artifact provenance, min/max/mean summary, JSON summary, terminal error.

Use `UNIQUE(scoring_run_id, model_run_id)` to support composite provenance FK from score rows.

## propensity_scores

```text
PRIMARY KEY(scoring_run_id, person_id)
(scoring_run_id, model_run_id) FK → scoring_runs
person_id FK → demographics
propensity_score REAL NOT NULL CHECK 0..1
```

No PII/features/rank/band/timestamps.

Required ranking index:

```text
(scoring_run_id, propensity_score DESC, person_id ASC)
```

Downstream eligibility always requires `scoring_runs.status='COMPLETED'`.

## Migration

Safely rebuild jobs inside transactional migration: create replacement, copy exact rows, verify/preserve IDs, drop/rename, recreate indexes, create scoring tables/indexes, update schema version. Test populated Phase 4 jobs.
