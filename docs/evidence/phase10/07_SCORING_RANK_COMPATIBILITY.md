# Phase 10 Scoring, Rank, Analytics Compatibility and Reuse

Generated: 2026-09-14

Prompt: `Prompts/phase10_campaign_intelligence_orchestration_prompt_pack/07_STEP_07_SCORING_RANK_COMPATIBILITY_AND_REUSE.md`

## Step result

`PASS_STEP_07_SCORING_RANK_COMPATIBILITY_AND_REUSE`

Phase 10 now resolves a complete scoring generation through an exact,
fail-closed compatibility gate. It reuses current scoring only when the model,
artifact, feature contract, score semantics, demographic source, full-universe
score integrity, and canonical provenance all match. Rank boundaries and the
analytics snapshot are independently reused or rebuilt without retraining or
rescoring when scoring itself remains current.

## Exact scoring compatibility

A persisted scoring candidate is reusable only when all of these checks pass:

- lifecycle status is `COMPLETED`;
- `model_run_id` is the exact compatible Step 6 model;
- the persisted artifact SHA-256 equals the revalidated model artifact;
- feature-contract version and SHA-256 equal the frozen current contract;
- the governed PRIMARY candidate and model-role policy are exact;
- score semantics identify the current look-alike propensity-score contract;
- demographic import ID, source checksum, row count, and minimum/maximum
  person identity match the latest completed demographic import and current
  demographic table;
- persisted run and summary counts equal the entire current demographic
  universe;
- score-row count and distinct-person count both equal that universe;
- missing people, extra people, and duplicate `(run, person)` scores are zero;
- every persisted score is numeric, finite, and within `[0, 1]`;
- the existing deep scoring-integrity verifier passes against current
  demographic and historical sources; and
- the run is the current canonical scoring run for its model.

Candidates are inspected in deterministic newest-first order. Rejected records
carry explicit reason codes. The same complete boundary is exposed through
`validate_phase10_scoring_candidate` for mandatory revalidation immediately
before reuse.

## Scoring execution and demographic drift

When no candidate passes, Phase 10 creates a durable `PROSPECT_SCORING` child
job and directly invokes the existing synchronous scoring worker/core. This
preserves the existing bounded chunking, full-universe reconciliation,
artifact verification, progress, completion, and failure lifecycles without
submitting a child task into the shared single-worker executor.

A demographics-only source change invalidates prior scoring while leaving the
Step 5 analysis and Step 6 model compatible. The resolver therefore reuses
those exact IDs, scores the complete new demographic universe, and rebuilds
rank/analytics. It does not create a model-training job.

## Independent rank and analytics readiness

READY requires all 100 percentile boundaries, sequential bucket IDs, the
correct ceiling rank for every bucket and population, finite `[0, 1]`
boundary scores, valid tie-break person IDs, and the current rank-contract
version. It also requires a current canonical analytics snapshot, verified
source provenance, and `ready_for_current_audience_actions=true`.

If scoring is compatible but a boundary is missing, the analytics snapshot is
missing/stale, or the rank contract is wrong, only the existing rank/analytics
preparation core runs. The scoring run, model, score rows, and child-job counts
remain unchanged.

## READY generation and Phase 9 bridge

Once scoring, rank, and analytics are current, Phase 10 builds a deterministic
intelligence key from the exact scoring compatibility fingerprint plus rank
and analytics contracts. It then:

- reuses an exact CURRENT/REUSABLE READY generation or registers a complete
  immutable generation with full historical/model/scoring provenance;
- verifies payload hashes and all foreign lineage before reuse;
- requires the orchestration Modeling Context and intelligence key to match
  the generation;
- atomically transitions the orchestration to READY, upserts the READY Phase
  10 context binding, and writes the exact scoring run into the existing Phase
  9 `source_scoring_run_id`; and
- supports idempotent READY replay without another generation or heavy work.

An existing Phase 9 scoring binding is safely replaced only by the fully
verified current scoring generation.

## Regression coverage

All Step 7 integration tests use isolated temporary SQLite databases and
temporary model-artifact directories. They execute real bounded training,
scoring, rank, and analytics cores only against fixture data.

Covered cases include:

- fresh synchronous scoring plus rank/analytics preparation;
- complete scoring and rank reuse with no child job;
- demographics-only drift with analysis/model reuse and full rescoring;
- incomplete full-universe scores;
- duplicate-person and invalid-score integrity findings;
- artifact SHA mismatch and score-semantics mismatch;
- missing percentile boundaries;
- missing analytics snapshots;
- rank-contract mismatch;
- rank-only repair with unchanged scoring/model/job counts;
- deterministic generation registration and exact reuse;
- orchestration/generation identity and lineage validation;
- replacement of an existing Phase 9 scoring binding; and
- idempotent READY finalization.

## Verification

| Gate | Result |
|---|---|
| Final Step 7 focused suite | PASS - 5 tests in 76.38s |
| Affected scoring/rank/repository suites | PASS - 58 tests in 293.78s |
| Full repository regression after final changes | PASS - 626 tests in 833.69s |
| Python compilation | PASS |
| Ruff changed-file checks | PASS |
| Diff whitespace/error check | PASS (line-ending notices only) |
| Real bounded fixture training/scoring/rank | PASS |
| Shared executor submission from Phase 10 parent | Not used |
| Production imports/training/scoring | Not run |

## Stop boundary

Step 7 ends after scoring/rank resolution and the reusable READY-generation /
Phase 9 binding primitives. It does not implement the Step 8 orchestration
worker/API lifecycle, Step 9/10 UI flow, or later observability, browser,
performance, CI, and freeze work.

`STOP_AFTER_STEP_07`
