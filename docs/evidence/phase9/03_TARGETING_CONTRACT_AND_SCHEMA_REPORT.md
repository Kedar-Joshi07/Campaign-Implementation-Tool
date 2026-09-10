# Phase 9 Step 3 — Targeting Contract and Schema Report

## Outcome

Phase 9 now has backend-owned, versioned contracts for campaign context, business targeting criteria, match strength, age buckets, and income groups. Schema version 13 adds one normalized campaign-targeting context table through an additive migration.

No historical, model-training, scoring, audience, campaign, member-resolution, export, or lineage contract was replaced or weakened.

## Contract versions

| Contract | Constant | Version |
|---|---|---:|
| Business targeting segment | `TARGETING_SEGMENT_CONTRACT_VERSION` | 1 |
| Campaign targeting context | `CAMPAIGN_TARGETING_CONTEXT_CONTRACT_VERSION` | 1 |
| Business match strength | `BUSINESS_MATCH_STRENGTH_CONTRACT_VERSION` | 1 |
| Age buckets | `AGE_BUCKET_CONTRACT_VERSION` | 1 |
| Income groups | `INCOME_GROUP_CONTRACT_VERSION` | 1 |

Versions are represented as strings in persistence, consistent with the existing frozen contract columns.

## Match-strength contract

Business match strength is cumulative:

| Value | Display threshold | Audience Filter mapping |
|---|---:|---|
| `VERY_STRONG` | 0.90+ | `score_min = 0.90` |
| `STRONG` | 0.80+ | `score_min = 0.80` |
| `GOOD` | 0.70+ | `score_min = 0.70` |
| `BROAD` | 0.60+ | `score_min = 0.60` |

The configurable default is `GOOD` (0.70+).

The independently defined distribution bands are non-overlapping:

| Band | Range |
|---|---|
| Very Strong | 0.90–1.00 |
| Strong | 0.80–<0.90 |
| Good | 0.70–<0.80 |
| Broad | 0.60–<0.70 |
| Below Broad | 0.00–<0.60 |

The cumulative thresholds are not treated as 0.10 buckets.

## Server-owned demographic groups

Age bucket contract v1:

- 18–24
- 25–34
- 35–44
- 45–54
- 55–64
- 65–74
- 75+

Income group contract v1:

- <25K
- 25K–49,999
- 50K–74,999
- 75K–99,999
- 100K–149,999
- 150K–249,999
- 250K+

Both the stable machine values and display labels are backend-owned. The 75+ age group maps to the existing validated Audience Filter age ceiling of 100.

## Campaign context contract

The canonical context payload contains:

- `product_ids`
- `campaign_types`
- `campaign_categories`
- `offer_types`
- `campaign_channel`
- `historical_campaign_channels`
- `campaign_targeting_context_contract_version`

`campaign_channel` is the delivery channel and uses the existing Phase 7 supported values (`EMAIL`, `DIRECT_MAIL`). `historical_campaign_channels` is a separate optional context field and is not silently equated with delivery channel.

Normalization and validation rules:

1. Strings are trimmed.
2. Blank or non-string multi-select values are rejected.
3. Duplicate multi-select values are removed.
4. Multi-selects are sorted deterministically.
5. Extra/unversioned fields are rejected.
6. Product IDs, campaign types, campaign categories, offer types, and historical campaign channels are checked against caller-supplied current backend reference values.
7. Unknown selections are rejected before persistence.
8. Canonical JSON uses sorted keys, compact separators, ASCII-safe encoding, and forbids non-finite numbers.
9. A SHA-256 digest is generated from the exact canonical UTF-8 JSON bytes.

## Business targeting contract

The targeting criteria contract captures:

- match strength;
- gender, age groups, states, and income groups;
- progressively disclosed marital status, education, employment status, resident status, resident type, and employment type;
- family-size minimum/maximum;
- top matching percent;
- `ALL_MATCHING` or `TOP_N` selection and its validated target count.

Dynamic categorical values are checked against current backend reference vocabularies. Unknown values, inverted ranges, unknown fields, invalid bucket values, and inconsistent selection settings are rejected.

## Audience Filter Contract mapping

The mapping preserves existing Audience Filter Contract v1 semantics:

- match strength becomes `score_min`;
- business categorical selections map to the existing categorical filter fields;
- family size maps to `family_member_count_min` / `family_member_count_max`;
- top matching percent maps to `top_percentile_max`;
- selection maps through the existing Audience Selection Contract normalizer;
- age and income buckets map to the existing numeric min/max fields.

Adjacent selected buckets are merged only when their union is contiguous. Disjoint age or income buckets become deterministic OR branches, each of which is independently normalized by the existing Audience Filter Contract. The Cartesian product of disjoint age and income ranges preserves exact `(age group union) AND (income group union)` semantics; it never widens selections by collapsing gaps into a single min/max range.

Example:

```text
Age 18–24 OR 35–44
AND income <25K OR 50K–74,999
```

maps to four normalized Audience Filter branches, not one broad `age 18–44 / income 0–74,999` filter.

## Additive schema migration

`CURRENT_SCHEMA_VERSION` is now 13.

New table: `campaign_targeting_contexts`

| Column | Purpose |
|---|---|
| `targeting_context_id` | Independent planning-context identity |
| `campaign_id` | Optional unique link after a governed campaign draft exists |
| three contract-version columns | Freeze context, targeting, and match-strength semantics |
| `campaign_context_json` / `campaign_context_sha256` | Canonical context and exact digest |
| `targeting_criteria_json` / `targeting_criteria_sha256` | Canonical criteria and exact digest |
| `source_scoring_run_id` | Optional explicit targeting/scoring source link |
| `created_at` / `updated_at` | Lifecycle timestamps |

Database constraints enforce valid JSON, bounded contract/JSON text, 64-character digests, positive optional references, and restrictive foreign keys to campaigns and scoring runs. Indexes support newest-context retrieval and explicit scoring-source lookup.

The table intentionally does not add one column per checkbox. Business selections remain normalized, versioned JSON with deterministic hashes.

Migration behavior:

- version 12 upgrades to version 13 in the existing ordered transaction loop;
- all existing tables and rows are retained;
- repeated initialization is idempotent;
- a failed version-13 migration rolls back both DDL and schema-version advancement.

The workspace database was additively migrated to version 13 during application initialization. The new context table contains zero rows; no targeting source was inferred and no draft/context data was fabricated.

## Files

- `app/schemas/campaign_targeting.py`
- `app/services/campaign_targeting_contract_service.py`
- `app/database/schema.py`
- `tests/test_phase9_targeting_contracts.py`
- `tests/test_phase9_schema.py`
- `README.md`

## Verification

Focused Phase 9 contract and schema suite:

```text
.venv\Scripts\python.exe -m pytest tests\test_phase9_targeting_contracts.py tests\test_phase9_schema.py -q
10 passed in 15.54s
```

Historical schema compatibility suite, including all prior migration generations:

```text
.venv\Scripts\python.exe -m pytest tests\test_database_schema.py tests\test_phase3_schema.py tests\test_phase4_schema_jobs.py tests\test_phase5_schema.py tests\test_phase6_schema.py tests\test_phase9_schema.py tests\test_phase9_targeting_contracts.py -q
42 passed in 48.63s
```

Additional checks:

- `git diff --check`: passed;
- read-only workspace database check: schema version `13`, `campaign_targeting_contexts` row count `0`.

A broader non-cleanroom pytest selection was stopped after an existing test stopped emitting progress for several minutes. It had not reported a failure, and no data import, training, scoring, browser, clean-room, full-5M, or performance process was allowed to continue. This interrupted exploratory run is not used as acceptance evidence.

## Step boundary

Step 3 is complete. Repository persistence methods, APIs, wizard UI, campaign-context selectors, targeting controls, targeting-intelligence resolution, target preview, saved target groups, and campaign-draft creation remain reserved for their ordered later steps.
