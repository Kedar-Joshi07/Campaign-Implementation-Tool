# Phase 10 Intelligence Lifecycle and Retention

Generated: 2026-09-14

Prompt: `Prompts/phase10_campaign_intelligence_orchestration_prompt_pack/11_STEP_11_INTELLIGENCE_LIFECYCLE_AND_RETENTION.md`

## Step result

`PASS_STEP_11_INTELLIGENCE_LIFECYCLE_AND_RETENTION`

Phase 10 now classifies every registered READY intelligence generation as
`CURRENT`, `REUSABLE`, `SUPERSEDED`, `STALE`, `RETIREMENT_ELIGIBLE`, or
`PROTECTED`. Classification updates only lifecycle metadata; it does not delete
or rewrite analytical lineage, immutable audiences, Target Groups, Campaigns,
or artifacts.

## Deterministic lifecycle classification

`reconcile_phase10_lifecycle` verifies each generation's immutable registry
record and compares its complete source and policy identity with the current
customer, campaign-sales, and demographic imports and the current Phase 10
contracts. The base classification is deterministic:

- an incompatible or unverifiable generation is `STALE`;
- a source-current generation with a newer generation for the same Modeling
  Context is `SUPERSEDED`;
- the newest source-current generation with a READY Campaign Context binding is
  `CURRENT`; and
- an otherwise source-current generation is `REUSABLE`.

A stale or superseded generation becomes `RETIREMENT_ELIGIBLE` only when it has
no Campaign Context binding and no protection reason. This is a classification,
not a deletion instruction.

The durable orchestration service applies the metadata-only classification
before reuse/build planning and after READY publication. A protected generation
remains eligible for compatibility-validated reuse: `PROTECTED` prevents
retirement and does not force avoidable training or scoring.

## Protection graph

A generation is overridden to `PROTECTED` when its analytical scoring lineage
is directly or indirectly referenced by any of the following:

- a Saved Audience;
- a Phase 9 Saved Target Group;
- a Campaign;
- a finalized Campaign;
- Campaign export audit history; or
- a QUEUED/RUNNING orchestration through generation, scoring, intelligence-key,
  or Modeling Context lineage.

The report preserves both the effective `PROTECTED` state and the
`classification_before_protection`, so a protected superseded/stale generation
remains auditable. No existing audience, Target Group, or Campaign reference is
mutated to point at a newer generation.

## Usage tracking

`last_used_at` is touched for the exact verified Phase 10 generation and its
Campaign Context binding when:

- an existing READY generation is reused by orchestration;
- Target Group preview or paged preview search succeeds; or
- Target Group save and Campaign-draft creation passes source/currentness
  validation.

Phase 9-only scoring sources safely no-op because they have no Phase 10 READY
generation binding.

## No-PII lifecycle report

The strict `Phase10LifecycleReport` contains only operational identifiers and
aggregate metadata:

- counts for all six lifecycle states;
- total registered generation count;
- each generation's score-row count;
- a de-duplicated physical score-row footprint across registered scoring runs;
- ordered protection reasons;
- reusable Campaign Context IDs; and
- retirement-eligible generation IDs.

It exposes no customer/person/contact attributes or score-row contents. When
multiple registry generations reuse one scoring run, the total footprint counts
those physical propensity-score rows once.

## Non-destructive retention boundary

The lifecycle service and repository contain no analytical DELETE operation.
Step 11 does not automatically delete:

- `propensity_scores`;
- `scoring_runs`;
- model artifacts or `model_runs`; or
- `historical_analysis_runs`.

Tests snapshot the analytical table counts and verify the model artifact still
exists before and after lifecycle reconciliation.

## Regression coverage

The focused lifecycle suite proves:

- current generation reporting and exact READY reuse;
- `last_used_at` updates on reuse, preview, and Target Group save;
- a superseded generation referenced through Saved Audience, Phase 9 Saved
  Target Group, and Campaign remains `PROTECTED` without reference mutation;
- an unreferenced superseded generation becomes `RETIREMENT_ELIGIBLE`;
- a newer completed demographic import marks the old generation `STALE`;
- active orchestration makes a generation `PROTECTED`;
- the report schema is strict and recursively contains no PII field names;
- shared score rows are not double-counted in the total footprint; and
- lifecycle classification performs no analytical deletion.

## Verification

| Gate | Result |
|---|---|
| Step 11 focused lifecycle suite | PASS - 5 tests in 59.02s |
| Phase 9 preview/save/progressive-disclosure/currentness compatibility plus updated repository contract | PASS - 30 tests in 132.72s |
| Complete Phase 10 regression after final changes | PASS - 84 tests in 210.52s |
| Ruff changed-file checks | PASS |
| Python compilation | PASS |
| Diff whitespace/error check | PASS (line-ending notices only) |
| Production imports/training/scoring | Not run |

All analytical work performed by tests used bounded temporary SQLite fixtures
and temporary model artifacts. No production or repository runtime database was
modified.

## Stop boundary

Step 11 stops after lifecycle classification, protection, usage tracking,
no-PII reporting, non-destructive retention proof, and affected regression. It
does not implement Step 12+ comprehensive matrix, clean-room, system-browser,
full-scale, observability, performance, CI, documentation-freeze, or Phase 10
freeze work.

`STOP_AFTER_STEP_11`
