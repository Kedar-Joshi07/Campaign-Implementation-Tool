# Phase 10 Model Compatibility, Reuse, and Validation

Generated: 2026-09-14

Prompt: `Prompts/phase10_campaign_intelligence_orchestration_prompt_pack/06_STEP_06_MODEL_COMPATIBILITY_REUSE_AND_VALIDATION.md`

## Step result

`PASS_STEP_06_MODEL_COMPATIBILITY_REUSE_AND_VALIDATION`

Phase 10 now resolves models through a fail-closed compatibility boundary,
prefers compatible CURRENT/REUSABLE Phase 10 generations, discovers compatible
pre-Phase10 model runs when necessary, and invokes governed training
synchronously only when no reusable model exists.

## Exact model compatibility

A candidate is reusable only after all of the following checks pass:

- model status is `COMPLETED`;
- `analysis_run_id` equals the exact Step 5 Historical Analysis;
- current reconstructed observation, selected, P, and U counts equal the model
  counts;
- deterministic training/validation row and positive counts equal the saved
  model counts under seed 42 and validation fraction 0.20;
- the selected candidate is the governed `BAGGING_PU` PRIMARY;
- the persisted feature contract equals the complete frozen contract and its
  version/SHA-256 equal the current values;
- model-role version, PRIMARY-only selection policy, candidate roles, and
  non-selectability of challenger/diagnostic candidates are valid;
- evaluation contract version and complete evaluation metadata are valid;
- automated-training policy is compatible: seed 42, fraction 0.20, and enabled
  Elkan-Noto challenger execution was not recorded as disabled;
- preprocessing metadata is structurally reconciled to the exact raw and
  transformed feature definitions;
- hyperparameter metadata identifies the bounded single-job Bagging PU PRIMARY
  and the governed label contract;
- metadata contains no customer/person identity, raw matrices, validation
  scores, or other prohibited persisted model input;
- the artifact path is safe, the file exists, its SHA-256 matches, it loads,
  its payload matches the frozen feature/PRIMARY metadata, and its selected
  estimator is a Bagging PU classifier; and
- required library metadata is a valid JSON object.

The same complete gate is exposed as
`validate_phase10_model_before_scoring`. Scoring therefore cannot rely on an
earlier reuse decision after the model, artifact, analysis, or sources change.

## Ordered discovery and deterministic selection

Discovery proceeds in two sequential tiers:

1. READY Phase 10 generations for the exact Modeling Context whose lifecycle
   is `CURRENT` or `REUSABLE`; CURRENT is ordered first, then newest creation
   timestamp and generation ID.
2. If the first tier has no compatible candidate, all model runs linked to the
   exact analysis, ordered by completed timestamp, created timestamp, and model
   run ID descending. This discovers compatible pre-Phase10 runs.

Every candidate in a tier is fully filtered before the first compatible record
is selected. The returned resolution records all compatible candidates and all
rejected candidates with deterministic reason codes. A newer incompatible
candidate therefore cannot displace an older exact-compatible candidate.

Phase 10 generation candidates receive additional validation of their
compatibility, historical-filter, source import/checksum, historical-window,
multi-product, eligibility, feature, role, evaluation, automated-training,
analysis, and artifact identities. A generation rejected for stale registry
metadata does not prevent its underlying model from being independently
rediscovered in the legacy tier when that model itself is still compatible.

## Fresh training and executor safety

When neither discovery tier contains a compatible model, Phase 10:

- persists a bounded `MODEL_TRAINING` child job containing the exact analysis,
  seed 42, validation fraction 0.20, and enabled Elkan-Noto setting;
- directly invokes the existing synchronous model-training worker/core;
- preserves the existing governed candidate roles, Bagging PRIMARY selection,
  challenger-only Elkan-Noto behavior, diagnostic non-selectability, artifact
  lifecycle, progress, and failure handling;
- reloads the terminal child job and requires `COMPLETED`; and
- subjects the newly trained model to the same complete pre-scoring gate.

The Phase 10 path never submits the child task into the shared single-worker
pool and waits on it. This prevents parent-worker self-deadlock while retaining
durable child-job metadata and existing progress transitions.

If Step 5 returned BLOCKED, Step 6 returns BLOCKED with no model, child job, or
scoring work.

## Regression coverage

The Step 6 tests use isolated temporary SQLite databases and temporary artifact
directories. Their fresh-training cases execute the real governed training
worker/core; they do not write to the project runtime database or production
artifact directory.

Covered cases include:

- real fresh synchronous child-job training and verified artifact creation;
- exact legacy model reuse;
- CURRENT/REUSABLE generation priority;
- deterministic newest-compatible selection after all candidates are checked;
- wrong analysis linkage;
- wrong feature contract;
- wrong model-role policy;
- wrong evaluation contract;
- incompatible automated-training policy and disabled challenger;
- challenger selected as the official model;
- invalid preprocessing and hyperparameter metadata;
- prohibited customer-level metadata;
- missing and checksum-corrupt artifacts;
- failed model runs;
- complete pre-scoring revalidation; and
- blocked history producing no model, child job, or scoring run.

## Verification

| Gate | Result |
|---|---|
| Final Step 6 focused suite | PASS - 4 tests in 27.11s |
| Initial affected Phase 10/model/job/scoring suites | PASS - 103 tests in 64.38s |
| Full repository regression after final changes | PASS - 621 tests in 863.63s |
| Python compilation | PASS |
| Diff whitespace/error check | PASS |
| Real governed training on isolated test data | PASS |
| Shared executor submission from Phase 10 parent | Not used |
| Production model training | Not run |
| Production scoring/import work | Not run |

## Stop boundary

Step 6 ends after exact model resolution and the mandatory pre-scoring model
gate. It does not resolve or execute prospect scoring, rank preparation,
generation registration, lifecycle orchestration, Phase 9 binding, or UI work.
Those remain assigned to later sequential prompts.

`STOP_AFTER_STEP_06`
