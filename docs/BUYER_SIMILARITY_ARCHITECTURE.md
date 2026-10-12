# Buyer Similarity v3 architecture and contracts

Current implementation reference, 2026-10-11. Code baseline HEAD
`336875c30fc32b00323d916ecc45b232016168a1`, with uncommitted 14B
changes; schema **33**. See [Prompt 18's evidence](evidence/lookalike_v3/18_DOCUMENTATION.md)
for the current gate. Earlier Phase 11 architecture describes the original
v1/v2 route and remains historical where it conflicts with this v3 addition.

## Two separate kinds of intelligence

| | Buyer Similarity (v3) | Purchase Probability (v1/v2) |
|---|---|---|
| Input evidence | Exact product-specific historical `ATTRIBUTED_PURCHASE` buyers and the 11 prospect-compatible demographics | Historical customer/campaign training outcomes and governed probability model/calibration |
| Learned object | Supported descriptive buyer prototypes, fitted on customer-disjoint FIT buyers | PU model and, for v2, separately governed calibration artifact |
| Prospect score | `BUYER_PROFILE_DISTANCE_V1` similarity index, not a probability | Raw model score or calibrated purchase probability under its recorded version |
| Readiness | Product support, frozen split, current profile/score generation and verification attestation | Compatible model/scoring generation and applicable calibration governance |
| Selection | Inclusive cumulative `score >= similarity_minimum` | Recorded legacy semantics; v2 uses **discrete** probability bands |
| Result | Version-3 immutable membership with matched product and similarity lineage | Version-1/2 immutable membership with historical propensity lineage |

Both paths share imported demographics, product catalog, normalized hard
audience-filter semantics, durable search attempts/history, and guarded export.
They do **not** share a score meaning, calibration artifact, cache key, or
membership interpretation. Omitted API version fields retain the pinned
legacy behavior; v3 is explicitly requested by the business UI/API. Old
probability rows, artifacts, and exports are not converted.

```text
125K historical customers + 570K sales -> exact attributed buyers by product/context
                                              -> support-aware customer-disjoint split
                                              -> FIT-only scales and learned prototypes
5M independent demographic prospects ---------> verified score generation per product
                                              -> maximum valid product score per person
                                              -> exact AND/OR audience filters + minimum
                                              -> immutable, contact-free membership
                                              -> history/detail -> governed contact join/export
```

The prospect population has `person_id`; historical buyers have
`customer_id`. There is no inferred ID linkage. Campaign responses, sales,
IDs, and contact fields are not cold-prospect scoring features. User-entered
filters change eligibility, **not** the score for the same person under the
same profile. OR branches deduplicate by person ID.

## Method and selection

Eleven demographic features have fixed equal weights. FIT-buyer q05–q95
ranges scale numeric distances; categorical distance is zero for an exact
canonical match and one otherwise. Unknown or missing values contribute the
full feature distance, even when both are missing. Coverage is tracked
separately; below 0.80 gives no valid score. For each supported product,
`S = 1 - minimum weighted distance to a retained learned prototype`.
No held-out buyer is used to fit ranges, vocabulary, or prototypes.

With several selected products, `ANY_SELECTED_PRODUCT_MAX_V1` selects the
largest valid product score for each prospect; exact ties use ascending
product ID. Unsupported selected products block the context; they are not
silently dropped or substituted. The current support floor is 200 distinct
attributed buyers per product after context filters, with at least 160 FIT
and 40 HOLDOUT under `SIMILARITY_CUSTOMER_SPLIT_V2`. The old
`CUSTOMER_UNION_HASH_ORDER_80_20_V1` is explicit in historical artifacts,
not silently relabeled. The V2 split is customer-disjoint across the selected
product union and is a **descriptive buyer holdout**, not campaign-isolated
purchase-probability validation or prospective lift evidence.

A score **0.90** means nearest-prototype weighted distance is at most **0.10**
under this method. It does not mean 90% purchase probability, accuracy,
confidence, or percentile. Allowed minimums 0.50/0.60/0.70/0.80/0.90 are
inclusive and cumulative: 0.80 selects valid scores from 0.80 through 1.00.
The display tiers 50–<60 Exploratory, 60–<70 Broad, 70–<80 Good,
80–<90 Strong, 90–100 Very Strong are labels, not exclusive v3 selection
buckets. This differs from v2's discrete probability intervals: v2 0.80 is
`[0.80,0.90)`, legacy BROAD still maps to v2 0.60, and explicit v2 0.50
remains `[0.50,0.60)`.

## Durable lineage, invalidation, and reuse

| Change or event | V3 consequence | Probability consequence |
|---|---|---|
| Customer/sales import or historical context change | Reconcile cohort and split; stale incompatible profiles, generations, preflights, snapshots and exports | Independently recheck historical/model compatibility |
| Demographic import or feature-contract change | Rebuild/verify affected prospect generations, counts and memberships | Independently recheck scoring/currentness |
| Product support, split, FIT scales, prototype or score-method change | New versioned profile/generation; prior artifacts remain historical, not current | No implicit probability-model rewrite |
| Audience criteria/minimum change | New exact preflight/cache identity and membership; compatible verified scores may be reused | Its own versioned filter/band/cache identity |
| Delivery channel/profile change | Membership can be reused; export eligibility/contact join is rechecked | Same guarded export boundary |
| V3 outcome feedback | Validate immutable membership and retain outcome lineage; no automatic v3 profile retraining or probability recalibration | Governed v1/v2 feedback may trigger **calibration-only** update when its independent gates pass |
| Calibration artifact change | No automatic v3 invalidation when buyer source/profile is unchanged | Affected v2 probability readiness/currentness is rechecked |

The exact reusable snapshot is checked against source, profile, generation,
filter, method, count, ordering, and SHA-256 before reuse. On a miss, the
worker materializes a contact-free gzip membership in a temporary location,
validates it, and atomically publishes its registry/file lineage. Attempt
ownership and lease tokens fence stale workers. A retry creates another
attempt under the same user-visible search ID; a completed “Run again” is a
new search. Startup reconciles durable unfinished work. The v3 path bypasses
probability calibration and uses its own profile/scoring preparation, while
v1/v2 retain Phase 10 compatibility/reuse/build behavior.

The download boundary revalidates currentness and the immutable membership,
then joins only the selected profile's contact fields with consent and
contactability checks. Selected analytical members may exceed exportable
contacts. Export audit is append-only and separate by contract; no contact
PII belongs in analytical snapshots, result JSON, or screenshots. Download
does not send or activate a campaign.

## Deployment boundary

This is a local **single-node SQLite proof of concept**, not a distributed
service. The bounded coordinator accepts multiple durable submissions, but
heavy build/verification is serialized; SQLite locking, large score/index
tables, WAL/disk headroom, artifact-root integrity, and process restart must
be monitored. Do not run multiple independent application nodes or shared
artifact writers against the same SQLite file. The Prompt 16 measurements
are for one named Windows machine and disposable current 5M database, not
production SLOs. There is no authentication/RBAC, tenant isolation, outbound
activation, or remotely certified release gate in Prompt 18.

Sources: [approved semantics](../Prompts/Campaign_Implementation_Tool_14B_Lookalike_Prompt_Pack/01_APPROVED_V3_SEMANTICS.md),
[split recovery](evidence/lookalike_v3/15_1_SUPPORT_AWARE_SPLIT_RECOVERY.md),
[full-5M measurements](evidence/lookalike_v3/16_2_FULL5M_MEASUREMENTS.md),
[20 real runs](evidence/lookalike_v3/17_SCENARIOS.md), and
[operator guide](BUYER_SIMILARITY_OPERATOR_AND_DEMO.md).
