# Phase 10 Baseline and Architecture Inventory

Generated: 2026-09-13

Prompt: `Prompts/phase10_campaign_intelligence_orchestration_prompt_pack/01_STEP_01_BASELINE_RECONCILIATION_AND_PHASE9_FREEZE.md`

## Step result

`PASS_STEP_01_BASELINE_RECONCILED_PHASE9_FROZEN`

This step is inventory and evidence only. It introduces no Phase 10 schema,
contract, service, API, UI, orchestration, training, scoring, or ranking behavior.

## Repository baseline

| Item | Recorded value |
|---|---|
| Branch | `main` |
| HEAD | `7e54754053bf998e65c59a36c0096d5404bb6479` |
| Cached `origin/main` | `7e54754053bf998e65c59a36c0096d5404bb6479` |
| HEAD subject | `docs: record phase9 correction exact-sha ci` |
| HEAD commit time | `2026-09-13T14:17:15+05:30` |
| Initial tracked-file status | Clean |
| Initial untracked scope | `Prompts/phase10_campaign_intelligence_orchestration_prompt_pack/` only |
| Repository | `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git` |

The untracked Phase 10 prompt pack is user-provided input. It was not modified,
staged, or treated as part of the frozen Phase 9 application baseline.

## Phase 9 freeze and GO evidence

The authoritative closure evidence is
`docs/evidence/phase9_closure/PHASE9_FINAL_FREEZE_REPORT.md` and
`docs/evidence/phase9_closure/PHASE9_CLOSURE_ACCEPTANCE.md`.

| Gate | Frozen result |
|---|---|
| Phase 9 closure decision | `PHASE_9_CLOSURE_FROZEN_GO` |
| Interoperability implementation SHA | `111a9205df79ea160f5929dc25cc84f4e7a1fd19` |
| Initial documentation/freeze SHA | `5dd4537eda6a500ae381e62b013379372ef9568b` |
| Evidence-integrity correction SHA | `e49e579076e0c6bf78be5026ccafbb2c72e98549` |
| Final frozen handoff SHA | `7e54754053bf998e65c59a36c0096d5404bb6479` |
| Full regression | 558 passed |
| Focused interoperability matrix | 8 passed |
| Browser control ledger | 75 total: 71 PASS, 4 justified-exclusive, 0 failed/not-run/unjustified/invalid |
| Browser | Installed Google Chrome 153.0.8010.36 |

The final handoff SHA was independently verified against GitHub Actions by exact
`head_sha`:

- workflow: `CI`;
- run number: 13;
- run ID: `34748488710`;
- URL: <https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool/actions/runs/34748488710>;
- head SHA: `7e54754053bf998e65c59a36c0096d5404bb6479`;
- status/conclusion: `completed` / `success`;
- jobs: Repository Hygiene, Python Validation, Tests, Frontend Contract, and
  Clean-Room Phase1-7 all completed successfully.

Phase 9's chosen multi-branch legacy-reopen strategy remains Option B: safely
block the lossy legacy reopen and direct the user to Saved Target Groups or
Campaign Planner.

## Application and schema baseline

| Item | Value | Authority |
|---|---:|---|
| Application version | `0.1.0` | `app/config.py`, `app_metadata` |
| SQLite schema version | `14` | `app/database/schema.py`, `app_metadata` |
| Runtime database | `data/campaign_poc.db` | default configuration |
| Runtime database bytes | `3,951,042,560` | filesystem inventory |

The database was inspected through SQLite read-only URI mode. No schema
initialization, migration, import, training, scoring, or rank rebuild was run.

## Frozen contract versions

| Contract or policy | Version |
|---|---:|
| Feature contract | `1` |
| Model-role policy | `2` |
| Evaluation contract | `2` |
| Audience Filter contract | `1` |
| Audience Rank contract | `1` |
| Audience Selection contract | `1` |
| Audience Analytics contract | `1` |
| Campaign contract | `1` |
| Campaign export contract | `1` |
| Campaign member-resolution contract | `1` |
| Campaign export-snapshot contract | `1` |
| Campaign targeting-context contract | `1` |
| Targeting-segment contract | `1` |
| Business match-strength contract | `1` |
| Age-bucket contract | `1` |
| Income-group contract | `1` |
| Targeting-intelligence resolution contract | `1` |
| Target Group preview contract | `1` |
| Target Group/Campaign contract | `1` |
| Saved Target Group contract | `1` |
| Match-strength recommendation contract | `1` |
| Match-strength recommendation rule | `1` |

## Canonical data imports and counts

The current published tables reconcile exactly to their latest completed import
records.

| Dataset | Import ID | Rows read/inserted/rejected | Canonical source checksum |
|---|---:|---:|---|
| Customers | 1 | 125,000 / 125,000 / 0 | `99a09d2f0db06980afe290cf74a4db1df76cf8c340534fb2088879fb093d9ea9` |
| Campaign sales | 2 | 570,000 / 570,000 / 0 | `2fdb11c576a180b7349e50e0bf9d3b0a66d0d354ba8d42062756c8cd840965c4` |
| Demographics | 3 | 5,000,000 / 5,000,000 / 0 | `e12fa5f54606aee0e6704db418f2054df29f4e1b8827d82ed2ce7897b7693e75` |

Current table counts:

| Table | Rows |
|---|---:|
| `customers` | 125,000 |
| `campaign_sales` | 570,000 |
| `demographics` | 5,000,000 |
| `historical_analysis_runs` | 2 |
| `model_runs` | 2 |
| `scoring_runs` | 2 |
| `propensity_scores` | 10,000,000 |
| `audience_rank_boundaries` | 200 |
| `audience_analytics_snapshots` | 2 |
| `saved_audiences` | 3 |
| `phase9_saved_target_groups` | 2 |
| `campaigns` | 4 |
| `jobs` | 7 |

## Existing analytical lineage

No run below is selected because it is latest. Each chain is recorded by exact
identity and verified provenance.

| Chain | Analysis | Model | Scoring | Full population | Rank/analytics readiness |
|---|---|---|---|---:|---|
| A | Run 2, `ANY_PURCHASE`, Email/CMP0001/PRD008; 11,662 customers, 1,297 positive | Run 1, `BAGGING_PU`, artifact `3c5a8e083acaaf86aab03cc44000f0247789ff837d4efdac8cc6c1f7b1ff0a19` | Run 1, completed | 5,000,000 | 100 v1 boundaries; v1 analytics; canonical and source-verified |
| B | Run 1, `ANY_PURCHASE`, all products/channels/types/categories; 119,748 customers, 35,416 positive | Run 2, `BAGGING_PU`, artifact `cd50dc7a39bf1288478072f01d98216a4fb64187a8085c2752ad637fa82f01f6` | Run 2, completed | 5,000,000 | 100 v1 boundaries; v1 analytics; canonical and source-verified |

Both artifact files exist and their computed SHA-256 values match their model
and scoring metadata. Both scoring runs match customer import 1, campaign-sales
import 2, demographic import 3, feature contract v1/SHA-256
`a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`,
and model-role policy v2.

Lightweight currentness results for scoring runs 1 and 2 are independently:

- status `COMPLETED`;
- `is_canonical=true` for their respective model;
- `demographic_source_verified=true`;
- `historical_source_verified=true`;
- no currentness issues;
- `ready_for_current_audience_actions=true`;
- no active compute job.

The Phase 9 browser-certified explicitly linked source is analysis 1 -> model 2
-> scoring 2. Phase 10 must nevertheless resolve reuse by exact future Modeling
Context compatibility, not by treating run 2 as a global latest winner.

## Do-not-change inventory

### Feature boundary

Authority: `app/ml/feature_contract.py`.

- Version/SHA-256: `1` /
  `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`.
- Exact ordered features: `age`, `gender`, `state`,
  `individual_yearly_income`, `marital_status`, `education`,
  `employment_status`, `resident_status`, `resident_type`,
  `family_member_count`, `type_of_employment`.
- Numeric features: age, individual yearly income, family-member count.
- Remaining eight fields are categorical; null/blank maps to `Unknown/Other`,
  surrounding whitespace is trimmed, fuzzy matching is disabled, and unseen
  categories are ignored by encoding.
- Preprocessing is fitted only on training data: numeric coercion/finite checks,
  median imputation and standard scaling; categorical canonical normalization
  and one-hot encoding; all remainder columns are dropped.
- Internal cohort-only fields are `customer_id` and `pu_label`; identifiers,
  contact PII, campaign behavior, product behavior, targeting preferences, and
  other demographic attributes are not model features.

### PU model governance and evaluation

Authorities: `app/ml/model_roles.py`, `app/ml/pu_estimators.py`, and
`app/ml/evaluation.py`.

- `BAGGING_PU` is the mandatory `PRIMARY` and the only candidate eligible for
  official selection.
- `ELKAN_NOTO_LOGISTIC` is `CHALLENGER_1`; it remains advisory even when it
  outperforms the primary.
- `NAIVE_PU_LABEL_BASELINE` is `DIAGNOSTIC_CONTROL` and is never selectable.
- Selection policy is `PRIMARY_ROLE_GOVERNED`; no metric-based auto-promotion.
- Labels mean known positive (`1`) versus unlabeled (`0`), never confirmed
  positive versus confirmed negative.
- Evaluation metrics are observed-label diagnostics with the persisted
  disclaimer. A non-fitted/non-genuine/constant-score primary is a hard stop.
- Deterministic default split/training seed remains 42 and validation fraction
  remains 0.20 unless an explicit governed request supplies compatible values.

### Historical cohort and label semantics

Authorities: `app/schemas/historical.py`,
`app/repositories/historical_repository.py`, and
`app/services/training_cohort_service.py`.

- Existing normalized filters are campaign IDs, product IDs, product
  categories, historical campaign channels, campaign types, inclusive contact
  dates, `contacted_only`, and conversion definition.
- Existing conversions are `ATTRIBUTED_PURCHASE` (attributed flag and purchase),
  `ANY_PURCHASE` (purchase), and `RESPONSE` (response).
- Customer grain is authoritative: within matching observations, `MAX` of the
  governed conversion expression makes a customer positive. Thus any matching
  positive observation produces `pu_label=1`; all other selected customers are
  unlabeled.
- Training reconstruction requires a completed saved analysis, exact current
  customer/campaign provenance, the saved inclusive historical window, one row
  per customer, the exact raw feature boundary, and full count reconciliation.
- Historical saved-run results remain aggregate-only and explicitly reject
  forbidden identifiers/contact fields.

### Score semantics

Authorities: `app/services/prospect_scoring_service.py` and
`app/services/audience_query_service.py`.

- A new production scoring run covers the complete current canonical prospect
  universe; sampling is permitted only for bounded verification, never as the
  published score population.
- Scoring is bounded keyset traversal by `person_id`, default chunk size 25,000,
  with source snapshot/provenance captured before work and reconciled after it.
- Scores must be finite in `[0,1]`; higher is better.
- Stable global order is `propensity_score DESC, person_id ASC`.
- Scores are relative propensity ranks for the current scored universe, not a
  guarantee, causal explanation, or cross-context absolute truth.
- Completion requires exact row-count/min/max endpoint reconciliation, stable
  demographic provenance, score aggregates, feature-contract identity, model
  artifact identity, model role, and historical lineage.

### Rank and selection semantics

Authorities: `app/services/audience_preparation_service.py` and
`app/services/audience_query_service.py`.

- Rank contract v1 persists exactly 100 percentile boundaries.
- Boundary target rank for percentile P is `max(1, ceil(N * P / 100))`.
- Ties use ascending `person_id`, preserving the global deterministic order.
- Decile is `((percentile_bucket - 1) // 10) + 1`.
- Rank bands are ELITE 1, VERY_HIGH 2-5, HIGH 6-10, MEDIUM 11-25,
  LOW 26-50, and VERY_LOW 51-100.
- Top P includes every row ranked at or above the persisted P boundary under
  the score/person tie-break contract.
- Selection modes remain `ALL_MATCHING` and deterministic `TOP_N`; TOP_N uses
  the same score-descending/person-ascending order.
- Audience actions require completed canonical scoring, exact source
  provenance, 100 compatible boundaries, and a compatible current analytics
  snapshot.

### Campaign, export, and privacy contracts

Authorities: `app/services/campaign_contracts.py`,
`app/services/campaign_service.py`, and `app/services/saved_audience_service.py`.

- Campaign state remains DRAFT or FINALIZED; channels remain EMAIL and
  DIRECT_MAIL.
- Campaigns bind immutable saved-audience identity, exact resolved count,
  filter definition/hash, selection, scoring/model/analysis lineage, contract
  versions, and source checksums.
- Export is allowed only through governed campaign profiles. Email v1 contains
  base rank fields plus first name, last name, email. Direct Mail v1 contains
  base rank fields plus the governed postal contact columns.
- Contact PII is excluded from planning, analytics, saved-audience detail, and
  preview APIs; it is resolved only at governed export time.
- `customer_id` is prohibited from export, and there is no
  customer-ID/person-ID identity bridge.
- Export snapshots and start provenance are checked so source drift cannot
  silently produce an accepted export.

### Phase 9 business buckets and match strengths

Authority: `app/schemas/campaign_targeting.py`.

- Match strength is cumulative by minimum score: VERY_STRONG >= 0.90, STRONG
  >= 0.80, GOOD >= 0.70, BROAD >= 0.60. Default remains GOOD.
- Age buckets are inclusive and fixed: 18-24, 25-34, 35-44, 45-54, 55-64,
  65-74, and 75-100.
- Income groups are inclusive and fixed: 0-24,999; 25,000-49,999;
  50,000-74,999; 75,000-99,999; 100,000-149,999; 150,000-249,999; and
  250,000+.
- Demographic targeting and Match Strength map to post-score Audience Filter
  contract branches. They are not training features or modeling-context keys.

### Immutable multi-branch save and reopen

Authorities: `app/services/target_group_preview_service.py`,
`app/services/target_group_campaign_service.py`,
`app/services/saved_audience_service.py`, and
`app/services/campaign_service.py`.

- Phase 9 branches are normalized and canonically SHA-256 hashed as the complete
  ordered list; the first branch is not the definition.
- Branch membership is an exact SQL union with a unique `person_id` index and
  `INSERT OR IGNORE`, so overlapping branches are de-duplicated.
- TOP_N is applied only after the union, using the canonical score/person order.
- Saved Target Group metadata preserves full branches, hash, normalized campaign
  context/hash, targeting criteria/hash, exact source scoring run, exact count,
  versions, and immutable Saved Audience linkage.
- Campaign export reloads and normalizes every branch, verifies the canonical
  branch hash and resolved count, then resolves the exact union membership.
- Legacy Saved Audiences and one-branch Phase 9 groups may reopen in Audience
  Explorer. Multi-branch Phase 9 groups are blocked before filter population and
  redirected to the Phase 9 flows. Invalid, empty, non-list, or unreadable branch
  metadata also fails closed. No branch-one fallback is allowed.

## Callable architecture inventory

### Historical Analysis and cohort reconstruction

| Callable | Role | Execution boundary |
|---|---|---|
| `create_historical_analysis(path, value)` | Normalize filters, capture provenance, persist RUNNING, execute aggregate cohort analysis, reconcile provenance, persist COMPLETED/FAILED | Synchronous; does not submit to ProcessPool |
| `get_historical_analysis_run(path, analysis_run_id)` | Validate and reopen the complete persisted analysis snapshot | Synchronous/read path |
| `list_historical_analysis_runs(path, limit, offset)` | List bounded saved-run summaries | Synchronous/read path |
| `HistoricalRepository.analyze_cohort(filters)` | Execute authoritative bounded aggregate SQL | Synchronous core |
| `HistoricalRepository.insert_analysis_run`, `complete_analysis_run`, `fail_analysis_run` | Persist analysis lifecycle | Synchronous repository writes |
| `reconstruct_training_cohort(path, analysis_run_id)` | Reopen completed analysis, verify current provenance, reconstruct exact customer-grain PU cohort, reconcile counts | Synchronous core; safe inside a parent worker |
| `ModelTrainingRepository.reconstruct_customer_rows(...)` | Execute the authoritative reconstruction query | Synchronous core |

Existing API entry points are `POST /api/historical/analyses`,
`GET /api/historical/analyses`, and
`GET /api/historical/analyses/{analysis_run_id}`. Historical creation is
currently synchronous and is not a persisted background job.

### Model creation and training

| Callable | Role | Execution boundary |
|---|---|---|
| `ModelRunRepository.create_run(...)` | Create a RUNNING model-run record bound to an analysis | Synchronous repository write |
| `train_and_persist_model(...)` | Reconstruct, split, preprocess, train/evaluate governed candidates, atomically persist and verify artifact, complete/fail model run | Synchronous heavy core; safe to call directly inside one parent worker |
| `run_model_training_job(path, job_id)` | Consume one persisted queued MODEL_TRAINING job, call the synchronous core, persist progress/result/failure | Top-level worker target; does not itself submit |
| `submit_model_training_job_request(...)` | Validate analysis, create persistent job, then submit it | **ProcessPool-submitting wrapper; unsafe inside a parent worker** |
| `submit_model_training_job(path, job_id)` | Submit `run_model_training_job` to shared executor | **Direct ProcessPool submit; unsafe inside a parent worker** |

The public API is `POST /api/models/train`; it returns a durable job accepted
response. Model status/detail is persisted rather than held in browser memory.

### Scoring creation and execution

| Callable | Role | Execution boundary |
|---|---|---|
| `ScoringRepository.create_scoring_run(...)` | Create RUNNING scoring metadata bound to job, model, source snapshot, feature/artifact identity | Synchronous repository write |
| `run_chunked_prospect_scoring(...)` | Validate model, capture full prospect snapshot, create run, keyset-score all prospects, reconcile/publish or fail | Synchronous heavy core; safe to call directly inside one parent worker |
| `run_prospect_scoring_job(path, job_id)` | Consume one queued PROSPECT_SCORING job, call synchronous core, persist progress/result/failure | Top-level worker target; does not itself submit |
| `submit_prospect_scoring_job_request(...)` | Validate model/current state, create persistent job, then submit it | **ProcessPool-submitting wrapper; unsafe inside a parent worker** |
| `submit_prospect_scoring_job(path, job_id)` | Submit `run_prospect_scoring_job` to shared executor | **Direct ProcessPool submit; unsafe inside a parent worker** |

The public API is `POST /api/models/{model_run_id}/score`.

### Rank and analytics preparation

| Callable | Role | Execution boundary |
|---|---|---|
| `run_audience_rank_preparation(...)` | Validate canonical scoring, build/verify 100 boundaries and analytics snapshot, or return idempotently when already ready | Synchronous heavy core; safe to call directly inside one parent worker |
| `run_audience_preparation_job(path, job_id)` | Consume one queued AUDIENCE_PREPARATION job and persist lifecycle around the synchronous core | Top-level worker target; does not itself submit |
| `submit_audience_preparation_job_request(...)` | Validate run, create persistent job, then submit it | **ProcessPool-submitting wrapper; unsafe inside a parent worker** |
| `submit_audience_preparation_job(path, job_id)` | Submit `run_audience_preparation_job` to shared executor | **Direct ProcessPool submit; unsafe inside a parent worker** |
| `AudienceRankRepository.replace_boundaries/fetch_boundaries` | Persist/read exact percentile boundaries | Synchronous repository operations |
| `AudienceAnalyticsSnapshotRepository.upsert_snapshot/fetch_snapshot` | Persist/read provenance-bound analytics | Synchronous repository operations |

The public API is `POST /api/audience/runs/{scoring_run_id}/prepare`; readiness
is exposed at `GET /api/audience/runs/{scoring_run_id}/preparation-status`.

### Currentness and compatibility callables

| Callable | Purpose |
|---|---|
| `resolve_current_historical_source_provenance(...)` | Resolve exact current customer and campaign-sales imports/checksums/counts |
| `is_saved_analysis_provenance_current(...)` | Compare saved analysis provenance with current published sources |
| `validate_scoreable_model(...)` | Verify completed governed primary, exact feature contract, lineage and artifact checksum/loadability |
| `find_current_canonical_run_for_model_lightweight(...)` | Find a compatible completed scoring run for one exact model using metadata/provenance checks |
| `resolve_current_scoring_context_lightweight(...)` | Validate one exact scoring run without scanning all score rows |
| `validate_completed_scoring_run_provenance_lightweight(...)` | Lightweight metadata/source verification for one run |
| `validate_completed_scoring_run_integrity_deep(...)` | Explicit deep aggregate/integrity scan; not for normal interactive reads |
| `validate_audience_analytics_snapshot_currentness(...)` | Verify analytics identity against scoring/model/analysis/import/contract provenance |
| `get_audience_preparation_status(...)` | Combine boundaries, analytics, canonicality and source verification into readiness |
| `validate_saved_audience_currentness(...)` | Verify immutable saved-audience lineage, hashes, contracts, and boundaries |
| `resolve_targeting_intelligence(...)` | Resolve Phase 9 explicit source status; never silently substitute a latest run |

### Persistent jobs and recovery

`JobRepository` is the durable lifecycle authority. It provides
`create_training_job`, `create_scoring_job`, `create_audience_preparation_job`,
`fetch_job`, active-job lookup, `mark_running`, `update_progress`,
`mark_completed`, `mark_failed`, and `fail_stale_active_jobs`. Jobs persist type,
status, progress, stage, safe message, analysis/model linkage, canonical request
and result JSON, timestamps, and bounded internal failure detail.

`reconcile_stale_model_training_jobs(...)` is the existing startup recovery
hook. It marks stale active compute jobs failed and also fails stranded RUNNING
scoring runs. The shared executor is lazy, bounded, and configured as:

`ProcessPoolExecutor(max_workers=1)`

## Mandatory nested-executor rule for Phase 10

A Phase 10 parent orchestration job running in the shared worker process must
never call and wait on any of these submission paths:

- `submit_model_training_job_request` / `submit_model_training_job`;
- `submit_prospect_scoring_job_request` / `submit_prospect_scoring_job`;
- `submit_audience_preparation_job_request` /
  `submit_audience_preparation_job`.

With one worker, the child cannot start while the parent occupies the only
process, so submit-and-block would deadlock. A parent worker must call the
appropriate synchronous core directly:

1. `create_historical_analysis` when a compatible analysis does not exist;
2. `train_and_persist_model` when a compatible model does not exist;
3. `run_chunked_prospect_scoring` when compatible full-universe scores do not
   exist;
4. `run_audience_rank_preparation` when compatible rank/analytics state does
   not exist.

The parent orchestration layer must own its durable job state, stage progress,
restart/recovery semantics, and exact created/reused IDs. It must never infer a
result by reading the newest row.

## Phase 10 handoff constraints

- Full Phase 9 Campaign Context remains a business object. Phase 10 must add a
  separate Modeling Context and must not silently equate the two.
- Delivery channel, campaign details, Match Strength, demographic targeting,
  TOP_N/top percentage, and Target Group name/description are excluded from
  analytical compatibility identity.
- Modeling-context compatibility must include the governed analytical fields
  and policies defined by subsequent Phase 10 contract steps.
- Reuse requires exact identity, current source provenance, compatible contract
  versions, complete state, and verified artifacts/counts. Recency alone is not
  evidence of compatibility.
- Phase 1-9 behavior recorded above is frozen unless a later Phase 10 prompt
  explicitly requires an additive, backward-compatible change.

## Execution declaration

- Phase 10 feature implementation: not started.
- Database migration: not run.
- Data import: not run.
- Model training: not run.
- Prospect scoring: not run.
- Rank/analytics rebuilding: not run.
- Existing application/data mutations: none.
- Required Step 1 evidence: created.

`STOP_AFTER_STEP_01`
