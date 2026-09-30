# Campaign Recovery Baseline and Invariants

Prompt executed: `Prompts/campaign_recovery_prompt_pack_f437efd3/00_MASTER_GUARDRAILS_AND_EXECUTION_ORDER.md`

This is a baseline and execution-control record only. It does not claim that any
recovery defect is fixed, does not alter runtime behavior, and does not certify a
release. All canonical-database queries used SQLite read-only URI mode and returned
only aggregate or lineage metadata; no customer or contact data was read into this
evidence.

## A. Verified baseline

| Item | Verified value |
|---|---|
| HEAD | `f437efd3be9e6d4945b0ee12bff91ccce2697088` |
| Branch | `main` |
| Working tree before Prompt 00 | Only the operator-supplied, untracked `Prompts/campaign_recovery_prompt_pack_f437efd3/` directory; no tracked modifications |
| Application version | `0.1.0` (`app/config.py`, and canonical `app_metadata`) |
| SQLite schema version | `21` (`app/database/schema.py::CURRENT_SCHEMA_VERSION`, and canonical `app_metadata`) |
| Canonical database | `data/campaign_poc.db` |
| Canonical database size | 7,574,577,152 bytes |
| Python | 3.12.0 |
| `requirements.lock` SHA-256 | `350439D9ACB3AFC8ED9E1ADC48DFAA8455ED81C53D3DEAA5248E36CEEB2401F1` |
| `requirements-browser.lock` SHA-256 | `A8EF32BD35A0280AC1324075C14C02BD16DD0702F7FC796ECC2D08309B956A03` |

### Exact-SHA CI

The public GitHub Actions metadata contains one completed `CI` run for the exact
HEAD, run ID `36409122639`, created 2026-09-28T10:20:28Z and concluded
**failure**. The exact-SHA run is:

`https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool/actions/runs/36409122639`

| Job | Conclusion | Failing step |
|---|---|---|
| Repository Hygiene | success | — |
| Python Validation | success | — |
| Tests | failure | Run unit and integration tests (excluding heavy classes) |
| Frontend Contract | failure | Run bounded Phase 11 contract, UI, cache, and profile tests |
| Clean-Room Phase1-7 | success | — |

The public jobs API exposes job and step conclusions but the unauthenticated job-log
download returned HTTP 403. Local focused reproduction below therefore provides the
test-level evidence that is available without changing the repository.

### Sanitized Phase 10/11 registry counts

| Table | Rows |
|---|---:|
| `phase10_context_bindings` | 24 |
| `phase10_intelligence_generations` | 3 |
| `phase10_orchestration_runs` | 24 |
| `campaign_search_runs` | 33 |
| `campaign_search_attempts` | 39 |
| `campaign_search_run_runtime` | 33 |
| `campaign_search_progress_events` | 56 |
| `campaign_search_future_lineage` | 33 |
| `campaign_result_snapshots` | 10 |
| `campaign_result_export_events` | 24 |
| `targeting_option_catalogs` | 1 |
| `targeting_product_catalog` | 36 |
| `intelligence_verification_attestations` | 1 |
| `score_calibration_artifacts` | 2 |
| `calibrated_propensity_scores` | 10,000,000 |
| `calibration_score_stage` | 0 |
| `calibration_distribution_bins` | 2 |
| `search_preflight_cache` | 21 |
| `campaign_feedback_batches` | 0 |
| `campaign_feedback_outcomes` | 0 |
| `feedback_retraining_decisions` | 0 |

Visible run status is 26 `COMPLETED`, 6 `BLOCKED`, and 1 `FAILED`. Attempt status
is 26 `COMPLETED`, 8 `BLOCKED`, and 5 `FAILED`. Basic relational checks found no
orphan attempts, no orphan progress events, no run missing its runtime row, no
current-attempt lookup mismatch, and no visible-run/runtime status mismatch.

All 33 saved runs use selection contract v1. Their 26 completed runs contain 46
selected members in total and at most 4 in one run. There are no accepted feedback
batches or retraining decisions.

The promoted calibration artifact is artifact 2 for scoring run 6. Each of the two
calibration artifacts contains 5,000,000 rows, but both have **zero** non-null
`propensity_bucket` values. Artifact 2 probabilities range from approximately
0.06518 to 0.07856. All 21 persisted preflight entries are recorded `CURRENT`, and
their exact intersection counts are all zero. The latest scoring generation's raw
score range is approximately 0.01596 to 0.55876.

The canonical registry has 39 attempts but 33 attempts have no corresponding
append-only progress event. Runtime rows exist, so this specifically demonstrates
the missing initial-history event rather than missing visible runtime state.

## B. Verified dependency graph

### Search submission through completion

```text
POST /api/potential-customer-search/runs
  -> potential_customer_search_submission_service.submit_potential_customer_search
     -> targeting_option_catalog_service.get_targeting_catalog / get_or_build_targeting_catalog
     -> normalize campaign context + criteria + v1/v2 selection identity
     -> one transaction: CampaignTargetingContextRepository.create_context
                         + CampaignResultRegistryRepository.create_search_run
     -> configured Phase11SearchCoordinator.submit
        -> bounded ThreadPoolExecutor reservation by search_run_id
        -> execute_phase11_search_safely
           -> validate persisted identity; QUEUED -> PROCESSING
           -> phase11_search_orchestration_service._phase10_state
              -> direct generation lookup + has_current_attestation, or
              -> phase10_api_service.get_phase10_preparation, then
              -> phase10_api_service.prepare_phase10_targeting_intelligence
           -> bind current attempt to generation/scoring/calibration lineage
           -> validate exact cached snapshot, or
           -> iter_selected_members + ResultSnapshotMaterializer
           -> validate immutable snapshot
           -> CampaignResultRegistryRepository.complete_search_run
```

The coordinator has two lightweight workers and repeatedly polls durable Phase 10
state. Phase 10 remains responsible for compatibility/reuse/build decisions. The
current global `_PHASE10_HEAVY_GATE` is entered before `_phase10_state`, including
its cheap direct-attested-reuse lookup.

### Retry and dependency ownership

```text
POST /api/potential-customer-search/runs/{id}/retry
  -> retry_potential_customer_search
     -> CampaignResultRegistryRepository.retry_search_run
        -> validate idempotency and retry eligibility
        -> terminalize a stale PROCESSING attempt when applicable
        -> append immutable next campaign_search_attempts row
        -> reset visible run/runtime to QUEUED
        -> append retry QUEUED progress event
     -> Phase11SearchCoordinator.submit
        -> execute_phase11_search_safely
           -> _phase10_state reads the existing Phase 10 dependency
```

`phase10_api_service.retry_phase10_targeting_intelligence` exists, but the Phase 11
retry path does not call it or persist explicit dependency ownership. A terminal
Phase 10 failure is consequently reread and can immediately terminalize the new
Phase 11 attempt. Attempts also have no owner token, lease expiry, or fencing token;
worker writes guard visible status but not the identity of the currently leased
attempt.

### Import, currentness, calibration, preflight, and reuse

```text
data_import_service.import_* / _import_dataset
  -> source-file SHA-256 + authoritative data_import_runs publication
  -> _refresh_targeting_catalog_after_import
     -> targeting_option_catalog_service.get_or_build_targeting_catalog

latest import IDs/checksums
  -> Phase 10 generation lineage/currentness
  -> intelligence_attestation_service._key
     -> generation ID + scoring run + stored generation source checksums
        + artifact SHA + schema version
  -> record_deep_verification_attestation
     -> scoring-run status and propensity-score row-count equality
  -> propensity_calibration_service.publish_fitted_calibration
     -> promoted score_calibration_artifacts
     -> calibrated_propensity_scores + five optional 0.50+ bucket labels
  -> potential_customer_preflight_service.exact_preflight_many
     -> modeling-context generation lookup
     -> latest promoted calibration lookup
     -> search_preflight_cache or exact demographic/bucket intersection count
  -> Phase 11 exact-result cache key / membership materialization / snapshot reuse
```

The current import completion path refreshes the catalog but does not transactionally
invalidate generations, attestations, calibrations, preflight cache entries, or
snapshots. Direct reuse accepts an attestation derived from the candidate generation's
stored source checksums; it does not compare those values with the latest authoritative
imports. Preflight similarly labels a result `CURRENT` after lifecycle/calibration
lookup without the full attestation and live-source gate used by the intended invariant.

### Feedback through challenger publication

```text
POST /api/potential-customer-search/runs/{id}/feedback
  -> phase11_feedback_service.parse_feedback_csv / JSON rows
  -> ingest_feedback
     -> validate immutable snapshot membership, duplicates, conflict,
        timestamp, idempotency, and payload checksum
     -> campaign_feedback_batches + campaign_feedback_outcomes
     -> _adaptive_gate
        -> >=1000 labels, >=100 positive, >=100 negative, >=2 runs, and
           (>=10% new labels or PSI >=0.20)
     -> feedback_retraining_decisions
     -> configured FeedbackRetrainingWorker.submit
        -> join feedback to existing raw propensity_scores
        -> fit_held_out_calibration (sigmoid versus isotonic)
        -> challenger_meets_promotion_gates
        -> publish_fitted_calibration
```

Despite its name, `FeedbackRetrainingWorker` does not train a new feature model or
publish a new model/scoring generation. It fits a new calibrator to the incumbent raw
scores. Its PSI baseline is the full calibrated population while its comparison sample
is feedback from already selected audiences, so cohort selection and drift are mixed.

## C. Frozen recovery invariants

These are normative requirements for every later prompt. A later implementation may
strengthen them but must not weaken them.

1. One visible `search_run_id` may have many immutable attempts.
2. Only the currently leased attempt may mutate visible run/runtime state.
3. Terminal attempts remain immutable.
4. Currentness must be proven against the latest authoritative imports, not merely
   against values stored on the candidate generation.
5. Direct reuse may bypass heavy validation only when a durable attestation covers the
   same immutable lineage **and** current authoritative source identity.
6. A retry of a dependency-owned failure must retry or rejoin the dependency, not
   immediately reproduce the same terminal state.
7. Preflight and actual materialization must use the same selection semantics and
   lineage.
8. V1 raw-score semantics and v2 calibrated-probability semantics must never be
   conflated.
9. No demo qualification rule may be silently weakened.
10. Evidence must be generated at the SHA it claims to certify.

### Baseline conformance snapshot

| Invariant | Baseline status | Reason |
|---|---|---|
| 1 | Partial | Multiple immutable attempt rows exist, but mutable ownership is incomplete. |
| 2 | Fail | No durable leases, owner IDs, expiries, or fencing tokens guard worker writes. |
| 3 | Partial | Normal retry appends a new attempt; comprehensive stale-worker mutation proof is absent. |
| 4 | Fail | direct reuse and preflight do not prove against all latest authoritative import identities. |
| 5 | Fail | attestation uses stored generation source identity and only a population-count check. |
| 6 | Fail | Phase 11 retry does not invoke/rejoin Phase 10 retry. |
| 7 | Not proven | Similar predicates exist, but currentness/cache identity and parity are not end-to-end certified. |
| 8 | Fail | v2 calibrated probability is projected under legacy `propensity_score`/membership-v1 semantics and Results still shows Match Strength. |
| 9 | Pass by inspection | The 10,000 demo threshold and five approved probability buckets are not silently lowered; current counts honestly remain zero. |
| 10 | Fail | README and prior evidence name older SHAs/test totals; exact current-SHA CI is red. |

## Known-audit-finding reconciliation

| Candidate finding | Result at this SHA | Evidence |
|---|---|---|
| Exact-SHA GitHub CI is red | Verified | Run `36409122639`; Tests and Frontend Contract fail. |
| API compatibility conflicts with additive v2 status fields | Reproduced | `test_create_get_status_and_history_share_one_safe_status_contract` fails because v1 projections now include selection, attempt, queue, progress, issue, and retry fields. |
| 390px Result Detail overflows | **Not reproduced in the isolated named case** | The installed-system-Chrome test at 390x844 passed locally. The broader CI job remains red and Prompt 01 must add/retain 360, 390, tablet, and desktop assertions before resolving this candidate. |
| Retry does not restart failed Phase 10 dependency | Verified by call-chain inspection | Phase 11 retry never calls `retry_phase10_targeting_intelligence`. |
| Attempt fencing/leases are absent | Verified | Attempt schema and mutable repository writes have no owner/lease/fencing columns or predicates. |
| “Deep” attestation is shallow | Verified | It checks scoring status and exact row count only. |
| Direct attested reuse may ignore latest imports | Verified | attestation key is derived from candidate-generation values; direct path does not load latest import identity. |
| Preflight can claim currentness without full gate | Verified | it selects lifecycle-ready generation/promoted calibration then writes/returns `CURRENT`. |
| Every approved calibrated bucket is empty | Verified in canonical data | 10,000,000 calibrated rows; zero bucketed rows; maximum promoted probability ~0.07856. |
| Feedback cannot bootstrap v2 audiences | Verified for current canonical state | v2 has no eligible members/results; all 33 runs are v1; only 46 legacy selected memberships exist versus the 1,000-label gate. |
| Heavy lock covers cheap direct reuse | Verified | `_PHASE10_HEAVY_GATE` wraps the entire `_phase10_state` call. |
| `processing_seconds` includes queue time | Verified | `started_at` is set on creation; completion/failure elapsed time uses that value rather than `processing_started_at`. |
| Phase 10 wait can heartbeat at 3% | Verified | 10-second heartbeat repeatedly records `CHECKING_INTELLIGENCE` at 3% until `_phase10_state` returns. |
| Initial append-only progress history can be missing | Verified | 33 of 39 attempts have no progress event, despite runtime rows being present. |
| ETA history is not workload-classified | Verified | `stage_duration_history` partitions only by stage; `workload_class` is stored but unused. |
| Retry uses `crypto.randomUUID()` without fallback | Verified | retry directly invokes it; feedback has a `getRandomValues` fallback helper. |
| Train/calibration/test campaign isolation is incomplete | Verified by lineage inspection | model train/validation uses a customer split; calibration later assigns each validation customer only its minimum campaign ID before a second grouped split, which does not prove campaign isolation from model training. |
| Feedback worker recalibrates instead of retraining model | Verified | it fits calibration against existing propensity scores and publishes only a calibration artifact. |
| PSI compares selected feedback to full 5M | Verified | base is `calibration_distribution_bins`; sample is feedback-member calibrated scores. |
| V2 overloads legacy score/membership semantics | Verified | calibrated probability is aliased as `propensity_score`; result membership contract remains v1. |
| V2 Results retain legacy Match Strength/raw score concepts | Verified | Results projection always returns `criteria.match_strength`; membership/score summary naming remains legacy. |
| Reused stale catalog may not be re-promoted | Verified | existing-version early return does not set `is_current=1`; normalization later rejects a non-current catalog. |
| README/evidence are stale | Verified | root README still reports schema 18, baseline `b00946d...`, CI #26, and 966 tests while code/database are schema 21 and exact current-SHA CI is red. |

## D. Prompt execution graph

The only authorized sequence is:

```text
01 -> 02 -> 03 -> 04 -> 05 -> 06 -> 07 -> 08 -> 09 -> 10 -> 11 -> 12 -> 13
                                                                      |
                                             explicit policy decision +
                                                   /             \
                                                14A               14B
                                                   \             /
                                                    15 -> 16 -> 17 -> 18 -> 19
```

| Prompt | Dependency and gate |
|---|---|
| 01 | Restore deterministic exact-SHA CI, coherent API versioning, browser-key fallback, and responsive UI before behavioral recovery work. |
| 02 | Add leases/fencing so all later retry, restart, and worker changes have safe mutation ownership. |
| 03 | Build dependency retry/rejoin on the fenced attempt model from 02. |
| 04 | Define genuinely deep attestation and authoritative-source currentness. |
| 05 | Propagate import invalidation through generation, attestation, calibration, preflight, and results using 04. |
| 06 | Make preflight cache identity and actual materialization exact under the currentness model from 04–05. |
| 07 | Move only safely attested direct reuse outside heavy work and correct timing after 04–06. |
| 08 | Propagate truthful Phase 10 stages, heartbeats, initial events, and workload-aware ETA on the fenced orchestration path. |
| 09 | Separate v1 raw-score and v2 calibrated-probability membership/API/UI semantics after parity is stable. |
| 10 | Correct catalog promotion/load lifecycle consistent with import invalidation and v2 form identity. |
| 11 | Establish true train/calibrate/test isolation and calibration governance. |
| 12 | Correct PSI and separate recalibration from actual feature-model learning, using 09 and 11 contracts. |
| 13 | Produce the required zero-customer root-cause and business-policy decision gate; do not choose policy silently. |
| 14A or 14B | Execute exactly one approved path: improve absolute-probability modeling, or add an explicitly approved versioned selection contract. |
| 15 | Run fault injection, retry/restart, concurrency, and crash recovery after the chosen policy path. |
| 16 | Run performance and canonical 5M certification only after correctness/recovery gates pass. |
| 17 | Run exact 20-scenario preflight and sequential real runs without widening or fabricated qualification. |
| 18 | Refresh documentation/evidence from the resulting exact SHA and remove stale claims. |
| 19 | Run full regression and exact-SHA CI, then issue the only final GO/NO-GO decision. |

Do not run 14A and 14B together. Prompt 13 must record the explicit policy decision
that selects the branch. Do not skip forward because later tests depend on ownership,
currentness, selection semantics, and evidence established earlier.

## Focused reproduction results

- API compatibility test: **failed as expected** on the exact-key assertion.
- Result Detail 390x844 system-browser test: **passed** locally in installed Chrome;
  the earlier candidate overflow was not reproduced by this exact isolated test.
- A first browser invocation with the system Python could not import Playwright; the
  pinned project virtual environment contained it. A sandboxed virtual-environment
  invocation could not create Playwright's named pipe; the same test completed after
  the approved system-browser launch outside the sandbox.
- No full regression, full 5M scan, import, training, scoring, calibration publication,
  or scenario execution was performed by Prompt 00.
- A full SQLite `quick_check` was not used as a baseline gate because it would be an
  unbounded scan of the 7.57 GB canonical database. Targeted read-only relational and
  aggregate checks are recorded above; full database certification belongs to later
  bounded certification prompts.

## Prompt 00 decision

**GO for Prompt 00 only.** The starting state, red CI, reproducible API failure,
non-reproduced browser candidate, canonical aggregate state, dependency gaps, frozen
invariants, and mandatory execution order are sufficiently explicit for Prompt 01.
This is not a GO for release or for skipping any later prompt.
