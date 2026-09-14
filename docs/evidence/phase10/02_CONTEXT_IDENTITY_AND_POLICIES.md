# Phase 10 Context Identity and Policy Contracts

Generated: 2026-09-13

Prompt: `Prompts/phase10_campaign_intelligence_orchestration_prompt_pack/02_STEP_02_PHASE10_CONTEXT_IDENTITY_AND_POLICY_CONTRACTS.md`

## Step result

`PASS_STEP_02_CONTEXT_IDENTITY_AND_POLICIES`

Phase 10 now has a strict, versioned Modeling Context that is separate from the
existing Phase 9 Campaign Context, plus canonical historical, model, and scoring
compatibility fingerprints. No persistence, compatibility search, pipeline
execution, API, or UI orchestration was added in this step.

## Implementation

| File | Purpose |
|---|---|
| `app/schemas/phase10_intelligence.py` | Strict Pydantic identity, resolved-filter, score-semantics, and layered compatibility contracts; Phase 10 policy/version constants |
| `app/services/phase10_context_identity_service.py` | Campaign-to-modeling projection, normalization, canonical UTF-8 JSON, SHA-256, current-policy validation, and three layered fingerprint builders |
| `tests/test_phase10_context_identity.py` | Order/exclusion/invalidation/policy/fingerprint boundary tests |

The existing Phase 9 context schema and
`normalize_campaign_targeting_context()` were not changed.

## Modeling Context contract v1

The canonical identity contains exactly:

- `product_ids`;
- `campaign_types`;
- `campaign_categories`;
- `offer_types`;
- `historical_campaign_channels`;
- `conversion_definition`;
- `contacted_only`;
- `historical_window_policy_version`;
- `multi_product_positive_policy_version`; and
- `modeling_context_contract_version`.

Every collection is trimmed, de-duplicated, and sorted deterministically. At
least one product is required. The strict canonical schema rejects unknown
fields. Serialization uses sorted keys, compact separators, finite JSON values,
Unicode-preserving output, UTF-8 encoding, and SHA-256.

`derive_modeling_context_from_campaign_context()` deliberately projects only
the five analytical dimensions from the broader Phase 9 object and injects the
current governed policy values. Therefore excluded fields never enter the
canonical payload accidentally.

The returned identity names its hash `modeling_context_sha256`; this is distinct
from and does not replace the existing Phase 9 `campaign_context_sha256`.

## Included and excluded identity fields

| Input | Modeling hash effect | Reason |
|---|---|---|
| Product IDs | Changes | Analytical cohort dimension |
| Campaign types | Changes | Analytical cohort dimension |
| Campaign categories | Changes | Analytical cohort dimension |
| Offer types | Changes | Analytical cohort dimension |
| Historical campaign channels | Changes | Analytical cohort dimension |
| Conversion/contacted policy | Changes | Defines labels and selected observations |
| Historical-window policy version | Changes | Defines resolved training window policy |
| Multi-product positive policy version | Changes | Defines customer-level positive aggregation |
| Modeling Context contract version | Changes | Defines identity interpretation |
| Delivery channel | No change | Delivery is a campaign execution choice |
| Campaign name/description/launch date | No change | Business metadata, not analytical compatibility |
| Match Strength | No change | Post-score targeting filter |
| Demographic targeting | No change | Post-score targeting filter |
| Top percentage/TOP_N | No change | Post-score selection rule |
| Target Group name/description | No change | Saved business-object metadata |

Tests also confirm that delivery-channel changes continue to change the existing
Phase 9 Campaign Context hash while leaving the new Modeling Context hash
unchanged. This preserves Phase 9 semantics and proves the two identities are
not aliases.

## Frozen Phase 10 policy constants

| Policy/contract | Version or value |
|---|---|
| Modeling Context contract | `1` |
| Compatibility contract | `1` |
| Historical-window policy | `1` |
| Multi-product positive policy | `1` |
| Training-eligibility policy | `1` |
| Automated-training policy | `1` |
| Orchestration contract | `1` |
| Intelligence-generation contract | `1` |
| Lifecycle policy | `1` |
| Conversion definition | `ATTRIBUTED_PURCHASE` |
| Contacted-only | `true` |
| Automated training seed | `42` |
| Validation fraction | `0.20` |
| Elkan-Noto challenger | enabled, advisory only |

Historical-window policy v1 means the complete currently available canonical
contact-date range, persisted later as exact inclusive `contact_date_from` and
`contact_date_to` values. Multi-product policy v1 means one combined customer
cohort and one model; a customer is positive when any qualifying row for any
selected product satisfies the governed conversion. It never means per-product
score fusion.

The training-eligibility policy version is frozen here. Its numeric eligibility
boundaries are intentionally not invented in Step 2; the prompt pack assigns
their deterministic derivation from existing training constraints and
representative canonical diagnostics to the later eligibility step.

Canonicalization accepts persisted versioned identities so old/future records
can be hashed and compared exactly. `validate_current_modeling_context_policy()`
is the explicit fail-closed boundary that permits only the current v1 contract,
historical-window and multi-product policies plus attributed-purchase/contacted
semantics for new Phase 10 work.

## Compatibility fingerprint layers

All fingerprints use the same canonical compact JSON and UTF-8 SHA-256 rules.
Each layer carries `compatibility_contract_version=1` and depends on the exact
SHA-256 of the preceding layer.

### Historical compatibility

`build_historical_compatibility_fingerprint()` includes:

- the complete normalized Modeling Context and its verified
  `modeling_context_sha256`;
- exact resolved historical filters, including inclusive from/to dates;
- customer source checksum; and
- campaign-sales source checksum.

The builder rejects a mismatch between Modeling Context and resolved products,
campaign types/categories, offers, historical channels, conversion, or
contacted-only values. Filter lists are order-insensitive; dates and source
checksums are exact invalidators.

### Model compatibility

`build_model_compatibility_fingerprint()` includes:

- exact historical compatibility SHA-256;
- exact `analysis_run_id`;
- feature contract version and SHA-256;
- model-role policy version;
- evaluation contract version;
- training-eligibility policy version;
- automated-training policy version; and
- exact seed, validation fraction, and challenger-enabled setting.

Changing any one of these inputs changes the fingerprint. The builder refuses
to compose a model fingerprint from a fingerprint of the wrong layer.

### Scoring compatibility

`build_scoring_compatibility_fingerprint()` includes:

- exact model compatibility SHA-256;
- exact `model_run_id`;
- exact artifact SHA-256;
- demographic source checksum and population count; and
- exact score semantics.

Score semantics currently freeze finite range `[0,1]`, higher-is-better,
`propensity_score DESC, person_id ASC`, and mandatory full canonical-universe
coverage. Artifact, demographic source/count, ordering, or other semantic
changes produce a different scoring fingerprint.

Every supplied checksum is normalized to lowercase and must be exactly 64
hexadecimal characters. Layer type, positive IDs/counts, finite ranges, and
policy/version shapes fail closed through service and Pydantic validation.

## Deterministic example

For the representative two-product fixture in the focused tests:

| Identity | SHA-256 |
|---|---|
| Modeling Context | `3707a6a2d8554a4d8f2f9becb6a6bcdf270fd0e1a898c03db9ec55623d4762d9` |
| Historical compatibility | `0b271cf557862057f916bbfdc7b1b6bc5b68a21edd448906f1f9e45396a46c7f` |
| Model compatibility | `0cc8ff28805fac7f390e42bf38c72b433986dc74659140bb1a68b59b70a24e60` |
| Scoring compatibility | `666c43440f21bad6fdefbcdac3c9e4862a1bb549f8320c4871b593fbf1b0bcb5` |

These are contract examples, not registry records and not a claim that a
compatible persisted generation exists.

## Verification

| Gate | Result |
|---|---|
| New Phase 10 identity/fingerprint tests | PASS - 32 passed in 4.88s |
| Existing Phase 9 targeting-contract tests | PASS - 6 passed in 4.46s |
| New modules compile | PASS |
| Phase 9 context hash implementation modified | No |
| Database/schema migration | Not run; not required in Step 2 |
| Import/training/scoring/rank work | Not run |

The focused suite proves:

- input order and duplicates do not change canonical hashes;
- JSON is compact, deterministic, Unicode-preserving, and hashed as UTF-8;
- delivery channel, campaign details, targeting preferences, selection, and
  Target Group metadata do not change Modeling Context identity;
- every modeling dimension and policy version does change it;
- Phase 9 and Phase 10 hashes remain distinct;
- resolved filters must align with Modeling Context;
- historical fingerprints invalidate on exact date/source changes;
- model fingerprints invalidate on analysis, feature, governance, evaluation,
  eligibility, automated-training, seed, split, and challenger changes; and
- scoring fingerprints invalidate on model, artifact, demographics, population,
  and score-semantics changes.

## Stop boundary

Step 2 does not search existing runs, extend historical SQL, add registry
tables, execute pipelines, bridge Phase 9, or expose new endpoints/UI. Those
remain subsequent sequential steps.

`STOP_AFTER_STEP_02`
