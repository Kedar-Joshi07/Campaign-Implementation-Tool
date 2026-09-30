# Prompt 13 — Zero-customer blocker: root-cause package and business-policy decision gate


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

Resolve the zero-customer problem scientifically without silently weakening the approved targeting contract.

## Current condition to re-verify

Prior evidence reported calibrated purchase probabilities approximately:
- min 0.065;
- max 0.079;

while approved v2 buckets start at 0.50.

Recompute this from the canonical database/current promoted calibration. Do not trust stale evidence.

## Required diagnostics

Produce:
- calibrated probability quantiles: min, p1, p5, p10, p25, p50, p75, p90, p95, p99, max;
- raw-score quantiles;
- purchase/outcome base rate used for calibration;
- reliability table/calibration curve data;
- bucket population counts for existing approved buckets;
- top-percentile population sizes;
- expected precision/lift where statistically supported;
- model ROC-AUC/AP/lift with proper held-out lineage from Prompt 11;
- whether a 50% individual purchase probability is statistically plausible in this problem.

## Decision options

Create:
`docs/evidence/recovery_hardening/13_SELECTION_POLICY_DECISION.md`

Present at least these policy options without implementing them silently:

### Option A — keep 0.50+ absolute-probability buckets
Implication: current system remains NO-GO until model/data produce such probabilities.

### Option B — versioned lower absolute-probability buckets
Example ranges must be derived from observed distribution and business interpretation, not invented for demo convenience.

### Option C — versioned percentile/top-X% targeting
Selection based on relative ranking while still displaying calibrated purchase probability.

### Option D — versioned lift/risk-band targeting
Only if statistically justified and understandable to business users.

For each option document:
- semantics;
- risks;
- required UI changes;
- migration/contract changes;
- demo implications;
- whether exact 10K qualification is feasible without filter widening.

## No-shortcut rule

Do not:
- alter v2 thresholds;
- relabel percentiles as probabilities;
- multiply probabilities;
- change calibration merely to force higher numeric values;
- fabricate feedback;
- lower the 10K qualification minimum;
- submit nonqualifying searches.

## Output

This prompt is a mandatory human/business decision gate.

End by stating which implementation prompt should be run next:
- **14A** if the decision is to keep current absolute-probability contract and improve data/model only;
- **14B** if explicit approval is given for a new versioned percentile/probability selection contract.

Do not choose on behalf of the operator.
