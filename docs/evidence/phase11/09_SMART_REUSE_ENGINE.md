# Phase 11 Step 9 — exact-result cache and smart-reuse engine

Date: 2026-09-17  
Baseline preserved: `881b5a652e869af1415547de452b9cccd2c18293`

## Outcome

`app/services/phase11_search_orchestration_service.py` now owns the three-layer search decision without duplicating Phase 10 compatibility logic:

1. reopen and verify the immutable canonical Phase 9 criteria and filter-branch JSON/checksums;
2. ask the frozen Phase 10 API service for current exact readiness;
3. ask Phase 10 preparation to reuse/build only when no exact READY binding exists;
4. persist `PROCESSING` while a durable Phase 10 parent remains `QUEUED`/`RUNNING`;
5. calculate an exact result-cache key only after verified READY lineage is available;
6. validate an exact snapshot hit with metadata, currentness, file, checksum, schema and row count;
7. on a miss, stream the exact Audience Engine membership into the Step 11 publisher boundary;
8. revalidate the published snapshot before completing the search run.

The service exposes a bounded `resume_phase11_searches` poll/resume operation for `QUEUED` and `PROCESSING` search rows. State lives in SQLite rather than a request/session object, so a Phase 10 wait survives navigation and process restart. `BLOCKED`/`FAILED` Phase 10 outcomes produce terminal search states with registry-owned safe messages.

## Phase 10 ownership

Currentness and compatibility are delegated to:

- `get_phase10_preparation` for exact current readiness;
- `prepare_phase10_targeting_intelligence` for the Phase 10 reuse/build decision;
- `Phase10IntelligenceRepository.verify_generation_record` for immutable READY lineage validation.

Step 9 does not reproduce historical-window, source-provenance, training eligibility, model compatibility, scoring compatibility, rank readiness or lifecycle classification rules. The verified Phase 10 response supplies the generation, analysis, model and scoring lineage plus its persisted `REUSE`/`BUILD` plan.

Result source is assigned as follows:

- `EXACT_RESULT_REUSE` only after a validated snapshot hit;
- `INTELLIGENCE_REUSE` when every Phase 10 layer is reused and a new/repair membership publication is required;
- `NEW_INTELLIGENCE_BUILD` when the exact Phase 10 orchestration plan contains any `BUILD` decision.

## Exact cache identity

The canonical SHA-256 cache key includes:

- cache-key contract version;
- verified generation ID;
- a generation fingerprint covering immutable intelligence/currentness lineage, source checksums, model artifact, scoring and policy/contract versions;
- targeting-criteria SHA;
- filter-branch SHA;
- selection mode and target count;
- audience filter, selection and rank contract versions;
- result-membership contract version.

Campaign name, description, launch date, delivery channel and export profile are deliberately absent. Tests prove that changing only delivery/profile keeps the key, while criteria, branches, selection or generation/source lineage changes it.

## Exact hit validation

An exact cache candidate is reusable only when all checks pass:

- Phase 10 still reports a READY generation current for the request;
- generation ID/fingerprint and Modeling Context match;
- criteria and branch hashes match;
- selection mode/target count match;
- result-membership contract matches;
- registry currentness is `CURRENT`;
- generation remains `READY` in a reusable lifecycle;
- the portable artifact path resolves inside the configured project root and exists;
- the stored file checksum matches;
- CSV/JSONL membership schema is exact and its row count equals `resolved_count`;
- optional Parquet verification uses metadata only when `pyarrow` is available.

Validation streams artifact bytes with bounded memory. It never queries or counts `propensity_scores`. A missing, corrupt, wrong-schema or wrong-count artifact is not an exact hit; the row is marked `STALE` and handed to the deterministic publisher boundary for repair. The repaired artifact is revalidated before reuse/completion.

## Audience Engine filtering

Each stored Phase 9 branch represents exact AND-across-field predicates; the stored branch list represents OR across disjoint age/income branches. Step 9 calls the existing `search_audience` service for each branch and performs a bounded k-way merge:

- maximum 49 live branch iterators, matching the persisted registry limit;
- 100-row keyset pages;
- global `propensity_score DESC, person_id ASC` ordering;
- adjacent identity de-duplication for defensively handling externally seeded overlap without a population-sized set;
- early stop when `TOP_N` is satisfied;
- only `person_id`, `propensity_score`, `percentile_bucket`, `decile` and `rank_band` cross the materializer boundary.

There is no Cartesian-product/permutation precompute and no delivery/contact PII in the cache decision or membership stream.

## Step 11 composition boundary

Step 9 supplies the exact membership stream and all reuse decisions. Step 11 owns atomic membership-file publication, manifest/storage policy and final production materializer composition. Until that publisher exists:

- a READY cache miss remains durably `PROCESSING` with `waiting_on=RESULT_MATERIALIZER`;
- no fake snapshot or completed count is created;
- the Step 8 public submission executor remains disabled, so the business UI truthfully reports the workflow as not yet connected.

Tests use a deterministic temporary CSV-GZIP publisher solely to exercise all Step 9 decision paths. This is not a claim that Step 11 production publication is implemented.

## Verification

Focused engine suite:

```text
.venv/Scripts/python.exe -m pytest tests/test_phase11_smart_reuse_engine.py -q
19 passed in 22.43s
```

Covered cases include:

- exact canonical key and generation fingerprint;
- profile-only exact reuse with a distinct second search history row;
- changed demographic filters using the same intelligence without training/scoring writes;
- durable Phase 10 waiting followed by `NEW_INTELLIGENCE_BUILD` completion;
- exact-hit membership-scan prohibition;
- cache rejection for every required metadata mismatch;
- stale generation rejection;
- missing/corrupt/count-mismatched artifact repair and revalidation;
- Audience Engine paged OR-branch merge, ordering, overlap de-duplication and `TOP_N` stopping;
- absent Step 11 materializer producing no fake result;
- safe terminal handling with no persisted collaborator exception text;
- canonical persisted criteria/branch identity reopening.

Combined Phase 11 registry/submission regression:

```text
.venv/Scripts/python.exe -m pytest \
  tests/test_phase11_smart_reuse_engine.py \
  tests/test_phase11_search_result_registry.py \
  tests/test_phase11_business_search_form.py -m "not browser" -q
107 passed, 17 deselected in 123.92s
```

Frozen Phase 10 compatibility/orchestration regression:

```text
.venv/Scripts/python.exe -m pytest \
  tests/test_phase10_context_identity.py \
  tests/test_phase10_schema_registry_repository.py \
  tests/test_phase10_orchestration_service.py \
  tests/test_phase10_api_bridge.py \
  tests/test_phase10_lifecycle_retention.py -q
51 passed in 169.88s
```

Audience Engine and Phase 9 targeting regression:

```text
.venv/Scripts/python.exe -m pytest \
  tests/test_audience_query_service.py \
  tests/test_phase9_targeting_contracts.py \
  tests/test_phase9_business_targeting.py -q
24 passed in 70.70s
```

All fixtures use tiny temporary SQLite databases and temporary result artifacts.

## No-heavy-work statement and stop

No canonical generation, import, historical analysis, training, scoring, rank preparation, 5M filtering, snapshot publication, export or activation was run. No worker/executor or application server was started.

Earlier uncommitted Phase 11 changes remain preserved. No staging, commit, push or freeze was performed.

`STOP_AFTER_STEP_09`

Step 10 and subsequent prompts have not started.
