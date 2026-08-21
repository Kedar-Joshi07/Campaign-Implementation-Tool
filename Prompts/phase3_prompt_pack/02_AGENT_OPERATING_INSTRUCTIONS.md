# Phase 3 Agent Operating Instructions

These instructions apply to every Phase 3 step.

## Baseline discipline

- Work from `52396010f945b0328b84453ce25c587b11ed7fd7`.
- Do not rewrite Phase 2 cohort semantics.
- Before editing, inspect existing files that own the behavior you are extending.
- Preserve direct `sqlite3`, FastAPI, HTML/CSS/Vanilla JS architecture.
- Make additive migrations only.

## Execution discipline

For each step:

1. Read the freeze document.
2. Read the relevant step document.
3. Inspect existing code/tests before editing.
4. State what files you intend to change.
5. Implement only the current step.
6. Add focused tests.
7. Run focused tests.
8. Run the full existing test suite.
9. Run compile checks.
10. Inspect `git diff --check`.
11. Update `11_PROGRESS_TRACKER.md`.
12. Stop before the next step.

Do not automatically continue to later steps.

## Modeling discipline

- Never convert unlabeled into “true negative.”
- Never use `customer_id`, PII, campaign behavior, product behavior, spend or response history as model inputs.
- Never query demographics to enrich historical customer rows.
- Never fit preprocessing on validation data.
- Never calculate age using today's date.
- Never choose a model by accuracy alone.
- Never present the diagnostic naive baseline as PU learning.
- Never generate 5M prospect scores in this phase.

## SQL discipline

- Parameterize values.
- Dynamic identifiers must come only from code-owned allowlists.
- Keep cohort reconstruction semantics consistent with Phase 2.
- Avoid pandas materialization of 570K campaign observations when SQL can reduce them to ~121K customer rows first.

## Artifact discipline

- Model files are runtime artifacts, not source.
- Add artifact directories to `.gitignore`.
- Store relative paths plus SHA-256 in SQLite.
- Do not serialize customer IDs or raw data.
- Validate reloading after writing.

## Dependency discipline

- Add only dependencies required for Phase 3.
- Record installed versions at model-training time.
- Prefer BSD/MIT/Apache-compatible open-source packages.
- Do not silently change algorithms because of a dependency problem.
- If `pulearn` compatibility fails, stop with evidence and document the issue before choosing a fallback.

## Error handling

- Persist internal traceback/diagnostics for failed local model runs.
- Future/public-facing messages must be sanitized.
- Never persist secrets or unnecessary filesystem detail in user-facing metadata.

## Testing discipline

At minimum, tests must cover:

- migration from v2 to v3;
- rollback on failed migration;
- invalid analysis run;
- failed/not-completed run rejection;
- cohort count mismatch rejection;
- no duplicate customer rows;
- no demographics query;
- no prohibited feature;
- deterministic age;
- deterministic split;
- unseen category handling;
- preprocessing train-only fit;
- genuine PU estimator fit;
- metric bounds;
- artifact reload equivalence;
- artifact hash;
- failed model run persistence;
- no propensity-scoring implementation.

## Completion discipline

Do not mark a checklist item PASS based only on code presence. Attach evidence: test name/output, direct SQL reconciliation, file path, or runtime result.
