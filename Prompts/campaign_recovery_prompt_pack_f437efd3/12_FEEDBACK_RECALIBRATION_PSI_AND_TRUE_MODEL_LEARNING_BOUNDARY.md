# Prompt 12 — Correct feedback learning semantics, PSI comparison, and challenger governance


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

Make the feedback loop statistically and operationally honest.

## Inspect at minimum

- `app/services/phase11_feedback_service.py`
- `app/jobs/feedback_retraining_worker.py`
- calibration publication
- model training job infrastructure
- feedback/retraining DB schema
- UI labels/docs

## Workstream A — rename semantics

If the worker only fits a new calibration over existing raw scores, rename public/internal concepts from "retraining" to **recalibration** unless a true model retraining path is implemented.

Preserve migration/backward compatibility for stored table/column names where renaming them would be destructive; business/API labels should be truthful.

## Workstream B — PSI

Audit current PSI:
feedback-selected audience score distribution versus full 5M base distribution.

Determine whether this is a valid like-for-like drift test. If not, replace it with a comparison whose populations have the same selection basis.

Possible safe designs:
- score distribution of a current comparable scoring population versus reference scoring population;
- same campaign-selection policy across time;
- use another drift metric only if justified.

Persist enough reference lineage to reproduce the drift calculation.

Do not use a metric simply because it produces a trigger.

## Workstream C — adaptive gate

Keep governed minimum label/class/run floors, but make the "new information" rule statistically coherent.

Avoid creating a new WAITING decision row on every tiny feedback batch if that causes unbounded noisy history; if needed, design bounded event/state semantics while preserving auditability.

## Workstream D — true model learning boundary

Produce a documented distinction between:
1. recalibration of an existing scoring model;
2. true model retraining using new feedback.

If true retraining is implemented in this prompt, it must:
- create a new model_run;
- follow frozen feature/governance contracts;
- evaluate challenger vs incumbent;
- rescore the current demographic universe;
- create new generation lineage;
- require promotion gates.

If that is too large/risky for this step, do not fake it. Create an explicit future-work contract and keep automatic feedback behavior named recalibration.

## Tests

- PSI/reference population correctness;
- deterministic drift calculation;
- recalibration promotion/non-regression;
- non-finite metrics rejected;
- startup recovery;
- public labels do not claim model retraining if none occurred.

## Evidence

`docs/evidence/recovery_hardening/12_FEEDBACK_LEARNING.md`

## Acceptance gate

GO when automatic feedback behavior is statistically defensible and named truthfully.
