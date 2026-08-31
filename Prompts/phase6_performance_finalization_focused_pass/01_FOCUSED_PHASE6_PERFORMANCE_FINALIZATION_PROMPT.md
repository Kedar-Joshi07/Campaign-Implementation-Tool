# Focused Phase 6 Performance Finalization Pass Before Phase 7

Repository:
`https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`

Required starting HEAD:
`77398d91f126d47d021e7835581848d655701b3a`

## Objective

Phase 6 functionality is complete and correct.

This pass exists ONLY to fix one remaining Phase 7 blocker:

**interactive audience currentness/canonical validation is too expensive because it performs deep 5M score integrity scans on read paths.**

Real evidence at the starting SHA shows saved-audience currentness taking about:

```text
509 seconds
```

which is not acceptable for an interactive Phase 7 prerequisite.

The implementation must separate:

```text
LIGHTWEIGHT CURRENTNESS / READINESS VALIDATION
```

from:

```text
DEEP 5M SCORE-INTEGRITY VALIDATION
```

while preserving all Phase 1–6 governance.

---

# 0. NON-NEGOTIABLE SCOPE BOUNDARIES

Do NOT:

- regenerate customer data;
- regenerate campaign data;
- regenerate demographic data;
- retrain model 8;
- rerun Phase 5 5M scoring;
- change the exact 11-feature contract;
- change Feature Contract v1;
- change Model Role Policy v2;
- change Evaluation Contract v2;
- change BAGGING_PU governance;
- change score semantics;
- create a new 5M table;
- create audience member materialization;
- implement Campaign Builder;
- implement campaign persistence;
- implement CSV export;
- implement contact PII export;
- implement activation;
- start Phase 7.

This is a narrow Phase 6 performance finalization pass.

---

# 1. BASELINE GATE

Before any code changes:

```text
git rev-parse HEAD
git status --short
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
python scripts/validate_data.py --json
```

Required HEAD:

`77398d91f126d47d021e7835581848d655701b3a`

If unexplained local changes exist:

STOP.

Record:

- schema version;
- current canonical analysis_run_id;
- model_run_id;
- scoring_run_id;
- boundary count;
- saved audience count;
- current test count;
- current saved-audience currentness timing;
- current Audience Explorer readiness timing if measurable.

Create:

```text
docs/evidence/phase6_performance_finalization_baseline.json
```

Sanitized only:
- no PII;
- no person IDs;
- no absolute paths;
- no raw SQL;
- no tracebacks.

---

# 2. IDENTIFY ALL INTERACTIVE CURRENTNESS PATHS

Trace all service/API/UI paths that currently call deep scoring provenance validation.

At minimum inspect:

```text
validate_completed_scoring_run_provenance()
find_current_canonical_run_for_model()
_require_prepared_canonical_context()
_evaluate_saved_audience_currentness()
list_saved_audiences()
get_saved_audience_detail()
validate_saved_audience_currentness()
get_audience_preparation_status()
list_audience_preparation_runs()
get_audience_filter_options()
estimate_audience()
search_audience()
profile_audience()
save_audience()
```

Produce a call graph showing:

```text
interactive caller
→ currentness helper
→ deep validator
→ 5M aggregate scan(s)
```

Confirm whether duplicate deep validation occurs in one request.

---

# 3. CREATE TWO VALIDATION TIERS

## Tier A — Lightweight currentness validation

Create a new explicit lightweight currentness service/helper.

Suggested name:

```text
resolve_current_scoring_context_lightweight()
```

or equivalent.

It MUST NOT aggregate over all 5M propensity-score rows.

It should validate only persisted metadata and source provenance.

Required checks:

### Scoring run

```text
scoring_run exists
status = COMPLETED
model_run_id valid
scored_person_count > 0
scored_person_count = demographic_snapshot_count
selected_candidate = BAGGING_PU
feature_contract_version supported
feature_contract_sha256 valid/current
artifact_sha256 valid
```

### Model

```text
model exists
status = COMPLETED
analysis_run_id matches scoring provenance
selected model/governance valid
artifact SHA matches scoring metadata
feature contract matches scoring metadata
```

### Historical source

Compare:

```text
customer_import_id
customer_source_checksum
campaign_sales_import_id
campaign_sales_source_checksum
```

against current authoritative historical provenance.

### Demographic source

Compare:

```text
demographic_import_id
demographic_source_checksum
demographic_snapshot_count
demographic_min_person_id
demographic_max_person_id
```

against current authoritative demographic provenance.

### Current canonical scoring run

Determine whether this scoring run is the current canonical run for the model WITHOUT
performing a 5M aggregate scan.

If multiple completed runs exist:
- newest current-source matching valid run is canonical;
- stale runs remain historical.

### Rank readiness where needed

For Audience Explorer/saved audience use:

```text
boundary_count = 100
rank_contract_version supported
```

## Tier B — Deep integrity validation

Keep the existing deep validator or create a clearly named deep variant such as:

```text
validate_completed_scoring_run_integrity_deep()
```

This tier may continue to perform:

```text
COUNT(*)
COUNT(DISTINCT person_id)
MIN/MAX person_id
MIN/MAX/AVG score
```

over `propensity_scores`.

Deep validation is allowed only for explicit integrity/audit contexts such as:

- Phase 5 scoring completion;
- Phase 6 rank preparation submission/run;
- explicit acceptance/audit scripts;
- manual integrity verification;
- controlled export/activation verification in a later phase if explicitly required.

Deep validation MUST NOT run automatically on ordinary interactive reads.

---

# 4. REMOVE DUPLICATE DEEP VALIDATION

Audit:

```text
find_current_canonical_run_for_model()
```

If it currently deep-validates each completed scoring run, introduce a lightweight
canonical resolver.

Suggested:

```text
find_current_canonical_run_for_model_lightweight()
```

or refactor with clearly separate helper names.

Do not use a vague boolean argument if it makes safety intent hard to read.

The code should make it obvious whether a caller is doing:

```text
CURRENTNESS CHECK
```

or:

```text
FULL SCORE INTEGRITY AUDIT
```

---

# 5. APPLY LIGHTWEIGHT VALIDATION TO INTERACTIVE PHASE 6 PATHS

Use lightweight currentness validation in:

```text
GET /api/audience/runs
GET /api/audience/runs/{id}/preparation-status
GET /api/audience/options
POST /api/audience/estimate
POST /api/audience/search
POST /api/audience/profile
POST /api/audiences
GET /api/audiences
GET /api/audiences/{id}
saved-audience currentness validation
Audience Explorer readiness resolution
```

Do not reduce provenance guarantees.

The result must still detect:

- historical source drift;
- demographic source drift;
- model/artifact mismatch;
- unsupported feature contract;
- stale scoring run;
- incomplete/missing rank boundaries;
- unsupported rank/filter/selection contracts.

The only thing removed from interactive reads is repeated full 5M score-table integrity aggregation.

---

# 6. SAVED AUDIENCE CURRENTNESS PERFORMANCE FIX

This is the critical acceptance target.

Current behavior at the starting SHA is approximately:

```text
validate_saved_audience_currentness()
≈ 509 seconds
```

Refactor:

```text
_evaluate_saved_audience_currentness()
```

to use lightweight scoring currentness.

Avoid duplicate checks already implied by one authoritative lightweight context.

Saved-audience currentness must still verify:

```text
saved scoring_run_id
saved model_run_id
saved analysis_run_id
saved historical source provenance
saved demographic provenance
feature contract
artifact SHA
selection/filter/rank contract versions
100 rank boundaries
current canonical scoring run
```

No 5M score aggregate scan.

## Saved audience list

Current list behavior validates each row individually.

For a list of N saved audiences, avoid repeating the same scoring/model/source
currentness computation N times when rows share the same scoring run.

Implement request-scoped memoization/cache such as:

```text
scoring_run_id -> lightweight currentness result
analysis_run_id -> historical currentness result
```

No Redis.

No long-lived global stale cache required.

---

# 7. AUDIENCE EXPLORER CURRENTNESS PERFORMANCE FIX

Refactor:

```text
_require_prepared_canonical_context()
```

to use the lightweight validator.

The following interactive endpoints should become fast enough for normal UI use:

```text
options
estimate
search
profile
save audience
```

Search/profile SQL may still take time based on filters and aggregation, but
currentness validation itself must not add multi-minute overhead.

Preserve:

```text
prepared
is_canonical
source_verified
ready_for_current_audience_actions
currentness_issues
```

semantics.

---

# 8. DEEP VALIDATION SAFETY REGRESSION

Do not accidentally weaken completion/acceptance validation.

Verify deep validation remains active where required.

At minimum:

### Phase 5 completion
A completed scoring run must still reconcile exactly.

### Rank preparation
Before preparing 100 rank boundaries, require deep scoring integrity or equivalent
strong precondition so boundaries are never created from a corrupted score table.

### Explicit audit
The deep validator must remain available for acceptance/integrity audits.

---

# 9. FIX REAL PERFORMANCE EVIDENCE SCRIPT

Update:

```text
scripts/phase6_capture_real_5m_performance.py
```

to measure the REAL service layer.

Required timed calls:

```text
get_audience_filter_options()
estimate_audience()
search_audience()
profile_audience()
list_saved_audiences()
get_saved_audience_detail()
validate_saved_audience_currentness()
```

Optionally measure HTTP endpoints separately, but service timings are required.

The evidence must distinguish:

```text
service_timings
sql_query_timings
rank_preparation_metrics
```

Do not label raw COUNT queries as profile timing.

Do not call repository-only saved-audience methods and label them as service timing.

---

# 10. PERFORMANCE ACCEPTANCE TARGETS

This is a local SQLite POC, so do not create fake production SLAs.

However, interactive currentness must be practically usable.

### Saved audience currentness

Target:

```text
< 5 seconds
```

Preferred:

```text
< 1 second
```

on the current local POC environment after warm filesystem/cache state.

If still >5 seconds:
- profile remaining path;
- do not freeze Phase 7 baseline;
- report blocker.

### Saved audience list

Target:

```text
< 5 seconds total
```

Preferred:

```text
< 1 second
```

for the current small saved-audience count.

### Saved audience detail

Target:

```text
< 5 seconds
```

Preferred:

```text
< 1 second
```

### Audience preparation status/list

Must not scan 5M scores.

### Search / estimate / profile

Measure actual service timings.

Long profile aggregation may be acceptable for this POC, but currentness overhead
must be separately reported.

Do NOT optimize by weakening data/provenance correctness.

---

# 11. OPTIONAL SAFE CACHE

If lightweight metadata currentness still performs repeated source lookups inside
one request, add request-scoped or short-lived bounded reuse.

Allowed:

```text
request-local dict
small bounded in-process TTL cache
```

If using TTL:
- keep it short;
- key by database/source/scoring provenance;
- source ID/checksum changes must invalidate naturally;
- do not rely solely on stale cache for correctness.

Do not add Redis/Celery/external infrastructure.

---

# 12. TESTS

Add comprehensive tests.

## Lightweight vs deep

1. lightweight validation does NOT call `fetch_score_aggregates`.
2. lightweight canonical resolver does NOT scan propensity-score aggregates.
3. deep validator still detects row-count mismatch.
4. deep validator still detects duplicate score identities.
5. lightweight validator detects historical source drift.
6. lightweight validator detects demographic source drift.
7. lightweight validator detects artifact mismatch.
8. lightweight validator detects feature-contract mismatch.
9. lightweight validator rejects stale scoring run.
10. lightweight validator accepts current canonical run.

## Saved audiences

11. currentness uses lightweight validator.
12. list does not repeat identical scoring currentness work per audience.
13. stale historical source -> false.
14. stale demographic source -> false.
15. rank boundaries missing -> false.
16. unsupported contract version -> false.
17. current saved audience -> true.

## Audience Explorer

18. preparation status does not deep-scan.
19. run list does not deep-scan.
20. options does not deep-scan.
21. estimate does not deep-scan.
22. search does not deep-scan.
23. profile does not deep-scan.
24. save audience does not deep-scan.

## Deep gates retained

25. rank preparation still performs deep integrity verification before publishing boundaries.
26. scoring completion validation remains unchanged.
27. explicit deep audit still works.

## Regression

28. all Phase 1–6 tests green.
29. no Phase 7 API/schema/UI added.
30. no PII exposure.

---

# 13. REAL 5M SERVICE PERFORMANCE REVALIDATION

Run corrected service benchmarks against the canonical 5M DB.

Do NOT mutate canonical score rows.

Record:

## Currentness

```text
saved audience currentness
saved audience list
saved audience detail
audience preparation status
audience run list
```

## Audience Explorer services

```text
options
unfiltered first search page
next keyset page
state search
age+income search
top 1% search
estimate all
estimate top 1%
estimate top decile
profile top 1%
profile filtered TOP_N 50K
```

## Rank preparation

Use copied DB for clean preparation metrics.

Preserve:

```text
scanned_rows = 5,000,000
boundary_count = 100
```

Create:

```text
docs/evidence/phase6_real_5m_service_performance.json
```

No person IDs, PII, raw SQL, absolute paths, or tracebacks.

---

# 14. FINAL REGRESSION GATE

Run:

```text
python -m pip check
python -m pytest -q
python -m compileall -q app scripts tests
git diff --check
python scripts/validate_data.py --json
```

Then verify:

```text
git status --short
```

Canonical lineage should remain dynamically resolved and consistent with the current accepted chain.

Verify:

- Phase 5 deterministic re-score still passes;
- historical source current;
- demographic source current;
- score row count remains 5,000,000;
- 100 boundaries valid;
- saved validation audience current;
- no Phase 7 runtime implementation.

---

# 15. DOCUMENTATION / HANDOFF UPDATE

Update only Phase 6 technical docs/evidence:

```text
docs/PHASE_6_IMPLEMENTATION_SUMMARY.md
Prompts/phase6_prompt_pack/02_PROGRESS_TRACKER.md
Prompts/phase6_prompt_pack/03_ACCEPTANCE_CHECKLIST.md
Prompts/phase6_prompt_pack/04_PHASE_7_HANDOFF_CONTRACT.md
docs/evidence/phase6_real_5m_service_performance.json
```

Do NOT rewrite root README.

Document:

```text
Interactive currentness = lightweight metadata/provenance validation
Deep 5M score integrity = explicit audit/preparation/completion validation
```

---

# 16. COMMIT AND FREEZE

Create one focused commit, e.g.:

```text
perf: separate phase6 currentness from deep score integrity
```

After commit:

```text
git rev-parse HEAD
git status --short
```

The resulting SHA becomes the candidate Phase 7 starting baseline.

Do not self-embed the final SHA in the same commit.

---

# 17. FINAL REPORT

Return:

1. starting SHA `77398d91f126d47d021e7835581848d655701b3a`
2. final SHA
3. files changed
4. schema version
5. whether schema migration was required
6. lightweight validation helper name
7. deep validation helper name
8. interactive callers migrated
9. deep callers retained
10. duplicate deep-validation path removed
11. saved-audience currentness BEFORE
12. saved-audience currentness AFTER
13. saved-audience list timing
14. saved-audience detail timing
15. preparation-status timing
16. audience-run-list timing
17. options service timing
18. search first-page timing
19. search next-page timing
20. estimate timing
21. profile top-1% timing
22. filtered TOP_N 50K profile timing
23. rank-preparation runtime
24. rank-preparation rows/sec
25. rank-preparation scanned rows
26. boundary count
27. canonical analysis/model/scoring IDs
28. historical source verification
29. demographic source verification
30. deterministic Phase 5 re-score result
31. score row reconciliation
32. pytest result
33. pip check
34. compileall
35. diff check
36. validate_data result
37. no Phase 7 implementation confirmation
38. FINAL DECISION: GO / CONDITIONAL GO / NO-GO

---

# 18. FINAL GO RULE

GO for Phase 7 only if:

- saved-audience currentness no longer performs deep 5M score aggregation;
- Audience Explorer interactive currentness no longer performs deep 5M score aggregation;
- lightweight currentness detects source/model/artifact/contract drift;
- deep integrity remains available at explicit audit/preparation/completion boundaries;
- saved-audience currentness is practically interactive (<5 sec target);
- real SERVICE timings are captured;
- full tests pass;
- Phase 1–6 data/model/scoring state remains unchanged;
- no Phase 7 implementation has begun.

If currentness remains multi-minute:

```text
NO-GO — PHASE 7 BLOCKED
```

STOP after the final report.
