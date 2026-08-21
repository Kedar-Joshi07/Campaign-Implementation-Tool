# Phase 3 Acceptance Checklist

Mark each item `PASS`, `FAIL`, `PARTIAL`, or `NOT TESTED`. Attach evidence.

Any failed **Critical** item means **No-Go for Phase 4**.

## A. Base and repository integrity

- [x] PASS — **Critical** `git rev-parse HEAD` is the exact accepted Phase 2
  baseline `52396010f945b0328b84453ce25c587b11ed7fd7`.
- [x] PASS — Baseline evidence records 158 tests passing in 51.42s before Phase 3.
- [x] PASS — The initial prompt pack and all accumulated Phase 3 work remain
  uncommitted; unrelated prior/user changes were preserved.
- [x] PASS — `git status --short -- data` and `git diff --name-only -- data`
  returned no source-data changes; `git lfs status` listed no LFS data object change.
- [x] PASS — `git ls-files` found no `.db`/`.joblib`; the populated DB and both
  artifacts resolve to `.gitignore` rules.
- [x] PASS — Phase 2 tracker clarification names the accepted SHA without changing
  historical pre-commit counts/timings.
- [x] PASS — Final `git diff --check` passed; only informational line-ending
  notices were emitted.

## B. Frozen scope

- [x] PASS — **Critical** Frontend remains static HTML/CSS/Vanilla JavaScript;
  focused frontend/historical UI tests passed.
- [x] PASS — **Critical** Backend remains FastAPI/Python/direct `sqlite3`.
- [x] PASS — Requirements/source scan found no TensorFlow, PyTorch, XGBoost,
  LightGBM, MLflow, Airflow, Redis, Celery, Kafka, or Spark addition.
- [x] PASS — **Critical** Source/scope scan found no customer/person mapping.
- [x] PASS — **Critical** SQL-trace cohort test and source scan found no training
  query against `demographics`.
- [x] PASS — **Critical** No prospect-scoring path exists; full model execution
  completed in 1.857761s without a 5M scan.
- [x] PASS — Schema/source scan found no `propensity_scores` table or API.
- [x] PASS — Frontend contract test confirms Model Training remains disabled and
  labeled “Later phase.”
- [x] PASS — Audience Explorer and Campaigns navigation remain disabled; no
  audience/campaign builder or export implementation exists.

## C. Dependencies and licensing

- [x] PASS — scikit-learn 1.7.1 is installed and persisted per model run.
- [x] PASS — pulearn 0.0.12 is installed and persisted per model run.
- [x] PASS — joblib 1.5.2 is installed and persisted per model run.
- [x] PASS — BSD-style/BSD-3-Clause licensing is documented in README, the
  implementation summary, and `15_LIBRARY_AND_LICENSE_NOTES.md`.
- [x] PASS — Final `python -m pip check` reported no broken requirements.
- [x] PASS — Full data fitted Elkan–Noto and Bagging PU; no dependency fallback or
  silent naive substitution occurred.

## D. Schema v3

- [x] PASS — **Critical** ordered transactional v2→v3 migration and repeated
  initialization tests pass.
- [x] PASS — Fresh initialization reaches schema v3 with all expected tables.
- [x] PASS — Populated v2 migration preserves Phase 1/2 counts and run snapshot.
- [x] PASS — Injected v3 migration failure leaves schema v2 and rolls back DDL.
- [x] PASS — Future schema versions are rejected.
- [x] PASS — All 26 frozen `model_runs` columns and count/status/hash constraints
  are asserted by schema tests.
- [x] PASS — Both model-run indexes exist; populated validation found all 23
  required application indexes.
- [x] PASS — `model_runs` has no BLOB column; artifact is stored on disk.
- [x] PASS — Schema test confirms no propensity-score table.

## E. Analysis reconstruction

- [x] PASS — **Critical** missing, RUNNING, FAILED, and malformed analyses are
  rejected; only structurally valid `COMPLETED` runs proceed.
- [x] PASS — **Critical** reconstruction reuses the code-owned Phase 2 matching
  observation/customer-label CTE.
- [x] PASS — Full run 10 reconciled 14,037 matching observations exactly.
- [x] PASS — **Critical** selected count reconciled at 14,037.
- [x] PASS — **Critical** positive count reconciled at 626.
- [x] PASS — **Critical** unlabeled count reconciled at 13,411.
- [x] PASS — **Critical** `626 + 13,411 = 14,037` and schema/service tests enforce
  the invariant.
- [x] PASS — **Critical** reconstruction returns one unique row per customer.
- [x] PASS — Fixture proves observations outside saved filters cannot alter label.
- [x] PASS — contacted-only and inclusive date behavior is tested.
- [x] PASS — ATTRIBUTED_PURCHASE, ANY_PURCHASE, and RESPONSE fixtures pass.
- [x] PASS — age uses saved `contact_date_to`.
- [x] PASS — birthday/on-day and day-before age boundaries pass.
- [x] PASS — mutated current-source counts/labels trigger reconciliation failure.

## F. Feature boundary

- [x] PASS — **Critical** raw model X is exactly the 11 ordered frozen features.
- [x] PASS — Internal `customer_id` is removed before preprocessing/model fit.
- [x] PASS — Feature-contract and artifact tests find no source PII in X/metadata.
- [x] PASS — No ZIP/address field is selected.
- [x] PASS — No campaign/product/offer/channel field is selected.
- [x] PASS — No engagement/purchase/spend/margin/recency field is selected.
- [x] PASS — `pu_label` is target-only and absent from X.
- [x] PASS — No ethnicity/religion/industry/family-income field is selected.
- [x] PASS — Contract version 1 has deterministic SHA-256
  `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`.

## G. Split and preprocessing

- [x] PASS — Split is at unique-customer grain.
- [x] PASS — Seed 42 is the default and persisted.
- [x] PASS — Validation fraction 0.20 is the default and persisted.
- [x] PASS — Full split overlap is zero; unit tests enforce disjoint membership.
- [x] PASS — Both partitions require known positives and unlabeled rows.
- [x] PASS — Same-seed train/validation membership hashes matched exactly.
- [x] PASS — Leakage tests prove preprocessor fit uses training rows only.
- [x] PASS — Missing numeric values transform to finite matrices.
- [x] PASS — invalid age/income/family values fail explicitly.
- [x] PASS — null/blank categorical values normalize to `Unknown/Other`.
- [x] PASS — unseen validation categories transform without failure.
- [x] PASS — Full data records 11 raw and 64 transformed features plus names,
  cardinalities, and imputation values.

## H. PU training

- [x] PASS — **Critical** Elkan–Noto and Bagging genuine-PU estimators fitted.
- [x] PASS — **Critical** Elkan–Noto candidate ran successfully with documented
  bounded dense compatibility conversion.
- [x] PASS — naive baseline is named/marked diagnostic-only and non-PU.
- [x] PASS — governance tests prevent naive selection even if role metadata is
  misdeclared.
- [x] PASS — full-data Bagging challenger fitted 10 estimators in 0.243–0.672s
  measured candidate runs.
- [x] PASS — all-positive/all-unlabeled training cohorts are rejected.
- [x] PASS — fewer than five training positives is rejected.
- [x] PASS — all full-data candidate score vectors were finite and nonconstant.
- [x] PASS — same-seed candidate scores, selected model, and persisted predictions
  are reproducible.

## I. Evaluation

- [x] PASS — **Critical** all documentation/metrics call class 0 unlabeled, never
  true negative.
- [x] PASS — accuracy is neither calculated nor used for selection.
- [x] PASS — ROC-AUC is named `observed_label_roc_auc` with disclaimer.
- [x] PASS — AP is named `observed_label_average_precision` with disclaimer.
- [x] PASS — known-positive recall@5/10/20 is persisted for every fitted candidate.
- [x] PASS — known-positive lift@5/10/20 is persisted for every fitted candidate.
- [x] PASS — count/mean/median/std/p10/p25/p75/p90 are recorded by label group.
- [x] PASS — non-finite and negative score tests fail evaluation.
- [x] PASS — constant scores raise `LOW_SCORE_VARIANCE` and cannot win.
- [x] PASS — **Critical** selected `BAGGING_PU` is genuine PU; all-genuine failure
  never falls back to naive.
- [x] PASS — transparent selected/eligible comparison reason is persisted.
- [x] PASS — canonical JSON tests find no IDs, PII, or per-row scores.

## J. Persistence

- [x] PASS — real completion plus injected pipeline/completion failures prove both
  guarded lifecycle transitions and cleanup.
- [x] PASS — model runs 1/2 persist source analysis ID 10.
- [x] PASS — canonical feature, preprocessing, selected hyperparameters, and full
  evaluation snapshots are populated.
- [x] PASS — exact Python/NumPy/pandas/SciPy/scikit-learn/pulearn/joblib versions
  are persisted.
- [x] PASS — artifact paths are relative and path traversal is rejected.
- [x] PASS — joblib lives under ignored `artifacts/models`, not SQLite.
- [x] PASS — SHA-256 is persisted and independently matched to file bytes.
- [x] PASS — both full-data artifacts reload through the verified loader.
- [x] PASS — 128 reloaded scores match with maximum absolute difference 0.0.
- [x] PASS — missing and checksum-corrupt artifacts fail clearly.
- [x] PASS — payload/metadata tests find no rows, ID list, matrices, PII, or
  per-customer scores.

## K. CLI

- [x] PASS — `--analysis-run-id` is required by argparse.
- [x] PASS — real JSON output returned model run IDs 1 and 2.
- [x] PASS — subprocess failure test returned exit code 1.
- [x] PASS — success/failure `--json` subprocess outputs parsed.
- [x] PASS — failure summary is sanitized; traceback remains local in SQLite/log.
- [x] PASS — README and implementation summary document current flags/lifecycle.

## L. Regression and hardening

- [x] PASS — final full suite: 219 passed in 126.75s, no warnings reported.
- [x] PASS — final `compileall` passed with no output.
- [x] PASS — all Phase 1 API regression tests pass; endpoints unchanged.
- [x] PASS — all Phase 2 API regression tests pass; endpoints unchanged.
- [x] PASS — focused frontend/Historical Analysis UI regression passed.
- [x] PASS — no browser customer/person-level endpoint or payload was introduced.
- [x] PASS — trace/source/performance evidence proves training never scans
  demographics.

## M. Full-data evidence

- [x] PASS — populated completed analysis 10 reconstructed successfully.
- [x] PASS — 14,037 observations/customers = 626 positive + 13,411 unlabeled.
- [x] PASS — both genuine-PU candidates trained; Bagging PU selected.
- [x] PASS — observed-label and top-slice metrics are recorded in tracker/docs/DB.
- [x] PASS — model runs 1/2 have verified 10,108-byte artifacts.
- [x] PASS — run 2 records all six stages and 1.857761s governed total.
- [x] PASS — model run 2 is the same-seed rerun; all semantic evidence matched.
- [x] PASS — limitations are documented in README and implementation summary.

## Final decision

Record:

- Critical failures: None.
- Other failures/partials: None.
- Full test result: 219 passed in 126.75s; no warnings reported.
- Full-data reconstruction: analysis 10; 14,037 observations/customers; 626
  known positives; 13,411 unlabeled; exact reconciliation.
- Selected PU candidate: `BAGGING_PU`.
- Key validation lift/recall: top 5% 1.911830 / 0.096; top 10% 1.598861 /
  0.160; top 20% 1.159174 / 0.232.
- Artifact reload status: PASS; both 10,108-byte artifacts match SHA-256
  `04913a2eb766d116b2e73ea9842ecf25914b3360f35e1fee65860351841bf1de`.
- Reproducibility status: PASS; split fingerprints, contract, selected candidate,
  non-runtime metrics, metadata, 128 scores, and artifact bytes matched exactly.
- Residual risks: synthetic observed-label evidence is not population ground
  truth/calibration; local synchronous SQLite/joblib design is not production
  multi-user infrastructure; Elkan 0.0.12 requires bounded dense training input;
  timings are machine/cache dependent.
- **Go / Conditional Go / No-Go for Phase 4:** **Go for Phase 4.**
- Reasoning: every Critical and non-Critical acceptance item passed with direct
  tests, SQL/count reconciliation, runtime evidence, scope scans, persisted
  metadata, artifact checksum/reload, and same-seed reproducibility. Phase 4 can
  safely consume a verified `COMPLETED model_run_id` without adding scoring or
  later audience/campaign scope.
