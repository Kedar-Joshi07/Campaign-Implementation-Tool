# Phase 10 Historical Context Extension

Generated: 2026-09-13

Prompt: `Prompts/phase10_campaign_intelligence_orchestration_prompt_pack/03_STEP_03_EXTEND_HISTORICAL_CONTEXT_FILTERING.md`

## Step result

`PASS_STEP_03_HISTORICAL_CONTEXT_EXTENSION`

Historical Analysis now supports `campaign_categories` and `offer_types` from
request validation through persisted filters, response/default/options
contracts, SQL cohort selection, saved-run replay/currentness, and training
cohort reconstruction. The extension is backward compatible with pre-Phase-10
saved filter JSON and low-level callers that omit both fields.

## Implementation

| File | Change |
|---|---|
| `app/schemas/historical.py` | Added normalized category/offer lists to request, persisted payload, run response, defaults, and options contracts |
| `app/repositories/historical_repository.py` | Added parameterized category/offer predicates and bounded, exact distinct option queries |
| `app/services/historical_service.py` | Added empty-list defaults for both new dimensions |
| `app/services/historical_analysis_service.py` | Added old-JSON normalization and the canonical inclusive contact-date range resolver |
| `app/services/phase10_context_identity_service.py` | Added deterministic Modeling Context to exact Historical-filter resolution for Phase 10 |
| `tests/test_phase10_historical_context_extension.py` | Added Step 3 contract, query, replay, reconstruction, and date-resolution proofs |
| `tests/test_historical_service.py` | Updated option/default and fixed-query-count regression expectations |

No database migration was needed: canonical `campaign_sales` already contains
nullable `campaign_category` and `offer_type` columns populated by the governed
import path.

## Filter and cohort semantics

Each populated list is emitted as one parameterized SQL `IN` predicate. Values
inside a dimension are therefore ORed; populated dimensions are joined with
`AND`. Empty or omitted category/offer dimensions add no predicate and preserve
the previous historical cohort.

The existing authoritative `matching_observations` / `customer_labels` CTE is
shared by historical analysis and training reconstruction. It groups by
`customer_id` and calculates the governed label with `MAX(...)`. Consequently:

- multiple qualifying observations/products still produce one customer row;
- a customer is positive when any qualifying selected-product observation has
  an attributed purchase; and
- no per-product score or label fusion is introduced.

The Step 3 fixture proves a customer with two selected products is emitted once
and labeled positive because one of those products has a governed positive
outcome, while a second customer remains unlabeled.

## Backward compatibility

New filter instances default both fields to `[]`. Saved-run decoding first
copies the stored payload and supplies missing `campaign_categories` and
`offer_types` as empty lists before strict normalization/consistency checks.
The public replay response therefore always returns the expanded current shape.

The low-level shared CTE also treats absent new keys as empty lists. This
protects older internal dictionary callers as well as saved-analysis replay.
Strict validation remains in force for malformed values and all existing
fields. Training-cohort reconstruction consumes the normalized replay payload,
so old completed runs remain reconstructable when their source provenance is
current.

## Exact options and full-window resolution

Historical options now return trimmed, nonblank, case-stably sorted distinct
values from canonical `campaign_sales` for both new dimensions. The queries are
bounded at 100 values each and do not fabricate catalog values.

`resolve_current_canonical_contact_date_range()` returns the exact inclusive
minimum and maximum canonical `contact_date` values, rejects unloaded history,
and fails closed on invalid ranges. `resolve_phase10_historical_filters()` uses
those exact dates and projects all Modeling Context analytical dimensions plus
the governed contacted/conversion policies into the typed resolved-filter
contract. It does not use implicit date defaults.

The Phase 10 filter-generation service boundary resolves this directly and
does not depend on navigation through the advanced Historical Analysis page.
The advanced page was not changed because its exposure is optional in this
step; later orchestration can call this boundary without UI coupling.

## Required scenario proof

| Requirement | Verified result |
|---|---|
| Empty new filters preserve old behavior | Omitted and explicit-empty runs have identical summaries |
| Campaign category only | Lifecycle selects 4 observations / 3 customers / 1 positive |
| Offer only | Loyalty selects 2 observations / 2 customers / 0 positives |
| Category plus offer | Lifecycle AND (Bundle OR Discount) selects 2 observations / 2 customers / 1 positive |
| Multi-product plus category plus offer | 3 observations collapse to 2 unique customer rows; labels are C1=1, C2=0 |
| Zero result | Unknown campaign category raises the governed no-match error |
| Old JSON compatibility | Missing keys reopen as empty lists and reconstruct successfully |
| Exact available options | Categories and offers equal the canonical fixture's distinct values |
| Exact Phase 10 dates | Resolved inclusive window is `2025-01-01` through `2025-02-02` |

## Verification

| Gate | Result |
|---|---|
| Step 3 focused scenarios | PASS - 7 passed |
| Legacy low-level SQL compatibility plus Step 3 suite | PASS - 8 passed |
| Full repository regression suite | PASS - 597 passed in 402.89s |
| Python module compilation | PASS |
| Whitespace/error-marker check | PASS |
| Production import/training/scoring/ranking | Not run; not required and no production data mutation was needed |

The first full-suite pass exposed one legacy direct-call dictionary without the
new keys. The SQL boundary was corrected to apply the required empty-list
compatibility rule, the failed test passed, and the complete 597-test suite was
then rerun successfully.

## Stop boundary

Step 3 does not add registry persistence, compatible-generation lookup,
automated training/scoring orchestration, Phase 9 integration, or new business
UI/API surfaces. Those remain assigned to subsequent sequential prompts.

`STOP_AFTER_STEP_03`
