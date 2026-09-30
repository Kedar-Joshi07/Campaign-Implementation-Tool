# Prompt 11 — Strengthen calibration methodology and leakage controls


# Common execution contract

**Canonical starting SHA:** `f437efd3be9e6d4945b0ee12bff91ccce2697088`

You are working on the repository **Campaign Implementation Tool**. Treat the current codebase, database schema, tests, migrations, and committed evidence as authoritative only after you verify them yourself. Do not assume prior summaries are correct merely because they exist in `docs/evidence`.

Before changing anything:

1. Run `git rev-parse HEAD` and confirm the starting commit is `f437efd3be9e6d4945b0ee12bff91ccce2697088` or a documented descendant created by an earlier prompt in this pack.
2. Run `git status --short`. Do not overwrite unrelated local changes. If prior pack steps created changes, preserve them and identify the exact prior step/commit.
3. Read the files named in this prompt plus adjacent callers, tests, migrations, API schemas, and frontend consumers. Search the whole repository for every symbol you modify.
4. Reproduce the current behavior with focused tests before changing it when practical.
5. Keep changes additive and narrowly scoped. Do not rewrite frozen Phase 1-10 behavior unless a defect proven by this pack requires it.
6. Preserve synthetic-data truthfulness. Do **not** fabricate customers, widen targeting filters, lower approved probability thresholds, duplicate people, change scenario definitions, or invent evidence to make a demo pass.
7. Preserve existing immutable lineage. Never rewrite historical attempts, snapshots, calibration artifacts, feedback batches, or audit events in place.
8. Never persist tracebacks, raw exception text, filesystem paths, secrets, contact PII, or unbounded payloads into business-safe runtime fields.
9. Every mutable worker write must be concurrency-safe and transactionally guarded.
10. Do not mark a requirement complete just because code exists. Prove the behavior through tests and, where requested, canonical/runtime evidence.
11. If a required business-policy decision is not encoded in the repository, stop that policy change and produce a decision document instead of silently choosing.
12. Do not commit or push unless explicitly instructed by the operator. At the end, report changed files, tests run, results, remaining risks, and the next prompt to run.

## Required completion format

End the run with:

- **Starting SHA**
- **Working tree state before**
- **Defects reproduced**
- **Root cause**
- **Files changed**
- **Schema/API/contract changes**
- **Tests added or changed**
- **Commands run**
- **Pass/fail results**
- **Evidence artifacts produced**
- **Known remaining risks**
- **GO / NO-GO for this prompt**
- **Recommended next prompt**


## Objective

Prove model training, calibration fitting, and calibration evaluation are separated by an appropriate campaign/group boundary, not merely by customer rows.

## Inspect at minimum

- model training cohort/split code;
- `app/ml/preprocessing.py`
- `app/services/training_cohort_service.py`
- `app/services/propensity_calibration_service.py`
- historical campaign/customer observation lineage
- model-run persisted split metadata
- calibration artifact schema
- tests for deterministic calibration

## First: produce a leakage audit

Document:
- unit of observation;
- customer-to-campaign multiplicity;
- current model train/validation split method;
- how calibration group IDs are assigned;
- whether one campaign can contribute customers to both model training and calibration/test;
- effect of `MIN(campaign_id)` for customers in multiple campaigns.

Do not change methodology until the audit is explicit.

## Required improved split

Design a deterministic grouped strategy that keeps campaign/group leakage bounded according to the actual data model.

A preferred conceptual structure:
- model-training campaign groups;
- calibration-fit campaign groups;
- final calibration-evaluation campaign groups;

with zero overlap where statistically feasible.

If the available dataset is too small to support a three-way campaign-group split with both outcome classes, fail transparently and document the insufficiency rather than relaxing the rule silently.

Persist split lineage:
- group IDs/hash;
- counts;
- seed;
- strategy version;
- overlap counts;
- class balance.

## Calibration selection

Continue evaluating sigmoid/isotonic or justified alternatives on a genuine held-out evaluation partition.

Promotion metrics must be calculated on data not used to fit that calibrator.

Do not optimize and report performance on the same records.

## Tests

- deterministic split for fixed seed/data;
- zero group overlap;
- both classes required in each needed subset;
- multi-campaign customer handling is deterministic and documented;
- candidate selection metric uses held-out evaluation only;
- impossible split fails safely.

## Evidence

`docs/evidence/recovery_hardening/11_CALIBRATION_ISOLATION.md`

Include old-vs-new methodology, not just passing tests.

## Acceptance gate

GO only when the promoted calibration's reported evaluation metrics are based on a genuinely held-out grouped evaluation set.
