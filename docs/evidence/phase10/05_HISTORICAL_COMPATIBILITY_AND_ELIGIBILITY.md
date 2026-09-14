# Phase 10 Historical Compatibility and Training Eligibility

Generated: 2026-09-14

Prompt: `Prompts/phase10_campaign_intelligence_orchestration_prompt_pack/05_STEP_05_HISTORICAL_ANALYSIS_COMPATIBILITY_AND_ELIGIBILITY.md`

## Step result

`PASS_STEP_05_HISTORICAL_COMPATIBILITY_AND_ELIGIBILITY`

Phase 10 now resolves Historical Analysis through an exact, source-current
compatibility boundary and applies a frozen version-1 training-eligibility
policy before any model or scoring work can begin.

## Modeling Context to Historical filters

The resolver uses the canonical Phase 10 context service and maps exactly:

| Modeling Context field | Historical Analysis filter |
|---|---|
| `product_ids` | `product_ids` |
| `campaign_types` | `campaign_types` |
| `campaign_categories` | `campaign_categories` |
| `offer_types` | `offer_types` |
| `historical_campaign_channels` | `campaign_channels` |
| canonical historical start/end | full `contact_date_start` / `contact_date_end` range |
| fixed policy | `contacted_only=true` |
| fixed response definition | `ATTRIBUTED_PURCHASE` |

Delivery channel and Phase 9 prospect-target controls are deliberately absent
from the Modeling Context and Historical filters. Changing either therefore
does not change Historical Analysis compatibility.

## Exact compatibility and legacy discovery

A saved analysis is reusable only when all of these conditions hold:

- status is `COMPLETED`;
- decoded and normalized saved filters equal the required filters exactly;
- customer import ID and normalized checksum equal the current source;
- campaign-sales import ID and normalized checksum equal the current source;
- the saved selected, positive, and unlabeled counts reconcile with a fresh
  reconstruction of the exact current cohort; and
- reconstructed cohort currentness and source lineage remain valid.

Subset and superset matches are rejected. Completed candidates are checked in
deterministic completion/ID order, but recency only chooses among candidates
that first pass every exact-compatibility condition.

Pre-Phase10 analyses remain discoverable: their stored filter JSON is decoded
through the existing Historical schema defaults and canonical normalization
before comparison. A legacy payload that omitted subsequently defaulted keys
was proven reusable when its normalized meaning was exactly equivalent.

When no compatible analysis exists, the resolver delegates creation to the
existing governed `create_historical_analysis` service and returns its durable
analysis ID. It does not insert an analysis directly or weaken the requested
filters.

## Frozen training-eligibility policy v1

| Requirement | Version-1 value |
|---|---:|
| Minimum selected customers | 14 |
| Minimum positive customers (P) | 7 |
| Minimum unlabeled customers (U) | 7 |
| Deterministic split viability | Required |

The numerical boundary is derived from the existing training constraints, not
chosen independently: training requires at least five P and five U records,
while the governed stratified split reserves 20% for validation. Seven records
per class are the integer boundary that leaves at least five for training and
at least one for validation. This yields the 14-customer total floor.

Passing the count floor is necessary but not sufficient. The resolver also
reconstructs the exact cohort and executes the existing deterministic split
(seed 42, validation fraction 0.20), checking:

- at least five P and five U records in training;
- both classes in validation; and
- when the Elkan-Noto correction is enabled, at least one positive in its
  deterministic 10% training holdout.

This independent viability gate prevents a count-eligible but structurally
unsplittable cohort from advancing.

An ineligible resolution is terminal for this stage:

- status: `BLOCKED`;
- model/scoring work: not invoked;
- filters: never silently broadened; and
- business message: `There is not enough verified past campaign history for this combination yet.`

Deterministic reason codes and reconciled selected/P/U counts are retained in
the versioned `TrainingEligibilityContract` for technical diagnosis without
exposing customer-level data.

## Read-only runtime diagnostics

Representative diagnostics were executed against `data/campaign_poc.db` using
SQLite read-only URI mode. They reconstructed counts only; they did not create
an analysis, model, scoring run, or job.

Canonical date range: 2024-01-01 through 2025-12-31.

| Representative context | Selected | P | U | Count gate |
|---|---:|---:|---:|---|
| Narrow single product (`PRD020`) | 2,137 | 142 | 1,995 | PASS |
| Multi-product (`PRD020`, `PRD001`) | 5,350 | 341 | 5,009 | PASS |
| Broad (all 36 available products) | 119,748 | 25,473 | 94,275 | PASS |
| Restrictive category/offer (`Holiday / Year-end Promotion`, `Fixed Discount`) | 2,482 | 143 | 2,339 | PASS |

These diagnostics establish that the frozen floors are compatible with narrow,
multi-product, broad, and restrictive representative runtime contexts. Exact
split viability is still evaluated per resolved cohort rather than inferred
from these aggregate diagnostics.

## Verification

| Gate | Result |
|---|---|
| Step 5 focused tests | PASS - 13 passed in 12.73s |
| Phase 10/Historical affected suites | PASS - 87 passed in 33.46s |
| Full repository regression | PASS - 617 passed in 428.99s |
| Exact reuse and mismatch rejection | PASS |
| Source import/checksum drift rejection | PASS |
| Delivery/prospect-target non-effect | PASS |
| Zero-history BLOCKED/no model or scoring | PASS |
| P/U count boundaries and split viability | PASS |
| Legacy saved-filter normalization/discovery | PASS |
| Non-reconciling saved counts fail closed | PASS |
| Python compilation | PASS |
| Diff whitespace/error check | PASS |
| Production analysis creation | Not run |
| Import/training/scoring work | Not run |

## Stop boundary

Step 5 ends after exact Historical Analysis resolution and training-eligibility
evaluation. It does not resolve or launch models, scoring, rank preparation,
orchestration jobs, Phase 9 bindings, or user-interface work. Those remain
assigned to later sequential prompts.

`STOP_AFTER_STEP_05`
