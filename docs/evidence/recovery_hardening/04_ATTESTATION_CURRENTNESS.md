# Prompt 04 — Trustworthy Attestation and Source Currentness

## Starting point

- Starting SHA: `f437efd3be9e6d4945b0ee12bff91ccce2697088`.
- The working tree already contained the completed, uncommitted Prompt 01–03 changes and evidence. They were preserved.
- No commit or push was performed.

## Defects reproduced

The prior `record_deep_verification_attestation` implementation compared only `COUNT(propensity_scores)` with `scoring_runs.scored_person_count`. Its key contained generation/scoring IDs, the model artifact checksum, three source checksums, and the application schema version, but omitted import IDs, model ID, feature/scoring contracts, rank/analytics contracts, and the verified facts.

`has_current_attestation` then recomputed that key solely from the generation's stored values. A new authoritative import did not change the old generation row, so an attestation could remain `VERIFIED` after its real source had changed. Duplicate/missing/extra identities, invalid score facts, contract drift, and rank/analytics readiness were not established by attestation creation.

## Root cause

The attestation was a row-count memo, not evidence of the authoritative deep validator. Currentness was circular: it asked whether the generation still described the identity it had when created, rather than comparing that identity with the latest authoritative source imports and current runtime contracts.

## Before and after call graph

### Before

```text
Phase 11 direct reuse
  -> has_current_attestation(generation)
     -> hash values stored on that same generation
     -> SELECT VERIFIED row
     -> true even when a newer source import exists

Calibration promotion
  -> record_deep_verification_attestation
     -> SELECT scoring status/scored_person_count
     -> SELECT COUNT(propensity_scores)
     -> VERIFIED when counts match
```

### After

```text
Attestation creation / refresh / explicit certification
  -> reload authoritative generation by ID
  -> validate generation + scoring + model + artifact + feature/scoring contracts
  -> compare generation identity with latest customer/campaign-sales/demographic imports
  -> authoritative deep scoring validator
       -> score count + distinct count + duplicate count
       -> missing/extra demographic membership
       -> finite [0,1] scores and actual min/mean/max
       -> scoring/model/source provenance
  -> authoritative rank/analytics readiness validator
  -> persist contract versions + exact identity + fact JSON + fact SHA + outcome
  -> VERIFIED only when every required fact succeeds

Ordinary Phase 11 direct reuse
  -> reload authoritative generation/scoring/model metadata
  -> compare import IDs/checksums with latest authoritative imports
  -> compare score-summary/model/artifact/feature identities
  -> bounded 100-row rank-boundary + one analytics-snapshot check
  -> exact current v2 attestation lookup
  -> no propensity-score deep scan
```

## Versioned identity and persisted evidence

Schema version 24 extends `intelligence_verification_attestations` with:

- verification contract version `2`;
- integrity contract version `2`;
- model run ID and artifact identity;
- feature contract version/checksum;
- scoring semantics checksum;
- customer, campaign-sales, and demographic import IDs/checksums;
- rank and analytics contract versions;
- canonical verified facts JSON and its SHA-256;
- bounded failure-code JSON.

The attestation key also binds the generation, analysis, model, scoring, all three source identities, schema version, feature/scoring identities, generation policies, rank/analytics identities, and expected population count.

Migration 24 retains older records but marks row-count-only `VERIFIED` rows `STALE`. They are never silently accepted under v2. The migration is idempotent.

## Deep verification facts

The authoritative scoring integrity repository now returns, in one governed fact set:

- score row count;
- distinct person count;
- duplicate count;
- missing demographic count;
- extra person count;
- invalid/non-finite/out-of-range score count;
- actual score minimum, mean, and maximum.

The existing deep scoring validator consumes these facts, reconciles them with scoring metadata and current source provenance, and exposes them to the attestation service. The attestation service additionally requires current rank boundaries and the current analytics snapshot. Any required failure persists a `FAILED` attestation with allowlisted failure codes; it never promotes `VERIFIED` evidence.

## Source currentness invariant

`has_current_attestation` first resolves the latest completed customer, campaign-sales, and demographic imports. Their IDs and checksums must exactly equal the attested generation. It then checks current model/scoring metadata, scoring-summary identity, feature and artifact identity, rank boundaries, analytics snapshot, schema version, and verification/integrity contract versions before accepting the exact attestation key.

Therefore a newer authoritative import makes currentness false automatically even if the old generation row and old attestation remain unchanged. Correctness does not depend on a best-effort invalidation callback.

## Performance benchmark

On the bounded certified 60-person integration dataset, 10 consecutive `has_current_attestation` calls produced:

- all 10 results current: `true`;
- total: `2.482391` seconds;
- mean: `248.239` ms per call.

The benchmark calls only bounded metadata, 100 rank-boundary rows, and one analytics snapshot. A test replaces the deep validator with a function that raises and proves both `has_current_attestation` and the Phase 11 direct-reuse path still succeed, demonstrating that ordinary reuse does not scan propensity scores.

## Files changed for Prompt 04

- `app/database/schema.py`
- `app/database/search_recovery_schema.py`
- `app/repositories/scoring_repository.py`
- `app/services/prospect_scoring_service.py`
- `app/services/intelligence_attestation_service.py`
- schema-version assertions advanced to version 24
- `tests/test_intelligence_attestation_currentness.py`
- `tests/test_prospect_scoring_service.py`
- `tests/test_search_recovery_calibration_feedback.py`

## Tests

The Step 04 matrix proves:

1. valid full lineage creates a v2 `VERIFIED` attestation with fact hash;
2. duplicate score identity signal prevents verification;
3. missing demographic membership prevents verification;
4. invalid score signal prevents verification;
5. missing model identity prevents verification;
6. a newer authoritative demographic import makes currentness false;
7. unchanged source and generation return true through the bounded fast path;
8. old verification/integrity contracts are not reused;
9. migration 24 makes legacy count-only attestations stale and is idempotent;
10. Phase 11 direct reuse does not invoke the deep validator;
11. existing calibration, scoring, provenance, schema, and smart-reuse behavior remains green;
12. Prompt 03 retry/rejoin and Prompt 02 attempt fencing remain green on schema 24.

## Commands and results

- New Step 04 currentness module after final optimization: **9 passed** in 39.89 seconds.
- Affected calibration, Phase 10 scoring, prospect scoring/repository, Phase 11 smart reuse, and schema suite: **78 passed** in 231.15 seconds.
- Prompt 03 dependency retry/rejoin plus Prompt 02 fencing regression: **19 passed** in 64.22 seconds.
- Ruff on all Step 04 production/test files: **passed**.
- Python compilation: **passed**.
- `git diff --check`: **passed** (Git emitted only existing CRLF normalization notices).

## Known remaining risks

- The benchmark is a bounded integration benchmark, not the later canonical five-million-row certification. It nevertheless proves the reuse path is independent of population size because it issues no score-table scan.
- Full repository-wide CI, real-browser certification, and canonical production-data certification are owned by later prompts in this recovery pack and are not claimed here.
- Prompt 01–03 changes remain uncommitted in the same working tree and are intentionally preserved.

## Gate

**GO.** `has_current_attestation` cannot return true after an authoritative source change without a new matching v2 verification, and ordinary direct reuse does not invoke the deep validator.

**Recommended next prompt:** the next sequential prompt in `campaign_recovery_prompt_pack_f437efd3`.
