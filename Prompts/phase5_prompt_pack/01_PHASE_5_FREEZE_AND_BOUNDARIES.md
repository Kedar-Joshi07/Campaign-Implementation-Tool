# Phase 5 Freeze, Scope, Architecture, and Boundaries

## Authoritative baseline

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Required starting HEAD: `fdae4a7a40c846e4038a8ebe656257eb4164cd5d`

Before editing:

```text
git rev-parse HEAD
git status --short
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
python scripts/validate_data.py --json
```

Expected evidence includes schema v4, healthy 125K customers / 570K campaign rows / 5M demographics, and at least one verified role-policy-v2 `BAGGING_PU` model. `model_run_id=7` is evidence only and must never be hard-coded.

## Frozen model governance

Phase 5 POC scores only:

```text
status = COMPLETED
PRIMARY = BAGGING_PU + Logistic Regression
model_role_policy_version = 2
evaluation_contract_version = 2
selection_policy = PRIMARY_ROLE_GOVERNED
selected_candidate = BAGGING_PU
```

Do not score legacy role-policy-v1, Elkan-selected, Naive diagnostic, RUNNING/FAILED, incompatible, or unverifiable models.

## Frozen 11-feature contract

```text
age
gender
state
individual_yearly_income
marital_status
education
employment_status
resident_status
resident_type
family_member_count
type_of_employment
```

```text
feature contract version = 1
SHA256 = a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535
```

No additions, deletions, or silent substitutes.

## Identity boundary

```text
Historical identity = customer_id
Prospect identity   = person_id
customer_id != person_id
```

No name/address/email/phone/postal/fuzzy/household linkage.

## Scoring read boundary

Read only:

```text
person_id + exact 11 features
```

Never read for scoring:

```text
first_name, last_name, address*, street, postal_code, city,
phone_number, email, ethnicity, religion, occupation_industry,
family_yearly_income, children/adult counts, country
```

## Architecture

```text
POST /api/models/{model_run_id}/score
→ persistent PROSPECT_SCORING job
→ shared bounded ProcessPoolExecutor(max_workers=1)
→ scoring worker
→ verify model/artifact/feature contract
→ create scoring_run
→ keyset-read prospect chunks
→ validate/normalize exact raw features
→ persisted preprocessor.transform()
→ persisted BAGGING_PU predict_proba
→ validate finite [0,1]
→ transactional chunk inserts
→ propensity_scores
→ exact population reconciliation
→ scoring_run COMPLETED
→ job COMPLETED
```

No synchronous 5M scoring in HTTP.

## Schema

Phase 5 schema = v5.

Add:

```text
scoring_runs
propensity_scores
```

Extend/rebuild `jobs` to support:

```text
MODEL_TRAINING
PROSPECT_SCORING
```

## Heavy-job policy

At most one active `QUEUED/RUNNING` heavy job across training and scoring. Do not allow training+scoring or scoring+scoring concurrently. No unbounded queue.

## Chunking

Never load all 5M into pandas.

Required scoring pagination:

```sql
WHERE person_id > ?
ORDER BY person_id
LIMIT ?
```

No `OFFSET` in the scoring loop.

Recommended internal default chunk size: `25000` with internal safety bounds `1000..100000`. Do not expose it as a business/UI control.

## Persistence

`propensity_scores` stores only:

```text
scoring_run_id
model_run_id
person_id
propensity_score
```

No PII, feature vectors, raw features, explanations, row timestamps, percentile, band, rank.

## Score semantics

Call it **Look-alike Propensity Score** or **PU Propensity Score**. Higher means stronger learned affinity. For current Bagging scoring it must be finite and in `[0,1]`.

Do not say `0.92 = 92% purchase probability`.

## Score bands/percentiles

Explicitly deferred. Phase 5 stores raw scores plus a ranking index. Phase 6 freezes ranking/band/percentile semantics.

## UI

Add a `Prospect Scoring` section under Model Training with scoreability, universe count, job progress, count/min/mean/max/runtime/throughput. No person table. Audience Explorer remains disabled.

## Restart

Stale active jobs and RUNNING scoring runs become FAILED on startup. No automatic resume. Partial rows under FAILED scoring runs are never usable.

## Age assumption

Training age was historical-reference-date derived. Demographics provides age directly. For the synthetic POC, treat demographic age as compatible prospect snapshot age and enforce the 18–100 frozen contract. Document this approximation; do not fabricate DOB or arbitrary date adjustment.

## Non-goals

No Audience Explorer, individual scored-prospect API, filters, ranks/bands, audience persistence, campaign builder, export, activation, SHAP, calibration, automatic retraining, distributed queues.
