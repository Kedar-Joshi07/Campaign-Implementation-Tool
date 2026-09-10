# Phase 9 Baseline and Gap Report

Generated at: 2026-09-09T06:31:42Z

Prompt: `Prompts/phase9_business_friendly_campaign_targeting_prompt_pack/01_STEP_01_BASELINE_AND_PHASE9_GAP_ANALYSIS.md`

## Decision

Step 1 is complete. The frozen Phase 1-8 implementation is verified at the exact required SHA and no functionality was changed. The only pre-existing worktree entry was the newly supplied, untracked Phase 9 prompt pack; there were no tracked-code modifications at the start of this step.

## Frozen baseline

| Item | Recorded state |
|---|---|
| Required Phase 1-8 SHA | `d6a9f9b963622a334bf3e5c3220e5d0a73e528fe` |
| Local branch / HEAD | `main` / `d6a9f9b963622a334bf3e5c3220e5d0a73e528fe` |
| Remote main | `d6a9f9b963622a334bf3e5c3220e5d0a73e528fe` |
| Tracked baseline status | Clean; only the untracked Phase 9 prompt pack was present |
| Application version | `0.1.0` |
| SQLite schema version | `12` |
| Feature Contract | v1 |
| Model Role Policy | v2 |
| Evaluation Contract | v2 |
| Audience filter / rank / selection / analytics | v1 / v1 / v1 / v1 |
| Campaign / export / member resolution | v1 / v1 / v1 |
| Exact-baseline CI | Run `34315317222`: all five required jobs completed successfully |

## Current information architecture

The current top-level navigation is implementation-oriented rather than campaign-first:

1. Overview
2. Data Status
3. Historical Analysis
4. Model Training & Prospect Scoring
5. Audience Explorer
6. Campaigns / current Phase 7 workflow

There is no default `Create Campaign` entry, no `Saved Target Groups` business surface, no `Insights` grouping, and no `Advanced` grouping. Historical analysis, PU terminology, model execution, scoring, raw run identifiers, rank bands, percentiles, and saved-audience terminology are visible in the normal navigation or default workspaces.

## Existing control inventory

The certified Phase 8 inventory contains 111 actionable controls: 104 `PASS`, 7 `JUSTIFIED_EXCLUSIVE`, 0 `FAIL`, and 0 `NOT_RUN`.

Audience Explorer has 38 controls. They expose exact Phase 6 functionality for score min/max, percentile, decile, rank band, age and income min/max, gender, state, marital status, education, employment status, resident status/type, family size, employment type, selection mode, TOP_N, estimate/search/profile, saved-audience creation/reopen, and Campaign Builder handoff.

Campaign Builder has 25 controls. Its flow is `Choose Audience -> Campaign Details -> Review -> Finalize / Export`; it requires an already-current Saved Audience before campaign creation. Campaign details currently contain name, description, delivery channel, and optional planned launch date. Product, campaign type, campaign category, offer type, and a separately defined historical-channel intent are not persisted in the campaign contract.

## Current API surface

The baseline exposes 38 operations across system/data/reference, historical analysis, model training/scoring, audience preparation/estimate/search/profile/saved audiences, and campaign draft/currentness/finalize/export APIs.

Reusable Phase 6 operations already provide exact estimates, deterministic keyset search, non-PII prospect rows, aggregate profiles, immutable saved audiences, and currentness. Reusable Phase 7 operations already provide campaign draft/update, currentness, finalization, governed Email/Direct Mail export, and aggregate export events.

There is no Phase 9 planning-session API, campaign-targeting-context contract, business-targeting criteria contract, business match-strength comparison API, explicit targeting-intelligence resolver interface, or draft-context linkage.

## Current data and lineage

| Layer | Current state |
|---|---|
| Imports | Customers 125,000; campaign sales 570,000; demographics 5,000,000; all completed with zero rejected rows |
| Historical analysis | Runs 1 and 2 completed; current targeting chain uses analysis run 2 |
| Model | Model run 1 completed from analysis run 2; selected candidate `BAGGING_PU` |
| Scoring | Scoring run 1 completed for exactly 5,000,000 potential customers |
| Audience preparation | 100 v1 rank boundaries and one v1 analytics snapshot for scoring run 1 |
| Saved Audience | Audience 1, immutable TOP_N selection, exact resolved count 50,000 |
| Campaigns | Campaigns 1 and 2 finalized from saved audience 1 for Email and Direct Mail |
| Exports | Export events 1 and 2 completed |
| Jobs | Training, scoring, and audience preparation jobs completed; no active lineage work |

The historical `customer_id` population and independent demographic `person_id` population remain deliberately separate. No identity mapping exists or is implied.

## Reference-data readiness

The historical source contains 36 products, 7 campaign types, 9 campaign categories, 6 offer types, and 9 historical campaign channels. Existing product and historical options services can be adapted instead of hardcoding JavaScript values. Delivery channel remains the frozen Phase 7 `EMAIL` / `DIRECT_MAIL` contract and must not be silently equated with historical channel context.

## Business-user gap register

| ID | Gap | Business impact | Required Phase 9 response |
|---|---|---|---|
| P9-G01 | Navigation begins with technical implementation stages | A user must understand the data/ML pipeline before starting a campaign | Add campaign-first navigation while retaining technical pages under Advanced/Insights |
| P9-G02 | Campaign creation requires a pre-existing current Saved Audience | The workflow is reversed for a campaign owner | Allow campaign details/context/preferences to exist as a draft before target-group save |
| P9-G03 | Default UI exposes Historical Analysis, PU, model, scoring, artifact, run ID, percentile, decile, and rank terminology | Non-technical users cannot understand the required sequence | Apply the business terminology contract and progressive disclosure |
| P9-G04 | No persisted campaign targeting context | Product/type/category/offer intent is lost | Add a versioned normalized additive context contract and persistence model |
| P9-G05 | No Phase 9 business targeting criteria contract | UI bucket semantics could drift or be client-owned | Add backend-owned, versioned criteria and canonical normalization |
| P9-G06 | Age and income are only continuous min/max filters | Business users cannot choose familiar, disjoint groups safely | Add server-owned age/income buckets and map disjoint selections without broadening them |
| P9-G07 | Score/rank/percentile controls are analyst-facing | Selectivity requires technical knowledge | Add Very Strong/Strong/Good/Broad cumulative match-strength choices with visible thresholds |
| P9-G08 | No exact match-strength comparison or deterministic recommendation | Users cannot see the size/selectivity trade-off | Compute exact counts through existing estimate logic and document a versioned recommendation rule |
| P9-G09 | No explicit targeting-intelligence resolution interface | A planner adapter could accidentally use an unrelated latest run | Require an explicitly linked, verified current source and return READY/STALE/NOT_AVAILABLE/INCOMPATIBLE_CONTEXT states |
| P9-G10 | Campaign context is not analytically linked today | Product/offer selections could be misrepresented as model inputs | Capture context honestly and reserve automatic compatibility/orchestration for Phase 10 |
| P9-G11 | No business `Why these people?` explanation | Exact output lacks plain-language meaning | Add deterministic, non-causal explanation based on context, criteria, threshold, and source status |
| P9-G12 | Target preview is technically labeled and lacks Phase 9 KPI/view models | Users see raw implementation concepts rather than campaign decisions | Adapt exact estimate/search/profile output into business KPIs, score bands, mix, and non-PII preview |
| P9-G13 | Saved Audience and technical provenance dominate the save/reopen experience | Business users lack a clear Saved Target Group concept | Preserve immutable Saved Audience internally while presenting Saved Target Group in the default UI |
| P9-G14 | Existing validation/currentness copy is frequently technical | Users cannot recover without backend knowledge | Add plain-language validation, empty/loading/error/currentness states while retaining audit reasons in details |
| P9-G15 | No Phase 9-specific control inventory or browser scenario | The new workflow would lack exhaustive real-browser assurance | Extend fail-closed inventory and certify all new controls in installed Chrome/Edge |

## Frozen behavior to reuse unchanged

- Historical-analysis cohort and aggregate engine.
- Governed PU model-training methodology, Feature Contract v1, Model Role Policy v2, and Evaluation Contract v2.
- Exact 5M prospect-scoring engine and currentness/provenance checks.
- Phase 6 audience preparation, exact estimate, deterministic keyset search, profile, and immutable Saved Audience services.
- Phase 7 campaign draft, currentness, finalization, immutable finalized state, Email/Direct Mail export profiles, export audit events, and PII acknowledgement.
- The `customer_id` / `person_id` separation and the rule that no contact PII appears before governed export.

Phase 9 should add adapters, view models, contracts, and additive persistence around these capabilities rather than rewriting them.

## Browser baseline

The latest strict-fresh Phase 8 certification used installed system Chrome `152.0.7977.83` in headless mode and passed with zero unexplained console errors, JavaScript exceptions, or critical network failures. Its 111-control inventory is the frozen starting inventory for Phase 9.

## Step boundary

No Phase 9 functionality, schema, API, or frontend behavior was implemented in Step 1. Proceed to Step 2 only under a separate continuation, per the prompt's `STOP` instruction.
