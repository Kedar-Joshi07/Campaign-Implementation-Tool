# Phase 5 Progress Tracker

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Authoritative Phase 4 baseline: `fdae4a7a40c846e4038a8ebe656257eb4164cd5d`

## Baseline
- Date: 2026-08-24
- Starting HEAD: fdae4a7a40c846e4038a8ebe656257eb4164cd5d
- Worktree: baseline verified before edits; current tree intentionally modified for Phase 5 Step 1
- Schema: v4 baseline before Step 1 (now v5)
- Full pytest: baseline 268 passed, 1 warning
- pip check: No broken requirements found
- compileall: pass (`app`, `scripts`, `tests`)
- data validation: overall_status `OK`
- customer count: 125000
- campaign_sales count: 570000
- demographic count: 5000000
- verified model_run_id: 7
- selected candidate: BAGGING_PU
- artifact SHA: a6f50f3391997bec539f1371306a81d314079020686b588a28b3c44815a1a210
- feature contract version: 1
- feature contract SHA: a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535

## Step 1 — Schema v5
Status: COMPLETE
- jobs migration: implemented `MIGRATIONS[5]` with `jobs_v5` rebuild; widened `job_type` to `MODEL_TRAINING|PROSPECT_SCORING`; added scoring-stage constraints.
- old jobs preserved: explicit v5 migration row-count parity check + migration tests confirming preservation and idempotent re-init.
- scoring_runs: created with strict lifecycle/status/count/hash/range constraints and FK links to `jobs` and `model_runs`.
- propensity_scores: created with composite PK (`scoring_run_id`, `person_id`), FK to (`scoring_runs.scoring_run_id`, `scoring_runs.model_run_id`), FK to `demographics.person_id`, and bounded score check.
- indexes: added required v5 indexes `idx_scoring_runs_newest`, `idx_scoring_runs_model_newest`, `idx_scoring_runs_status`, `idx_scoring_runs_completed_model_unique`, `idx_propensity_scores_run_score_person`.
- rollback/idempotence: covered by v5 rollback test and repeated initialize pass tests in new schema suite.
- focused/full tests: focused suites 74 passed; full suite 274 passed (1 warning).
- issues: no functional blockers; `git diff --check` reports line-ending conversion warnings only (no whitespace/hunk failures).

## Step 2 — Data access / compatibility
Status: COMPLETE
- scoreability: added `validate_scoreable_model()` in `app/services/model_scoring_compatibility.py` requiring COMPLETED + role-policy v2 + evaluation-contract v2 + PRIMARY_ROLE_GOVERNED + selected BAGGING_PU + exact v1 feature contract + verified artifact + candidate agreement.
- exact demographic columns: added bounded `ProspectScoringRepository.fetch_scoring_chunk()` in `app/repositories/prospect_scoring_repository.py` returning only `person_id` plus frozen 11 features (12 selected columns total, no forbidden fields).
- keyset query: implemented keyset-only pagination via `WHERE person_id > ? ORDER BY person_id LIMIT ?` and initial `ORDER BY person_id LIMIT ?`; explicit no `OFFSET` in query constants.
- feature/artifact preflight: added `run_scoring_preflight()` chaining `validate_and_normalize_feature_frame` -> persisted `preprocessor.transform` -> persisted estimator scoring (`positive_class_scores`) with no persistence side effects.
- age assumption: enforced frozen feature validation path (including age 18-100 contract) through shared contract validator; invalid age/income/family hard-fails preflight.
- tests/issues: new focused suites `tests/test_scoring_compatibility.py` and `tests/test_prospect_scoring_repository.py`; focused run 13 passed, combined Step1+2 focused run 18 passed; full regression 287 passed, 1 warning; no functional blockers, only line-ending warnings from `git diff --check`.

## Step 3 — Scoring engine
Status: COMPLETE
- chunk size: added direct scoring engine in `app/services/prospect_scoring_service.py` with default chunk size 25000 and enforced bounds 1000..100000.
- write strategy: per-chunk bounded persistence via new `ScoringRepository.insert_scores_chunk()` (`executemany` transaction) with no whole-population accumulation.
- score validation: each chunk enforces exact length, finite values, and unit interval [0,1] after persisted `preprocessor.transform` + `positive_class_scores(require_unit_interval=True)`.
- completion reconciliation: engine rechecks demographic snapshot count/min/max, aggregate score count/distinct count, and final keyset cursor == snapshot max before completion.
- summary: `score_summary_json` now includes count/min/max/mean, total_seconds, rows_per_second, chunk_size/count, largest chunk rows, largest transformed matrix bytes, provenance fields (model/feature/artifact), score semantics label, and age semantics note; no per-person values.
- re-score fixture: added deterministic verification helper `verify_scoring_run_sample()` (ordered bounded sample, refetch 11 features, strict allclose compare to persisted scores).
- tests/issues: new `tests/test_prospect_scoring_service.py`; expanded `tests/test_scoring_repository.py`; focused suites 27 passed; full regression 295 passed (1 warning); no functional blockers, only existing line-ending warnings from `git diff --check`.

## Step 4 — Job orchestration
Status: COMPLETE
- executor reuse: extended `app/jobs/executor.py` with `submit_prospect_scoring_job()` reusing the same lazy `ProcessPoolExecutor(max_workers=1)` path used by training; no second executor introduced.
- global active policy: generalized `JobRepository` to enforce one active compute job across `MODEL_TRAINING` and `PROSPECT_SCORING`; added `create_scoring_job()` and `find_active_compute_job()` while preserving existing training methods.
- worker: added top-level `app/jobs/prospect_scoring_worker.py` to execute queued scoring jobs, mark RUNNING (`STARTING` at 2%), relay bounded progress stages from direct scoring engine, and persist bounded completion payload (no person-level identifiers).
- stale reconciliation: startup reconciliation now fails stale active jobs of either type and marks all stale RUNNING `scoring_runs` as FAILED (including associated/orphan RUNNING runs); no auto-resume.
- training regression: retained existing training orchestration API and worker behavior; training submit path now respects global active-job lock when scoring is active.
- tests/issues: added `tests/test_scoring_job_orchestration.py`; extended `tests/test_job_executor.py` for scoring submit path and `tests/test_model_job_orchestration.py` no-BackgroundTasks guard. Focused run: 32 passed. Full regression: 303 passed, 1 warning. `pip check`: clean. `compileall`: clean (`app`, `tests`, `scripts`). `git diff --check`: line-ending warnings only; no whitespace/hunk failures.

## Step 5 — APIs
Status: COMPLETE
- POST score: added `POST /api/models/{model_run_id}/score` (HTTP 202) in `app/routers/models.py`, wired to `submit_scoring_request()` in `app/services/model_api_service.py`; no request body required.
- scoring status: added `GET /api/models/{model_run_id}/scoring-status` returning aggregate readiness only (eligibility/reason, demographic count, candidate/feature/artifact compatibility, active compute job, completed scoring run reference).
- scoring list/detail: added `GET /api/scoring-runs` (paginated newest-first with optional `status` and `model_run_id` filters) and `GET /api/scoring-runs/{scoring_run_id}` detail with identity/population/model contract/score summary only (no person-level data).
- job detail: existing `GET /api/jobs/{job_id}` now supports scoring jobs with sanitized failure messaging and validated/safe result payload decoding.
- safety/OpenAPI: updated schema contracts in `app/schemas/models.py`; OpenAPI now exposes Step 5 scoring endpoints; public JSON decoding now rejects forbidden content (person/customer identifiers, raw features, SQL/path/traceback-like content) and non-finite numeric payloads.
- tests/issues: added `tests/test_scoring_api.py`; updated `tests/test_model_api.py` OpenAPI expectations and `tests/test_phase3_hardening.py` scope gates to allow Step 5 APIs while keeping later-phase surfaces disabled. Focused Step 5 suites: 27 passed. Full regression: 311 passed, 1 warning. `pip check`: clean. `compileall`: clean (`app`, `tests`, `scripts`). `git diff --check`: line-ending warnings only; no whitespace/hunk failures.

## Step 6 — UI
Status: COMPLETE
- scoring panel: extended Model Training workspace with a dedicated Prospect Scoring section showing model run identity, PRIMARY candidate, artifact/feature compatibility, demographic universe count, readiness state, status reason, and completed scoring-run reference.
- CTA/progress/summary: added governed `Score Prospect Universe` CTA, scoring submission wiring (`POST /api/models/{model_run_id}/score`), active job polling reuse via `GET /api/jobs/{job_id}` every 1500ms, and aggregate completion rendering from scoring detail (`GET /api/scoring-runs/{scoring_run_id}`) including scored count, reconciliation, min/mean/max, runtime, rows/sec, and contract/artifact provenance.
- compute cross-disable: implemented shared compute lock in frontend so any active training/scoring job disables both Train and Score CTAs and updates announcements consistently.
- Audience Explorer disabled: preserved existing nav gating (Audience Explorer and Campaigns remain disabled as later-phase entries).
- tests/issues: updated `tests/test_frontend.py` for Step 6 panel/controls/endpoints/polling/already-completed behavior/cross-disable/disclaimer and no-individual-data constraints. Focused UI run: 32 passed (`tests/test_frontend.py` + `tests/test_historical_ui.py`). Full regression: 311 passed, 1 warning. `pip check`: clean. `compileall` (`app`, `tests`, `scripts`): clean. `git diff --check`: line-ending warnings only; no whitespace/hunk failures.

## Step 7 — Full 5M validation
Status: COMPLETE (GO)
- initial execution result (history): NO-GO due feature-contract age violation on demographics (`age` outside 18..100) before first persisted scoring chunk.
- remediation applied: repaired 1,096,838 out-of-contract rows in both live DB demographics and generated 5M demographics source file; hardened generator with `enforce_age_contract(...)` for future outputs.
- rerun evidence source: `logs/phase5_step7_rerun_report.json` (real API path, polling history, reconciliation, conflict checks, deterministic sample verification) and `logs/phase5_step7_validation.log` (concise execution ledger).
- full tests/pip/compile/diff/data: `pip check` clean; full `pytest -q` 311 passed, 1 warning; `compileall` clean (`app`, `tests`, `scripts`); `git diff --check` line-ending warnings only; `scripts/validate_data.py --json` overall_status `OK`.
- preflight (rerun): DB path `data/campaign_poc.db`; DB size 3,342,602,240 bytes; free disk 326,868,164,608 bytes; demographic count 5,000,000; model_run_id 7; selected candidate `BAGGING_PU`; role policy `2`; evaluation contract `2`; feature contract `1` SHA `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`; artifact SHA `a6f50f3391997bec539f1371306a81d314079020686b588a28b3c44815a1a210`.
- real API path (rerun): `POST /api/models/7/score` -> 202 (job_id 16), poll `GET /api/jobs/16` -> terminal `COMPLETED`, `GET /api/scoring-runs/5` -> `COMPLETED`, `GET /api/models/7/scoring-status` now returns completed-scoring reference and ineligible for resubmission.
- exact 5M reconciliation: MET. snapshot=5,000,000; scored=5,000,000; score rows=5,000,000; duplicate person IDs=0; invalid demographic FK=0; nonfinite=0; score<0=0; score>1=0.
- scoring aggregates/runtime: min=0.006214199504618037; mean=0.04663573730897857; max=0.9908241192195328; total_seconds=2591.537831999998; rows_per_second=1929.3563606367618.
- bounded-memory/keyset evidence: chunk_size=25000; chunk_count=200; largest_chunk_rows=25000; largest_transformed_matrix_bytes=3,280,796; repository scoring reads remain keyset-only (`ORDER BY person_id LIMIT ?`, `WHERE person_id > ? ORDER BY person_id LIMIT ?`) with no `OFFSET`.
- conflict hardening (real API): while job 16 active, scoring submit returned 409 and training submit returned 409.
- deterministic sample re-score: `verify_scoring_run_sample(scoring_run_id=5, sample_size=256)` verified=true, max_abs_diff=0.0.
- scope scan: no individual score API; no Audience Explorer/bands/percentiles/audience/campaign/export/activation/linkage surfaces activated.
- final SHA: working tree remains uncommitted; baseline commit still `fdae4a7a40c846e4038a8ebe656257eb4164cd5d` until a Phase 5 baseline commit is created.
- Go/No-Go Phase 6: GO.

## Pre-Phase-6 Phase 5 Finalization
Status: COMPLETE (GO)
- Note: This section records the canonical state at that historical checkpoint. It is no longer the current Phase 6 handoff baseline and is superseded by the Step 8 current canonical chain below.
- starting implementation SHA: `0d1425da0bacd020decb79b5d2d7b201b0c894e0`.
- dataset regeneration: demographics source regenerated adult-from-source under frozen age contract (18..100), with no post-hoc age mutation.
- canonical demographics import: `import_id=5`, `source_checksum=7d57a02add836f448ed2d937e60bb6c0d38402c3c82e6f219b54e904e0e0c2db`, `rows_read=5,000,000`, `rows_inserted=5,000,000`, `rows_rejected=0`.
- historical canonical at that checkpoint: `model_run_id=6`, `job_id=18`, `scoring_run_id=7` (superseded by Step 8 current canonical chain).
- reconciliation: demographic snapshot `5,000,000`; scored `5,000,000`; score rows `5,000,000`; duplicate person IDs `0`; invalid demographic FK `0`; nonfinite `0`; below-zero `0`; above-one `0`.
- score stats: min `0.006140909845521252`, mean `0.044244679521142034`, max `0.9943604573869449`.
- runtime and throughput: `total_seconds=1572.4510145999993`, `rows_per_second=3179.749291758956`.
- chunk and memory profile: `chunk_size=25000`, `chunk_count=200`, `largest_chunk_rows=25000`, `largest_transformed_matrix_bytes=3396428`.
- direct deterministic re-score: `verify_scoring_run_sample(scoring_run_id=7, sample_size=256)` -> `verified=true`, `max_abs_diff=0.0`.
- provenance verification: `demographic_import_id`, `demographic_source_checksum`, `demographic_snapshot_count`, `model_run_id`, `artifact_sha256`, `feature_contract_version`, and `feature_contract_sha256` all present and matched current loaded demographics source.
- conflict evidence during active scoring: second scoring submit `409`; training submit `409`.
- evidence artifact: `logs/phase5_prephase6_step3_rerun_report.json`.
- post-run gates: `python -m pip check` clean; `python -m pytest -q` 318 passed, 1 warning; `python -m compileall -q app scripts tests` clean; `git diff --check` no whitespace errors (line-ending warnings only); `python scripts/validate_data.py --json` overall_status `OK`.
- scope lock: no Phase 6 functionality implemented (Audience Explorer, person lookup, score bands/percentiles/deciles, audience selection/persistence, campaign builder, export, activation all remain absent/disabled).

## Step 5 — Final Acceptance and Phase 6 Baseline Freeze
Status: COMPLETE (GO)
- starting SHA for this correction stream: `eeed03d052cc75987cc8926b088d906ae0fb7ccc`.
- final acceptance artifact: `docs/evidence/phase5_final_corrections_validation.json` (sanitized; no absolute paths, PII, SQL, raw IDs, or tracebacks).
- required final gates:
	- `python -m pip check` clean;
	- `python -m pytest -q` -> `328 passed`;
	- `python -m compileall -q app scripts tests` clean;
	- `git diff --check` no whitespace/conflict errors (line-ending warnings only);
	- `python scripts/validate_data.py --json` -> `overall_status=OK`.
- canonical live evidence revalidated:
	- historical canonical-at-that-checkpoint `model_run_id=6` status `COMPLETED`;
	- historical canonical-at-that-checkpoint `scoring_run_id=7` status `COMPLETED`;
	- `demographic_import_id=5` status `COMPLETED`;
	- `scored_person_count=5,000,000`, persisted score rows `5,000,000`;
	- current-source provenance match `true`;
	- deterministic sample verify `true` (`max_abs_diff=0.0`).
- source-change lifecycle confirmed (bounded DB): stale historical run remains queryable/non-canonical, model becomes eligible after source change, and new canonical run completes.
- failed replacement lifecycle confirmed (bounded DB): multi-batch forced staging failure preserves live source, records FAILED import, and retains canonical verification for live source-aligned run.
- same-model coexistence confirmed: multiple `COMPLETED` runs per model across sources with one current canonical run.
- API semantics confirmed: stale history does not disable score submit, current canonical blocks duplicate scoring, run detail verification reflects current source.
- scope freeze confirmed: no Phase 6 implementation activated.
- authoritative Phase 6 baseline: final HEAD from this step's dedicated freeze commit.

## Step 8 — Final Phase 1-5 Acceptance Freeze (Current)
Status: COMPLETE (GO)
- starting SHA: `5f54c5e7138afaf615984babd32cac3a6bf2a99b`.
- final SHA at freeze completion: `5f54c5e7138afaf615984babd32cac3a6bf2a99b`.
- schema version: `8`.
- campaign source decision: regenerated campaign history was promoted as current source for final baseline.
- underage historical contact count: before `5453`, after `0`.
- canonical current imports:
	- customers: `import_id=8`, checksum `3a3449e64f582aaa17765fae2bb3c44c5352cb7c6ff723797fab322665aa36b8`.
	- campaign_sales: `import_id=9`, checksum `58106df84855c66128559c5abdf5258a9fbd950c000152d67199e1397fdaaefb`.
	- demographics: `import_id=5`, checksum `7d57a02add836f448ed2d937e60bb6c0d38402c3c82e6f219b54e904e0e0c2db`.
- canonical current derived chain:
	- analysis: `analysis_run_id=12` (`COMPLETED`, source provenance captured).
	- training: `job_id=20` (`COMPLETED`) -> `model_run_id=8`.
	- scoring: `job_id=21` (`COMPLETED`) -> `scoring_run_id=8`.
- frozen contracts and governance:
	- selected candidate: `BAGGING_PU`.
	- model role policy version: `2`.
	- evaluation contract version: `2`.
	- feature contract version/hash: `1` / `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`.
	- artifact SHA: `755e8f81bc1238673d17f59fb52044f44b5f00a8810fee82e694b4c4b8709d18`.
- score reconciliation (`scoring_run_id=8`): snapshot `5,000,000`; scored `5,000,000`; score rows `5,000,000`; distinct IDs `5,000,000`; duplicates `0`; invalid FK `0`; nonfinite `0`; below-zero `0`; above-one `0`.
- score summary: min `0.06774103945805435`, mean `0.20595671379862576`, max `0.9782832402557606`.
- deterministic verification: `verify_scoring_run_sample(scoring_run_id=8, sample_size=256)` -> `verified=true`, `max_abs_diff=0.0`.
- API path evidence:
	- `GET /api/models/8/scoring-status` -> `200`, `eligible=false`, `demographic_source_verified=true`.
	- `GET /api/scoring-runs/8` -> `200`, `status=COMPLETED`, `scored_person_count=5,000,000`.
	- `GET /api/jobs/21` -> `200`, `status=COMPLETED`.
	- duplicate `POST /api/models/8/score` -> `409`.
- Step 8 gates:
	- `python -m pip check` -> no broken requirements.
	- `python -m pytest -q` -> `344 passed`.
	- `python -m compileall -q app scripts tests` -> clean.
	- `git diff --check` -> no whitespace/conflict failures (line-ending warnings only).
	- `python scripts/validate_data.py --json` -> `overall_status=OK`.
- final integrity evidence artifact: `docs/evidence/phase1_to_phase5_final_integrity.json`.
- Phase 6 scope status: not implemented; freeze decision remains `GO`.
