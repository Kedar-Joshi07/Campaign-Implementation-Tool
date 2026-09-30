# Prompt 03 — True Phase 10 Dependency Retry and Rejoin

## Starting point

- Starting SHA: `f437efd3be9e6d4945b0ee12bff91ccce2697088`.
- The working tree already contained the completed, uncommitted Prompt 01 and Prompt 02 changes and evidence. Those changes were preserved.
- No commit or push was performed.

## Defect reproduced

A Phase 11 retry created Attempt N+1, but the worker then read the same terminal Phase 10 orchestration through `get_phase10_preparation`. `_phase10_state` returned that Phase 10 `FAILED` or `BLOCKED` state immediately, so the new Phase 11 attempt became terminal without restarting or joining its actual dependency.

## Root cause

The Phase 11 retry boundary owned only the local search attempt. It had no durable Phase 10 dependency ID, no failure-ownership classification, and no call to the governed Phase 10 retry API. Phase 10 already had exact-key active-work deduplication and a retry entry point, but Phase 11 did not use either capability.

## Failure ownership map

| Persisted condition | Owner | Automatic retry behavior |
|---|---|---|
| Phase 11 processing/runtime transient | Phase 11 | New fenced Phase 11 attempt |
| `PHASE10_TRANSIENT_FAILED` / legacy targeting-intelligence failure | Phase 10 transient | New fenced Phase 11 attempt, then governed Phase 10 retry or active-work rejoin |
| `PHASE10_BUSINESS_BLOCKED` | Phase 10 business/data sufficiency | No automatic retry loop; business guidance required |
| `CALIBRATED_PROPENSITY_NOT_READY` | Calibration | Phase 11 retry remains available after calibration is prepared |
| `STALE_PROCESSING_ATTEMPT` | Stale Phase 11 worker | Terminalize the stale attempt and create a newly fenced attempt |
| `PHASE10_PERMANENT_VALIDATION_FAILED` and immutable-contract failures | Permanent validation | Not retryable |

## Dependency-owned retry state machine

```text
Phase 11 Attempt N fails while depending on Phase 10 P10-X
        |
        | POST retry with idempotency key
        v
Create immutable Phase 11 Attempt N+1 + fresh execution fence
        |
        +-- exact Phase 10 is QUEUED/RUNNING
        |       -> bind N+1 to the same P10-X (rejoined=true)
        |
        +-- exact Phase 10 is retryable FAILED
        |       -> call governed Phase 10 retry API
        |       -> durable exact-key uniqueness creates P10-Y once
        |       -> bind N+1 to P10-Y (rejoined=false)
        |
        +-- a concurrent retry already created P10-Y
        |       -> re-read active exact work
        |       -> bind N+1 to P10-Y (rejoined=true)
        |
        +-- Phase 10 is BLOCKED or permanent FAILED
                -> reject retry; retain terminal history

N+1 remains PROCESSING/WAITING while P10-Y is active.
P10-Y READY   -> Phase 11 continues cache resolution/materialization -> COMPLETED.
P10-Y BLOCKED -> Phase 11 becomes non-retryable BLOCKED with safe guidance.
P10-Y FAILED  -> Phase 11 records transient/permanent ownership from Phase 10.
```

## Schema and contracts

Schema version 23 adds:

- Phase 10 orchestration `failure_code`, `failure_category`, and `retryable` fields;
- Phase 11 attempt `phase10_orchestration_id`, `phase10_dependency_status`, `phase10_dependency_rejoined`, and `phase10_dependency_updated_at` fields;
- Phase 11 runtime `technical_reference`.

The migration backfills historical Phase 10 `FAILED` rows as retryable legacy transient failures and historical `BLOCKED` rows as non-retryable business/data-insufficiency failures. Existing attempt, result, and score history is not rewritten.

Phase 10 API technical details now return the allowlisted failure code/category, retry eligibility, and support reference `P10-<orchestration_id>`. `can_retry` no longer marks every BLOCKED/FAILED state retryable.

Every Phase 11 dependency-lineage mutation requires the Prompt 02 attempt number and execution token and permits only the currently active attempt. A retry attempt cannot change its dependency ID after binding.

## Business-safe behavior

- Active exact work is surfaced as a rejoin, and the progress message states that Phase 11 is waiting for the existing targeting-intelligence preparation.
- A Phase 10 failure exposes a bounded `P10-<id>` reference, not an exception, path, or traceback.
- Business/data insufficiency and permanent validation failures have `retryable=false` and cannot create an endless retry loop.
- `SEARCH_RUNTIME_UNAVAILABLE` remains a Phase 11-local transient condition and is not misclassified as Phase 10 business blocking.

## Files changed for Prompt 03

- `app/database/schema.py`
- `app/database/phase11_schema.py`
- `app/repositories/phase10_intelligence_repository.py`
- `app/repositories/campaign_result_registry_repository.py`
- `app/schemas/phase10_intelligence.py`
- `app/services/phase10_api_service.py`
- `app/services/phase10_orchestration_service.py`
- `app/services/phase11_dependency_retry_service.py`
- `app/services/phase11_run_lifecycle_service.py`
- `app/services/phase11_search_orchestration_service.py`
- `app/services/potential_customer_search_submission_service.py`
- schema-version assertions advanced to version 23
- `tests/test_phase11_phase10_retry_rejoin.py`

## Tests and acceptance proof

The new tests prove:

1. the prior retry-to-the-same-terminal-Phase-10 defect;
2. a transient terminal dependency creates a new exact Phase 10 orchestration;
3. a second Phase 11 retry sharing the modeling context joins the same active orchestration;
4. restart reconciliation submits that one durable parent only once;
5. Phase 10 business BLOCKED does not loop;
6. permanent Phase 10 validation failure is not retryable;
7. technical support references are persisted safely;
8. a controlled transient dependency retry reaches Phase 10 READY and then Phase 11 COMPLETED without a database reset;
9. Prompt 02 stale-worker fencing remains effective.

## Commands and results

- Python compilation: **passed**.
- Initial Phase 10/API/orchestration/fencing focused set: **30 passed** in 216.09 seconds.
- New retry/rejoin tests before completion-path addition: **3 passed** in 30.83 seconds.
- Controlled end-to-end retry-to-completion test: **1 passed** in 34.07 seconds.
- Broad affected Phase 10/Phase 11 retry, concurrency, restart, reuse, and fencing suite: **60 passed** in 334.40 seconds.
- API contract and stale-worker regression selector after correcting runtime-unavailable ownership: **3 passed** in 25.04 seconds.
- The Playwright-only static UI selector could not start because the current Python environment does not contain the `playwright` package. This is an environment dependency, not an application failure; existing retry DOM/JavaScript coverage remains in the repository and browser certification is deferred to the pack's browser prompt.

## Known remaining risks

- This step proves the controlled dependency path on a bounded test dataset. Canonical data deep verification and source-currentness policy are deliberately owned by Prompt 04.
- Full real-browser and repository-wide CI certification are later prompts in this pack and are not claimed here.
- Prompt 01 and Prompt 02 changes remain uncommitted in the same working tree and are intentionally preserved.

## Gate

**GO.** A retryable Phase 10 failure can be retried from the Phase 11 API path, creates or rejoins exactly one governed Phase 10 dependency, survives restart reconciliation, and reaches Phase 11 completion without manual database mutation.

**Recommended next prompt:** `04_ATTESTATION_DEEP_VERIFICATION_AND_SOURCE_CURRENTNESS.md`.
