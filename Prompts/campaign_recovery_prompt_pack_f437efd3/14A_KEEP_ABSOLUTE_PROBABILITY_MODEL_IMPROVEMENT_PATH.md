# Prompt 14A — Conditional path: keep 0.50+ absolute purchase-probability contract


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


## Run only if

The operator/business explicitly chooses to retain the current absolute-probability bucket semantics.

## Objective

Improve model/data quality through governed methods without altering selection thresholds or calibration truth.

## Required work

1. Audit historical outcome quality, attribution definition, leakage, class balance, campaign coverage, and recency.
2. Determine whether the current feature set can plausibly discriminate sufficiently.
3. Evaluate legitimate model improvements compatible with the POC governance:
   - feature engineering from existing allowed fields;
   - campaign-aware training;
   - class/PU-learning improvements;
   - challenger models already allowed by repository policy;
   - better historical labels or additional governed outcome data.
4. Use proper train/calibration/test separation from Prompt 11.
5. Promote only if challenger gates are met.
6. Rescore full current demographic universe.
7. publish a new calibration and attestation.
8. rerun exact bucket distribution.

## Hard rule

If calibrated probabilities still do not enter approved buckets, report NO-GO. Do not distort the calibration to make numbers look larger.

## Tests/evidence

Create:
`docs/evidence/recovery_hardening/14A_MODEL_IMPROVEMENT.md`

Include incumbent vs challenger held-out metrics, calibration, probability distribution, and whether 10K+ exact scenarios are possible.

## Acceptance gate

GO only if the improved **honestly calibrated** model creates business-approved qualifying populations.
