# Buyer-similarity v3 descriptive-model factsheet

Current-status addendum, 2026-10-11: the Stage 08 observations below remain
historical bounded assurance. The later support-aware
`SIMILARITY_CUSTOMER_SPLIT_V2` is the current frozen partition policy; the
old union-hash `CUSTOMER_UNION_HASH_ORDER_80_20_V1` remains labeled in its
original artifacts. The V2 customer-disjoint HOLDOUT checks *descriptive
buyer-profile stability*, not campaign-isolated purchase-probability
validation, prospective lift, or repair of v2 calibration governance.

`BUYER_PROFILE_DISTANCE_V1` compares 11 normalized demographic fields with equal
weight. Numeric differences use fit-buyer q05–q95 ranges with declared zero-range
fallbacks; known categorical mismatches and missing or unknown features have
distance one. The score is one minus the smallest weighted prototype distance.
It is **not** purchase probability, percentile, confidence, response rate,
causal effect, or a count of matching attributes.

Historical attributed purchasers define each product's buyer cohort. The
customer-disjoint FIT subset alone defines bins, vocabulary, scales and
prototypes; HOLDOUT is descriptive only. Prospects are unlabeled, **not**
verified nonbuyers. Historical campaign records share a campaign component,
so the holdout does not repair probability-model leakage or establish
predictive performance. The historical AUC around 0.544 was nongoverned and
is not evidence that v3 improves it.

Stage 08 sampled the first 256 customers and prospects by source identifier,
plus 160 earbuds FIT buyers and 40 HOLDOUT buyers. This is bounded and not a
representative or five-million-row distribution certificate. The unrelated
cookware profile scored the earbuds holdout at a mean of 0.6489, slightly
above the earbuds profile's 0.6449. Three fit-only bootstrap replicates showed
top-quartile overlap Jaccard from 0.3333 to 0.6667. These observations do not
support a strong product-specificity claim; broad demographic resemblance may
include many people who will never buy.

The business explanation uses the actual winning-profile feature distances,
weights and coverage. For a saved result with at least five members, it averages
those terms over at most the first 50 selected members and shows the sample size, selected product and
historical fit-buyer support. It contains no member or prototype identifiers
and does not invent per-feature percentages. Response and lift validation
require independently observed outcome feedback or a suitable experimental
design. No automatic narrative AI or external model is used.

## Current measured scope and decision

Prompt 16.2 achieved `FULL5M_GO_ON_NAMED_HARDWARE` on a disposable current
five-million-person source. Three supported product profiles (PRD001,
PRD003, PRD004; published generation IDs 3/4/5 in that isolated database)
produced five million valid and zero invalid composite prospect scores.
The cumulative 0.50/0.60/0.70/0.80/0.90 counts were
4,935,724 / 4,280,439 / 2,412,119 / 591,372 / 43,384 in that specific
three-product context. This is distribution and integrity assurance, not
response prediction. [Measured resources and limitations](16_2_FULL5M_MEASUREMENTS.md).

Prompt 17's unchanged canonical scenarios all passed exact preflight with
the current profile/source context and the unchanged 10,000 minimum; all
20 real runs completed with identical preflight, immutable-member and
reopened-result counts. The smallest and largest were 25,765 and 627,218.
System-Chrome evidence and one governed representative export passed.
This is a **demo-readiness GO**, not a general promise that arbitrary
products or criteria will yield 10,000 customers. Original scenario JSON
SHA-256 `d168deccf2f7cf9723b5bc08a4b99bf0dc49325309c1a402cd59ba4beabb2b77`,
profile-set SHA-256 `b754deaacf04a6b2781c9b090ed2b476a24c33fa2cb770c7be972e1def`.
[Scenario report and screenshots](17_SCENARIOS.md).

The allowed conclusion is a reproducible **descriptive resemblance index**
under the declared feature/distance method. Product-specific predictive
discrimination, purchase-response accuracy, calibration and lift remain
**unvalidated / NO-GO for claims**. No actual future outcome labels or
prospective experiment were used to validate the 20 demo runs. V3 feedback,
if uploaded and validated against immutable membership, is retained with
lineage; it does not automatically refit these buyer profiles. Governed
v1/v2 feedback can update calibration only, not model features or raw scores.
